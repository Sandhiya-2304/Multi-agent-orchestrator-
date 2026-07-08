import asyncio
import json
import re
import sys
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse, FileResponse

from backend.db import (
    create_conversation,
    update_conversation_title,
    save_message,
    list_conversations,
    load_messages,
    delete_conversation,
    get_conversation_owner,
)
from backend.schemas import ChatRequest, LoginRequest
from backend.orchestrator.orchestrator import SDLCOrchestrator
from backend.service.service import OpenAIService
from backend.rag.config import (
    ALLOWED_EXTENSIONS,
    RAG_ATTACHMENT_MAX_CHARS,
    RAG_ATTACHMENT_MAX_CHARS_LIST,
    RAG_FULL_CONTEXT_CHAR_BUDGET,
    RAG_LIST_MIN_SCORE,
    RAG_LIST_TOP_K,
    RAG_MAX_UPLOAD_MB,
    RAG_MIN_SCORE,
    RAG_TOP_K,
)
from backend.rag.knowledge_base import RAGModelUnavailableError, RAGService
from agent_framework import Agent

router = APIRouter()

# Every chat belongs to the signed-in account that created it, identified by
# this header (the frontend sends the MSAL account's homeAccountId). There is
# no server-side verification of the Microsoft-issued token yet, so this only
# stops different users from *accidentally* sharing chats through the UI --
# it is not a substitute for real bearer-token validation against Azure AD.
def require_user_id(x_user_id: str | None = Header(default=None, alias="X-User-Id")) -> str:
    return x_user_id or "anonymous"


def ensure_conversation_access(conversation_id: int, user_id: str) -> None:
    owner = get_conversation_owner(conversation_id)
    if owner is not None and owner != user_id:
        raise HTTPException(status_code=404, detail="Chat workspace not found")

# Questions asking for every matching record ("list all IT students in the
# hostel") need broad recall across the whole source table, not just the
# handful of chunks closest to the query's own wording -- a top-4 similarity
# search reliably returns one or two rows and nothing else for these.
_LISTING_INTENT_RE = re.compile(
    r"\b(all|every|each|list|everyone|who\s+are|how\s+many|complete\s+list|full\s+list|names?\s+of)\b",
    re.IGNORECASE,
)


def is_listing_query(message: str) -> bool:
    return bool(_LISTING_INTENT_RE.search(message or ""))

import os

if os.environ.get("VERCEL"):
    OUTPUT_DIR = Path("/tmp/output").resolve()
else:
    OUTPUT_DIR = Path("output").resolve()
    
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Shared Orchestrator Instance
orchestrator = SDLCOrchestrator()

# Shared RAG Service Instance
rag_service = RAGService()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def generate_smart_chat_title(user_message: str, assistant_reply: str) -> str:
    try:
        title_agent = Agent(
            client=OpenAIService(),
            instructions=(
                "You are a precise conversation titler. "
                "Analyze the user request and assistant reply, then return a concise 3-to-4 word title. "
                "Output ONLY raw title text."
            ),
        )
        prompt = f"User Request: {user_message}\nAssistant Reply Summary: {assistant_reply[:300]}"
        result = await title_agent.run(prompt)
        title_text = result.text if hasattr(result, "text") else str(result)
        cleaned_title = title_text.strip().strip('"').strip("'")
        return cleaned_title[:40] if cleaned_title else "AI Development Chat"
    except Exception:
        words = (user_message or "").strip().split()
        return " ".join(words[:5]).strip() if words else "AI Development Chat"


def zip_folder(folder_path: Path) -> BytesIO:
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for file_path in folder_path.rglob("*"):
            if file_path.is_file():
                zip_file.write(file_path, file_path.relative_to(folder_path))
    zip_buffer.seek(0)
    return zip_buffer


def find_project_dir(project_folder: str) -> Path | None:
    if not OUTPUT_DIR.exists():
        return None

    direct = OUTPUT_DIR / project_folder
    if direct.exists() and direct.is_dir():
        return direct

    for p in OUTPUT_DIR.iterdir():
        if p.is_dir() and p.name == project_folder:
            return p

    return None

# ---------------------------------------------------------------------------
# Download Endpoints
# ---------------------------------------------------------------------------

@router.get("/download/project/{project_folder}")
def download_entire_project(project_folder: str):
    target_dir = find_project_dir(project_folder)
    if not target_dir:
        raise HTTPException(status_code=404, detail="Project folder not found")

    zip_buffer = zip_folder(target_dir)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{target_dir.name}.zip"'},
    )


@router.get("/download/file")
def download_single_agent_file(project_folder: str = Query(...), file_name: str = Query(...)):
    target_dir = find_project_dir(project_folder)
    if not target_dir:
        raise HTTPException(status_code=404, detail="Target workspace not discovered")

    requested_path = Path(file_name)
    if requested_path.is_absolute() or ".." in requested_path.parts:
        raise HTTPException(status_code=400, detail="Invalid file path")
        
    target_file = (target_dir / requested_path).resolve()
    if not target_file.is_relative_to(target_dir.resolve()):
        raise HTTPException(status_code=400, detail="Access denied")

    if not target_file.exists() or not target_file.is_file():
        raise HTTPException(status_code=404, detail=f"Artifact {file_name} not found")

    return FileResponse(path=target_file, filename=target_file.name, media_type="text/plain")


# ---------------------------------------------------------------------------
# Knowledge Base (RAG) Endpoints
# ---------------------------------------------------------------------------

@router.post("/documents/upload")
async def upload_document(file: UploadFile = File(...), conversation_id: str | None = Form(None)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext or '(none)'}")

    raw = await file.read()
    if len(raw) > RAG_MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"File exceeds {RAG_MAX_UPLOAD_MB} MB limit")

    # A file attached from inside a chat is private to that conversation --
    # only the Knowledge Base modal (which never sends conversation_id) adds
    # to the shared store visible everywhere.
    conv_id_int = None
    if conversation_id and conversation_id != "new":
        try:
            conv_id_int = int(conversation_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid Chat Identifier")

    try:
        return await rag_service.ingest_document(file.filename, raw, conversation_id=conv_id_int)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RAGModelUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/documents")
def get_documents():
    return rag_service.list_documents()


@router.delete("/documents/{document_id}")
def remove_document(document_id: int):
    rag_service.delete_document(document_id)
    return {"ok": True, "document_id": document_id}


# ---------------------------------------------------------------------------
# Chat CRUD Endpoints
# ---------------------------------------------------------------------------

@router.post("/login")
def login(req: LoginRequest):
    return {"ok": True, "email": req.email}


@router.get("/chats")
def get_chats(user_id: str = Depends(require_user_id)):
    rows = list_conversations(user_id=user_id)
    return [
        {"id": row["id"], "title": row["title"], "created_at": row["created_at"], "updated_at": row["updated_at"]}
        for row in rows
    ]


@router.post("/chats/new")
def new_chat(user_id: str = Depends(require_user_id)):
    chat_id = create_conversation("New Chat", user_id=user_id)
    return {"chat_id": chat_id, "title": "New Chat"}


@router.get("/chat/{conversation_id}")
def get_chat(conversation_id: str, user_id: str = Depends(require_user_id)):
    if conversation_id == "new":
        return {"id": "new", "messages": []}

    try:
        conv_id_int = int(conversation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid workspace identifier")

    ensure_conversation_access(conv_id_int, user_id)

    rows = load_messages(conv_id_int)
    formatted_messages = []

    for row in rows:
        if row.get("msg_type") == "sdlc":
            try:
                sdlc_data = json.loads(row["content"])
                formatted_messages.append({"role": "assistant", "msg_type": "sdlc", "content": sdlc_data})
            except Exception:
                formatted_messages.append({"role": row["role"], "msg_type": "text", "content": row["content"]})
        else:
            formatted_messages.append({
                "role": row["role"],
                "msg_type": "text",
                "content": row["content"],
                "attachment_filenames": row.get("attachment_filenames") or [],
            })

    return {"id": conv_id_int, "messages": formatted_messages}


@router.delete("/chats/{conversation_id}")
def remove_chat(conversation_id: int, user_id: str = Depends(require_user_id)):
    ensure_conversation_access(conversation_id, user_id)
    delete_conversation(conversation_id)
    return {"ok": True, "chat_id": conversation_id}


# ---------------------------------------------------------------------------
# Orchestration Execution
# ---------------------------------------------------------------------------

@router.post("/chat/{conversation_id}")
async def chat(conversation_id: str, req: ChatRequest, user_id: str = Depends(require_user_id)):
    """
    Main entry point for user messages.
    Delegates to SDLCOrchestrator and awaits result.
    """
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    if conversation_id == "new":
        raise HTTPException(status_code=400, detail="Initialize conversation session entry row first.")

    try:
        conv_id_int = int(conversation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Chat Identifier")

    ensure_conversation_access(conv_id_int, user_id)

    try:
        # Load previous messages to build conversation history for memory
        rows = load_messages(conv_id_int)
        history_text = ""
        if rows:
            history_text = "Previous conversation context:\n"
            for r in rows[-10:]:  # Keep only the last 10 interactions to avoid huge prompts
                role_name = "User" if r["role"] == "user" else "Assistant"
                content = r["content"]
                if r["msg_type"] == "sdlc":
                    try:
                        payload = json.loads(content)
                        content = f"[SDLC project generated: {payload.get('project_title', 'unknown')}]"
                    except Exception:
                        pass
                history_text += f"{role_name}: {content}\n"
            history_text += "\n"

        # Save user message
        save_message(conv_id_int, "user", "text", message, attachment_filenames=req.attachment_filenames)

        # Retrieve knowledge-base context, scoped to what THIS conversation is
        # allowed to see. If this chat has its own uploaded file(s), scope
        # STRICTLY to those and ignore the shared Knowledge Base entirely --
        # otherwise a question this chat's file doesn't answer could still get
        # answered from unrelated shared documents, which looks like the wrong
        # file's information leaking in. The shared Knowledge Base only grounds
        # chats that haven't attached anything of their own.
        sources: list[dict] = []
        context_blocks: list[str] = []
        listing_query = is_listing_query(message)
        own_doc_ids = rag_service.document_ids_owned_by_conversation(conv_id_int)
        allowed_doc_ids = own_doc_ids if own_doc_ids else rag_service.document_ids_for_conversation(conv_id_int)

        if allowed_doc_ids:
            if rag_service.total_content_chars_for_documents(allowed_doc_ids) <= RAG_FULL_CONTEXT_CHAR_BUDGET:
                # Small enough: don't gamble on similarity search finding every
                # relevant row for every possible phrasing of a question -- just
                # hand the model every document this conversation can see, in full.
                for doc_id in allowed_doc_ids:
                    full = rag_service.get_document_context(doc_id, max_chars=RAG_ATTACHMENT_MAX_CHARS_LIST)
                    if full:
                        context_blocks.append(f"[Source: {full['filename']}]\n{full['text']}")
                        sources.append({"document_id": full["document_id"], "filename": full["filename"], "score": 1.0})
            else:
                top_k = RAG_LIST_TOP_K if listing_query else RAG_TOP_K
                min_score = RAG_LIST_MIN_SCORE if listing_query else RAG_MIN_SCORE
                hits = await rag_service.retrieve(
                    message, top_k=top_k, min_score=min_score, allowed_document_ids=allowed_doc_ids
                )

                if listing_query:
                    # Chunk-level top-k is fundamentally the wrong tool for "list
                    # everyone matching X" -- any fixed k can still land short of
                    # every matching row. Use the hits only to find WHICH documents
                    # are relevant, then pull each one's full text so no row from a
                    # relevant document is left out. Capped to the best few
                    # documents so this can't blow up context size if many
                    # unrelated documents share a stray keyword.
                    seen_doc_ids: list[int] = []
                    for h in hits:
                        if h["document_id"] not in seen_doc_ids:
                            seen_doc_ids.append(h["document_id"])
                    for doc_id in seen_doc_ids[:3]:
                        full = rag_service.get_document_context(doc_id, max_chars=RAG_ATTACHMENT_MAX_CHARS_LIST)
                        if full:
                            context_blocks.append(f"[Source: {full['filename']}]\n{full['text']}")
                            sources.append({"document_id": full["document_id"], "filename": full["filename"], "score": 1.0})
                else:
                    for h in hits:
                        context_blocks.append(f"[Source: {h['filename']}]\n{h['text']}")
                        sources.append({"document_id": h["document_id"], "filename": h["filename"], "score": round(h["score"], 3)})

        # Files attached to *this* message are always used, regardless of how well
        # the question's wording matches them via similarity search -- otherwise
        # generic questions like "what is this file about?" retrieve nothing.
        # Only honored if the document actually belongs to this conversation (or
        # the shared KB) -- a stray/forged document_id from elsewhere is ignored.
        attachment_max_chars = RAG_ATTACHMENT_MAX_CHARS_LIST if listing_query else RAG_ATTACHMENT_MAX_CHARS
        for doc_id in req.attachment_document_ids:
            if doc_id not in allowed_doc_ids:
                continue
            if any(s["document_id"] == doc_id for s in sources):
                continue
            attached = rag_service.get_document_context(doc_id, max_chars=attachment_max_chars)
            if attached:
                context_blocks.insert(0, f"[Attached file: {attached['filename']}]\n{attached['text']}")
                sources.insert(0, {"document_id": attached["document_id"], "filename": attached["filename"], "score": 1.0})

        context_text = "\n\n".join(context_blocks)

        # Use the intent classifier in the orchestrator to decide routing
        is_sdlc = await orchestrator.is_sdlc_request(message)

        if not is_sdlc:
            # Chat mode
            reply = await orchestrator.handle_chat(message, history_text, context_text)
            save_message(conv_id_int, "assistant", "text", reply)
            title = await generate_smart_chat_title(message, reply)
            update_conversation_title(conv_id_int, title)
            return {
                "chat_id": conv_id_int,
                "mode": "chat",
                "msg_type": "text",
                "reply": reply,
                "sources": sources,
            }

        # SDLC mode (this can take 1-3 minutes depending on tools used by LLM)
        payload = await orchestrator.execute_sdlc(message, history_text, context_text)
        payload["sources"] = sources

        # Save and return
        save_message(conv_id_int, "assistant", "sdlc", json.dumps(payload))
        title = await generate_smart_chat_title(message, payload.get("reply", ""))
        update_conversation_title(conv_id_int, title)

        return payload
    except HTTPException:
        raise
    except Exception as e:
        # An uncaught exception here would otherwise reach the client as a
        # plain-text 500 ("Internal Server Error") instead of JSON, which
        # breaks the frontend's res.json() call and shows a useless generic
        # error. Surface what actually broke instead -- most commonly a
        # missing/invalid AZURE_OPENAI_* environment variable in this
        # deployment, since every path above (intent classification, chat,
        # SDLC generation, title generation) calls out to that model.
        print(f"[routes] /chat/{conversation_id} failed: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")