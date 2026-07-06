import asyncio

from backend.rag.config import RAG_EMBEDDING_MODEL


class RAGModelUnavailableError(Exception):
    """Raised when the local embedding model cannot be loaded (e.g. package
    missing, or no internet access on first run to download the model)."""


_model = None
_model_lock = asyncio.Lock()


def _load_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(RAG_EMBEDDING_MODEL)


async def _get_model():
    global _model
    if _model is None:
        async with _model_lock:
            if _model is None:
                try:
                    _model = await asyncio.to_thread(_load_model)
                except Exception as e:
                    raise RAGModelUnavailableError(
                        f"Local embedding model '{RAG_EMBEDDING_MODEL}' could not be loaded: {e}"
                    ) from e
    return _model


async def embed_texts(texts: list[str]) -> list[list[float]]:
    model = await _get_model()
    vectors = await asyncio.to_thread(model.encode, texts)
    return [v.tolist() for v in vectors]
