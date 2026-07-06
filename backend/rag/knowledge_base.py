import numpy as np

from backend import db
from backend.rag.chunking import chunk_text
from backend.rag.config import (
    INDEX_PATH,
    RAG_ATTACHMENT_MAX_CHARS,
    RAG_CHUNK_OVERLAP,
    RAG_CHUNK_SIZE,
    RAG_MIN_SCORE,
    RAG_TOP_K,
)
from backend.rag.embeddings import RAGModelUnavailableError, embed_texts
from backend.rag.loaders import load_document
from backend.rag.vector_store import FAISSVectorStore

__all__ = ["RAGService", "RAGModelUnavailableError"]


class RAGService:
    def __init__(self):
        self.store = FAISSVectorStore(INDEX_PATH)

    def is_enabled(self) -> bool:
        # Embeddings run locally -- no external credentials required, so RAG
        # is always available (an unavailable model is handled per-call below).
        return True

    def is_empty(self) -> bool:
        return self.store.ntotal == 0

    async def ingest_document(self, filename: str, raw_bytes: bytes, conversation_id: int | None = None) -> dict:
        text = load_document(filename, raw_bytes)
        chunks = chunk_text(text, RAG_CHUNK_SIZE, RAG_CHUNK_OVERLAP)
        if not chunks:
            raise ValueError(f"No extractable text found in {filename}")

        # Replace rather than accumulate: re-uploading the same filename (e.g. a
        # corrected version of a file) previously left the stale copy sitting in
        # the knowledge base forever, so both versions got mixed into retrieval.
        # Scoped to the same conversation (or both global) so two different
        # chats can each have their own file with the same name.
        existing_id = db.get_document_id_by_filename(filename, conversation_id=conversation_id)
        if existing_id is not None:
            self.delete_document(existing_id)

        vectors = await embed_texts(chunks)
        self.store.ensure_ready(dim=len(vectors[0]))

        document_id = db.create_document(filename, conversation_id=conversation_id)
        chunk_ids = [db.add_document_chunk(document_id, i, c) for i, c in enumerate(chunks)]
        try:
            self.store.add(
                np.array(chunk_ids, dtype="int64"),
                np.array(vectors, dtype="float32"),
            )
        except Exception:
            db.delete_document(document_id)
            raise

        db.update_document_chunk_count(document_id, len(chunks))
        return {"id": document_id, "filename": filename, "chunk_count": len(chunks)}

    async def retrieve(
        self,
        query: str,
        top_k: int = RAG_TOP_K,
        min_score: float = RAG_MIN_SCORE,
        allowed_document_ids: set[int] | None = None,
    ) -> list[dict]:
        if self.is_empty():
            return []

        try:
            [query_vector] = await embed_texts([query])
        except RAGModelUnavailableError as e:
            print(f"[rag] embedding model unavailable, skipping retrieval: {e}")
            return []

        # When scoped to a conversation, a chunk from a document outside the
        # allowed set (another chat's private attachment) must never appear in
        # the results -- so over-fetch before filtering, or a few disallowed
        # hits landing in the raw top-k could crowd out every allowed one.
        raw_top_k = top_k if allowed_document_ids is None else min(top_k * 5, 200)
        hits = self.store.search(np.array([query_vector], dtype="float32"), raw_top_k)
        hits = [(chunk_id, score) for chunk_id, score in hits if score >= min_score]
        if not hits:
            return []

        rows = db.get_chunks_by_ids([chunk_id for chunk_id, _ in hits])
        results = []
        for chunk_id, score in hits:
            row = rows.get(chunk_id)
            if not row:
                continue
            if allowed_document_ids is not None and row["document_id"] not in allowed_document_ids:
                continue
            results.append({
                "chunk_id": chunk_id,
                "document_id": row["document_id"],
                "filename": row["filename"],
                "text": row["content"],
                "score": score,
            })
            if len(results) >= top_k:
                break
        return results

    def get_document_context(self, document_id: int, max_chars: int = RAG_ATTACHMENT_MAX_CHARS) -> dict | None:
        """Full text of a specific document, bypassing similarity search entirely.
        Used to guarantee a just-attached file is used for the message it was
        attached to, even when the question's wording doesn't embed close to
        the document's content (e.g. "what does this file say?")."""
        doc = db.get_document(document_id)
        if not doc:
            return None

        text = db.get_document_full_text(document_id)
        if len(text) > max_chars:
            text = text[:max_chars] + "\n\n[...truncated...]"

        return {"document_id": document_id, "filename": doc["filename"], "text": text}

    def delete_document(self, document_id: int) -> None:
        chunk_ids = db.get_document_chunk_ids(document_id)
        if chunk_ids:
            self.store.remove(np.array(chunk_ids, dtype="int64"))
        db.delete_document(document_id)

    def list_documents(self) -> list[dict]:
        return db.list_documents()

    def document_ids_for_conversation(self, conversation_id: int) -> set[int]:
        return db.get_document_ids_for_conversation(conversation_id)

    def document_ids_owned_by_conversation(self, conversation_id: int) -> set[int]:
        return db.get_document_ids_owned_by_conversation(conversation_id)

    def total_content_chars_for_documents(self, document_ids: set[int]) -> int:
        return db.get_total_chunk_chars_for_document_ids(document_ids)
