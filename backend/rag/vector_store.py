from pathlib import Path

import faiss
import numpy as np


class FAISSVectorStore:
    """Cosine-similarity FAISS index (inner product over L2-normalized vectors)
    with id-based removal via IndexIDMap2, so deleted documents' vectors are
    actually removed rather than merely orphaned."""

    def __init__(self, index_path: Path):
        self.index_path = index_path
        self.index: faiss.Index | None = self._load()

    def _load(self):
        try:
            if self.index_path.exists():
                return faiss.read_index(str(self.index_path))
        except Exception as e:
            print(f"[rag] index file unreadable/corrupt, starting empty: {e}")
        return None

    @property
    def ntotal(self) -> int:
        return self.index.ntotal if self.index is not None else 0

    def ensure_ready(self, dim: int) -> None:
        if self.index is None:
            self.index = faiss.IndexIDMap2(faiss.IndexFlatIP(dim))

    def add(self, ids: np.ndarray, vectors: np.ndarray) -> None:
        faiss.normalize_L2(vectors)
        self.index.add_with_ids(vectors, ids)
        self.persist()

    def search(self, query_vec: np.ndarray, top_k: int) -> list[tuple[int, float]]:
        if self.index is None or self.index.ntotal == 0:
            return []
        faiss.normalize_L2(query_vec)
        scores, ids = self.index.search(query_vec, top_k)
        return [(int(i), float(s)) for i, s in zip(ids[0], scores[0]) if i != -1]

    def remove(self, ids: np.ndarray) -> None:
        if self.index is not None and len(ids):
            self.index.remove_ids(ids)
            self.persist()

    def persist(self) -> None:
        if self.index is not None:
            self.index_path.parent.mkdir(parents=True, exist_ok=True)
            faiss.write_index(self.index, str(self.index_path))
