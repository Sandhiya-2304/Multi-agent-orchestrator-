import json
import sqlite3
from datetime import datetime

import os

if os.environ.get("VERCEL"):
    DB_PATH = "/tmp/chat_history.db"
else:
    DB_PATH = "chat_history.db"


_db_initialized = False

def get_db_connection():
    global _db_initialized
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    
    if not os.environ.get("VERCEL"):
        conn.execute("PRAGMA foreign_keys = ON;")
    
    if not _db_initialized:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                msg_type TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                attachment_filename TEXT,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
        """)
        # Defensive migration for databases created before attachment_filename existed.
        try:
            conn.execute("ALTER TABLE messages ADD COLUMN attachment_filename TEXT")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists
        # attachment_filenames stores a JSON array, supporting multiple files per message
        # (attachment_filename above is kept only for older rows written before this).
        try:
            conn.execute("ALTER TABLE messages ADD COLUMN attachment_filenames TEXT")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists
        conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                chunk_count INTEGER NOT NULL DEFAULT 0,
                uploaded_at TEXT NOT NULL,
                conversation_id INTEGER
            )
        """)
        # conversation_id NULL means "shared knowledge base" (visible to every
        # chat, uploaded via the Knowledge Base modal). A file attached inside
        # a specific chat gets that chat's conversation_id, so it's only ever
        # visible in that one conversation -- it must never leak into others.
        try:
            conn.execute("ALTER TABLE documents ADD COLUMN conversation_id INTEGER")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists
        conn.execute("""
            CREATE TABLE IF NOT EXISTS document_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
            )
        """)
        conn.commit()
        _db_initialized = True
        
    return conn

def init_db():
    get_db_connection().close()



def create_conversation(title="New Chat"):
    now = datetime.now().isoformat()
    conn = get_db_connection()
    cur = conn.execute(
        "INSERT INTO conversations (title, created_at, updated_at) VALUES (?, ?, ?)",
        (title, now, now),
    )
    conn.commit()
    conversation_id = cur.lastrowid
    conn.close()
    return conversation_id


def update_conversation_title(conversation_id, title):
    now = datetime.now().isoformat()
    conn = get_db_connection()
    conn.execute(
        "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
        (title, now, conversation_id),
    )
    conn.commit()
    conn.close()


def save_message(conversation_id, role, msg_type, content, attachment_filenames=None):
    now = datetime.now().isoformat()
    attachments_json = json.dumps(attachment_filenames) if attachment_filenames else None
    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO messages (conversation_id, role, msg_type, content, created_at, attachment_filenames) VALUES (?, ?, ?, ?, ?, ?)",
            (conversation_id, role, msg_type, content, now, attachments_json),
        )
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now, conversation_id),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        # The conversation was deleted while this message was being generated
        # (e.g. a multi-minute SDLC build finishing after the user deleted the
        # chat mid-run) -- there's nothing left to attach it to, so drop it
        # instead of crashing the whole request with an uncaught 500.
        print(f"[db] conversation {conversation_id} no longer exists, dropping message")
    finally:
        conn.close()


def list_conversations():
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT id, title, created_at, updated_at FROM conversations ORDER BY updated_at DESC"
    ).fetchall()
    conn.close()
    return rows


def load_messages(conversation_id):
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT role, msg_type, content, attachment_filenames FROM messages WHERE conversation_id = ? ORDER BY id ASC",
        (conversation_id,),
    ).fetchall()
    conn.close()

    messages = []
    for r in rows:
        row = dict(r)
        raw = row.pop("attachment_filenames")
        try:
            row["attachment_filenames"] = json.loads(raw) if raw else []
        except (TypeError, ValueError):
            row["attachment_filenames"] = []
        messages.append(row)
    return messages


def delete_conversation(conversation_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
    conn.commit()
    conn.close()


def get_document_id_by_filename(filename, conversation_id=None):
    conn = get_db_connection()
    if conversation_id is None:
        row = conn.execute(
            "SELECT id FROM documents WHERE filename = ? AND conversation_id IS NULL ORDER BY id DESC LIMIT 1",
            (filename,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT id FROM documents WHERE filename = ? AND conversation_id = ? ORDER BY id DESC LIMIT 1",
            (filename, conversation_id),
        ).fetchone()
    conn.close()
    return row["id"] if row else None


def get_document_ids_for_conversation(conversation_id):
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT id FROM documents WHERE conversation_id = ? OR conversation_id IS NULL",
        (conversation_id,),
    ).fetchall()
    conn.close()
    return {r["id"] for r in rows}


def get_document_ids_owned_by_conversation(conversation_id):
    """Only this conversation's own attachments -- excludes the shared
    Knowledge Base, unlike get_document_ids_for_conversation above."""
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT id FROM documents WHERE conversation_id = ?", (conversation_id,)
    ).fetchall()
    conn.close()
    return {r["id"] for r in rows}


def get_total_chunk_chars_for_document_ids(document_ids):
    if not document_ids:
        return 0
    conn = get_db_connection()
    placeholders = ",".join("?" for _ in document_ids)
    row = conn.execute(
        f"SELECT SUM(LENGTH(content)) AS total FROM document_chunks WHERE document_id IN ({placeholders})",
        list(document_ids),
    ).fetchone()
    conn.close()
    return row["total"] or 0


def create_document(filename, conversation_id=None):
    now = datetime.now().isoformat()
    conn = get_db_connection()
    cur = conn.execute(
        "INSERT INTO documents (filename, chunk_count, uploaded_at, conversation_id) VALUES (?, 0, ?, ?)",
        (filename, now, conversation_id),
    )
    conn.commit()
    document_id = cur.lastrowid
    conn.close()
    return document_id


def update_document_chunk_count(document_id, chunk_count):
    conn = get_db_connection()
    conn.execute(
        "UPDATE documents SET chunk_count = ? WHERE id = ?",
        (chunk_count, document_id),
    )
    conn.commit()
    conn.close()


def add_document_chunk(document_id, chunk_index, content):
    conn = get_db_connection()
    cur = conn.execute(
        "INSERT INTO document_chunks (document_id, chunk_index, content) VALUES (?, ?, ?)",
        (document_id, chunk_index, content),
    )
    conn.commit()
    chunk_id = cur.lastrowid
    conn.close()
    return chunk_id


def list_documents():
    """Documents in the shared Knowledge Base only (visible to every chat) --
    not the ones privately attached inside a specific conversation."""
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT id, filename, chunk_count, uploaded_at FROM documents WHERE conversation_id IS NULL ORDER BY uploaded_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]




def get_document(document_id):
    conn = get_db_connection()
    row = conn.execute(
        "SELECT id, filename, chunk_count, uploaded_at FROM documents WHERE id = ?",
        (document_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_document_full_text(document_id):
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT content FROM document_chunks WHERE document_id = ? ORDER BY chunk_index ASC",
        (document_id,),
    ).fetchall()
    conn.close()
    return "\n\n".join(r["content"] for r in rows)


def get_document_chunk_ids(document_id):
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT id FROM document_chunks WHERE document_id = ?", (document_id,)
    ).fetchall()
    conn.close()
    return [r["id"] for r in rows]


def get_chunks_by_ids(ids):
    if not ids:
        return {}
    conn = get_db_connection()
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"""
        SELECT document_chunks.id AS id,
               document_chunks.content AS content,
               document_chunks.document_id AS document_id,
               documents.filename AS filename
        FROM document_chunks
        JOIN documents ON documents.id = document_chunks.document_id
        WHERE document_chunks.id IN ({placeholders})
        """,
        ids,
    ).fetchall()
    conn.close()
    return {r["id"]: dict(r) for r in rows}


def delete_document(document_id):
    # Explicit two-step delete: PRAGMA foreign_keys is skipped on Vercel (see
    # get_db_connection above), so ON DELETE CASCADE can't be relied on there.
    conn = get_db_connection()
    conn.execute("DELETE FROM document_chunks WHERE document_id = ?", (document_id,))
    conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
    conn.commit()
    conn.close()