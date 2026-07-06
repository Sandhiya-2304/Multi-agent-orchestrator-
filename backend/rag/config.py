import os
from pathlib import Path

# Embeddings are generated locally via fastembed (ONNX Runtime), not via an
# Azure OpenAI deployment -- no separate embedding deployment/credentials
# needed, and no PyTorch dependency (fastembed's onnxruntime backend is tens
# of MB installed vs. torch's several hundred MB-to-multi-GB, which is what
# blew past Vercel's 500MB serverless function size limit under
# sentence-transformers). This is the ONNX port of the exact same model, so
# embedding behavior/quality is unchanged.
RAG_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# fastembed caches downloaded model files under this directory. Vercel's
# filesystem is read-only except /tmp, matching the pattern already used for
# RAG_DIR/DB_PATH elsewhere in this app.
RAG_EMBEDDING_CACHE_DIR = "/tmp/fastembed_cache" if os.environ.get("VERCEL") else None

RAG_CHUNK_SIZE = 1500
# No overlap by default: an overlapping tail carried into the next chunk means
# reconstructing a document's full text (chunk-by-chunk, in order) duplicates
# that overlapping text -- harmless for narrow chunk search, but it corrupts
# the "hand the model the whole document" path below with repeated rows.
RAG_CHUNK_OVERLAP = 0
RAG_TOP_K = 6
RAG_MAX_UPLOAD_MB = 20
# Minimum cosine similarity for a retrieved chunk to be used at all -- without
# this, unrelated uploaded documents get pulled into every query's context
# just because they're the "closest" match, even when nothing is actually close.
RAG_MIN_SCORE = 0.35
# "List everyone in X" / "how many Y are there" questions need recall across
# every matching row, not just the handful of chunks closest to the query's
# own wording -- a broad question naturally scores lower against any single
# row than a narrow one does. Widen the net for those instead of always
# pulling a huge top-k (which would dilute normal Q&A with noise).
RAG_LIST_TOP_K = 25
RAG_LIST_MIN_SCORE = 0.15
# Cap on how much of a just-attached document gets forced into context (characters).
RAG_ATTACHMENT_MAX_CHARS = 12000
# Same cap, but for listing-style questions where truncating the source
# table/list would silently drop rows from the answer.
RAG_ATTACHMENT_MAX_CHARS_LIST = 40000
# When the whole knowledge base fits under this many characters, skip
# similarity search for retrieval entirely and just hand the model every
# document in full. Similarity search can always miss something depending on
# how a question happens to be phrased or how content happens to be chunked;
# for a knowledge base this size, giving the model everything is cheap and
# categorically can't omit anything.
RAG_FULL_CONTEXT_CHAR_BUDGET = 100000

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".csv", ".json", ".xlsx", ".pptx", ".zip"}

if os.environ.get("VERCEL"):
    RAG_DIR = Path("/tmp/rag_store")
else:
    RAG_DIR = Path("rag_store")

INDEX_PATH = RAG_DIR / "index.faiss"
