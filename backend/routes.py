import asyncio
import json
import re
import sys
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse, FileResponse

from backend.db import (
    create_conversation,
    update_conversation_title,
    save_message,
    list_conversations,
    load_messages,
    delete_conversation,
)
from backend.schemas import ChatRequest, LoginRequest
from backend.orchestrator.orchestrator import SDLCOrchestrator
from backend.service.service import OpenAIService
from agent_framework import Agent

router = APIRouter()

import os

if os.environ.get("VERCEL"):
    OUTPUT_DIR = Path("/tmp/output").resolve()
else:
    OUTPUT_DIR = Path("output").resolve()
    
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Shared Orchestrator Instance
orchestrator = SDLCOrchestrator()


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
# Chat CRUD Endpoints
# ---------------------------------------------------------------------------

@router.post("/login")
def login(req: LoginRequest):
    return {"ok": True, "email": req.email}


@router.get("/chats")
def get_chats():
    rows = list_conversations()
    return [
        {"id": row["id"], "title": row["title"], "created_at": row["created_at"], "updated_at": row["updated_at"]}
        for row in rows
    ]


@router.post("/chats/new")
def new_chat():
    chat_id = create_conversation("New Chat")
    return {"chat_id": chat_id, "title": "New Chat"}


@router.get("/chat/{conversation_id}")
def get_chat(conversation_id: str):
    if conversation_id == "new":
        return {"id": "new", "messages": []}

    try:
        conv_id_int = int(conversation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid workspace identifier")

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
            formatted_messages.append({"role": row["role"], "msg_type": "text", "content": row["content"]})

    return {"id": conv_id_int, "messages": formatted_messages}


@router.delete("/chats/{conversation_id}")
def remove_chat(conversation_id: int):
    delete_conversation(conversation_id)
    return {"ok": True, "chat_id": conversation_id}


# ---------------------------------------------------------------------------
# Orchestration Execution
# ---------------------------------------------------------------------------

@router.post("/chat/{conversation_id}")
async def chat(conversation_id: str, req: ChatRequest):
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
    save_message(conv_id_int, "user", "text", message)

    # Use basic heuristic in orchestrator to decide routing
    is_sdlc = orchestrator.is_sdlc_request(message)

    if not is_sdlc:
        # Chat mode
        reply = await orchestrator.handle_chat(message, history_text)
        save_message(conv_id_int, "assistant", "text", reply)
        title = await generate_smart_chat_title(message, reply)
        update_conversation_title(conv_id_int, title)
        return {
            "chat_id": conv_id_int,
            "mode": "chat",
            "msg_type": "text",
            "reply": reply,
        }

    # SDLC mode (this can take 1-3 minutes depending on tools used by LLM)
    payload = await orchestrator.execute_sdlc(message, history_text)

    # Save and return
    save_message(conv_id_int, "assistant", "sdlc", json.dumps(payload))
    title = await generate_smart_chat_title(message, payload.get("reply", ""))
    update_conversation_title(conv_id_int, title)

    return payload