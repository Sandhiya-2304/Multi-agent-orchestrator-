import sqlite3
from datetime import datetime

DB_PATH = "chat_history.db"


def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db():
    conn = get_db_connection()
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
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        )
    """)
    conn.commit()
    conn.close()


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
    conn = get_db_connection()
    conn.execute(
        "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
        (title, datetime.now().isoformat(), conversation_id),
    )
    conn.commit()
    conn.close()


def save_message(conversation_id, role, msg_type, content):
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO messages (conversation_id, role, msg_type, content, created_at) VALUES (?, ?, ?, ?, ?)",
        (conversation_id, role, msg_type, content, datetime.now().isoformat()),
    )
    conn.execute(
        "UPDATE conversations SET updated_at = ? WHERE id = ?",
        (datetime.now().isoformat(), conversation_id),
    )
    conn.commit()
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
        "SELECT role, msg_type, content FROM messages WHERE conversation_id = ? ORDER BY id ASC",
        (conversation_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_conversation(conversation_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
    conn.commit()
    conn.close()