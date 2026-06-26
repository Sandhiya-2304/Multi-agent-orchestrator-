import asyncio
import json
import os
import re
from datetime import datetime

import streamlit as st

from db import (
    init_db,
    create_conversation,
    save_message,
    list_conversations,
    load_messages,
    delete_conversation,
    update_conversation_title,
)
from orchestrator import SDLCOrchestrator
from agents.chat_agent import ChatAgent

st.set_page_config(page_title="AI Assistant", page_icon="🤖", layout="wide")
init_db()

if "messages" not in st.session_state:
    st.session_state.messages = []
if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = None
if "pending_new_chat" not in st.session_state:
    st.session_state.pending_new_chat = False
if "selected_conversation_id" not in st.session_state:
    st.session_state.selected_conversation_id = None
if "title_updated" not in st.session_state:
    st.session_state.title_updated = False

qp_chat_id = st.query_params.get("chat_id", None)
if qp_chat_id and qp_chat_id != "newchat" and st.session_state.conversation_id is None:
    try:
        cid = int(str(qp_chat_id).replace("chatid", ""))
        st.session_state.conversation_id = cid
        st.session_state.selected_conversation_id = cid
        st.session_state.pending_new_chat = False
        st.session_state.messages = load_messages(cid)
    except Exception:
        pass


def get_language(filename):
    ext_map = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".java": "java", ".cpp": "cpp", ".c": "c", ".go": "go",
        ".rs": "rust", ".rb": "ruby", ".php": "php", ".sql": "sql",
        ".html": "html", ".css": "css", ".md": "markdown",
        ".json": "json", ".yaml": "yaml", ".sh": "bash",
        ".tf": "terraform", ".tsx": "typescript", ".jsx": "javascript"
    }
    _, ext = os.path.splitext(filename.lower())
    return ext_map.get(ext, "text")


def generate_task_name(user_request):
    text = re.sub(r"[^a-z0-9\s]", " ", user_request.lower())
    words = text.split()
    stop_words = {
        "build", "create", "make", "generate", "develop",
        "write", "using", "with", "that", "this", "what",
        "about", "the", "and", "for", "from", "to", "in", "on",
        "a", "an", "is", "are", "was", "were", "be", "been",
        "project", "app", "application", "system", "service"
    }
    key_words = [w for w in words if w not in stop_words and w.isalnum()]
    task_name = "_".join(key_words[:2])
    return task_name[:25] if task_name else "my_project"


def should_run_sdlc(prompt: str) -> bool:
    p = prompt.lower()
    triggers = [
        "build", "create", "generate", "develop", "implement",
        "make a", "make an", "write a", "write an",
        "i want to build", "i want to create", "i need a",
        "project", "application", "app", "api", "service",
        "dashboard", "website", "system", "platform"
    ]
    return sum(1 for t in triggers if t in p) >= 2


async def generate_chat_title(chat_agent, user_prompt, assistant_text):
    title_prompt = f"""
Generate a short, professional conversation title.

User message:
{user_prompt}

Assistant reply:
{assistant_text}

Rules:
- Return only the title.
- 2 to 6 words.
- No quotes.
- Be specific.
"""
    result = await chat_agent.run(title_prompt)

    if result is None:
        title = "New Chat"
    elif hasattr(result, "text"):
        title = result.text or "New Chat"
    elif isinstance(result, dict):
        title = result.get("content") or result.get("text") or "New Chat"
    else:
        title = str(result)

    title = re.sub(r"\s+", " ", title).strip()
    title = re.sub(r'["\'`]', "", title)
    return title[:50] if title else "New Chat"


def start_pending_new_chat():
    st.session_state.messages = []
    st.session_state.conversation_id = None
    st.session_state.selected_conversation_id = None
    st.session_state.pending_new_chat = True
    st.session_state.title_updated = False
    st.query_params["chat_id"] = "newchat"


def open_chat(conversation_id):
    st.session_state.conversation_id = conversation_id
    st.session_state.selected_conversation_id = conversation_id
    st.session_state.pending_new_chat = False
    st.session_state.title_updated = True
    st.session_state.messages = load_messages(conversation_id)
    st.query_params["chat_id"] = f"chatid{conversation_id}"


def render_section_download(section_data):
    if isinstance(section_data, str):
        try:
            section_data = json.loads(section_data)
        except Exception:
            st.warning("Could not load downloadable section.")
            return

    if not isinstance(section_data, dict):
        st.warning("Could not load downloadable section.")
        return

    filename = section_data.get("filename", "download.txt")
    sections = section_data.get("sections", {})
    content = sections.get(filename, section_data.get("content", ""))

    st.download_button(
        label=f"📥 Download {filename}",
        data=content,
        file_name=filename,
        mime="text/plain",
        use_container_width=True,
        key=f"download_{filename}_{datetime.now().timestamp()}"
    )


def display_sdlc_result_inline(result_data):
    sections = result_data["sections"]
    task_name = result_data["task_name"]
    folder = f"output/{task_name}"

    present_sections = [
        k for k in [
            "requirements", "user_stories", "architecture",
            "code", "testing", "documentation", "deployment"
        ]
        if sections.get(k)
    ]

    summary = (
        f"✅ SDLC task completed.\n\n"
        f"Generated: {', '.join(present_sections)}.\n\n"
        f"📁 Output saved in: `{folder}/`"
    )
    st.session_state.messages.append({"role": "assistant", "msg_type": "text", "content": summary})
    save_message(st.session_state.conversation_id, "assistant", "text", summary)

    def add_section_message(label, filename, content, is_code=False):
        if is_code:
            lang = get_language(filename)
            preview = f"```{lang}\n{content}\n```"
        else:
            preview = content

        header = f"{label} (`{filename}`)"
        body = f"**{header}**\n\n{preview}"

        st.session_state.messages.append({"role": "assistant", "msg_type": "text", "content": body})
        save_message(st.session_state.conversation_id, "assistant", "text", body)

        section_data = {
            "task_name": task_name,
            "sections": {filename: content},
            "label": label,
            "filename": filename,
            "is_code": is_code,
        }
        section_json = json.dumps(section_data)
        st.session_state.messages.append({
            "role": "assistant",
            "msg_type": "section_download",
            "content": section_json
        })
        save_message(st.session_state.conversation_id, "assistant", "section_download", section_json)

    if sections.get("requirements"):
        add_section_message("📋 Requirements", "requirements.txt", sections["requirements"])
    if sections.get("user_stories"):
        add_section_message("📝 User Stories", "user_stories.txt", sections["user_stories"])
    if sections.get("architecture"):
        add_section_message("🏗️ Architecture", "architecture.txt", sections["architecture"])
    if sections.get("code"):
        code_filename = sections.get("filename", "code.py")
        add_section_message("💻 Code", code_filename, sections["code"], is_code=True)
    if sections.get("testing"):
        add_section_message("🧪 Testing", "testing.txt", sections["testing"])
    if sections.get("documentation"):
        add_section_message("📚 Documentation", "documentation.txt", sections["documentation"])
    if sections.get("deployment"):
        add_section_message("🚀 Deployment", "deployment.txt", sections["deployment"])
    if sections.get("code_review"):
        add_section_message("🔍 Code Review", "code_review.txt", sections["code_review"])

st.markdown('<div style="font-size:2.5rem;font-weight:700;color:#1E88E5;text-align:center;margin-bottom:0.5rem;padding:1.5rem 0;">🤖 AI Assistant</div>', unsafe_allow_html=True)
st.markdown('<div style="font-size:1.2rem;color:#666;text-align:center;margin-bottom:2rem;">Powered by Azure OpenAI</div>', unsafe_allow_html=True)

st.markdown("""
<style>
section[data-testid="stSidebar"] {
    width: 280px !important;
    padding-top: 0.5rem;
    padding-left: 0.5rem;
    padding-right: 0.5rem;
}

section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] span {
    font-size: 12px !important;
}

section[data-testid="stSidebar"] .stButton > button {
    font-size: 13px !important;
    min-height: 2rem;
    padding: 0.35rem 0.6rem;
    white-space: nowrap !important;
}
div[class*="st-key-new_chat_btn"] button:hover {
    background-color: #1e88e5;
    color: white;
}
            
<style>
.stChatMessage {
    padding: 1rem;
    font-size: 1.05rem;
    max-width: 100%;
}
.stChatInput textarea {
    min-height: 20px;
    font-size: 1.05rem !important;
    max-width: 100%;
}
""", unsafe_allow_html=True)


def short_title(title, max_len=24):
    return title if len(title) <= max_len else title[:max_len - 3] + "..."

with st.sidebar:
    st.header("Chat History")

    if st.button("➕ New Chat",key="new_chat_btn", use_container_width=True):
        start_pending_new_chat()
        st.rerun()

    conversations = list_conversations()

    if conversations:
        st.subheader("Saved Chats")

        for row in conversations:
            left, right = st.columns([3, 1], gap="small", vertical_alignment="center")

            with left:
                label = short_title(row["title"])
                if st.button(
                    label,
                    key=f"open_{row['id']}",
                    use_container_width=True,
                    help=row["title"]
                ):
                    open_chat(row["id"])
                    st.rerun()

            with right:
                if st.button(
                    "🗑️",
                    key=f"del_{row['id']}",
                    help="Delete Chat"
                ):
                    delete_conversation(row["id"])

                    if st.session_state.conversation_id == row["id"]:
                        st.session_state.conversation_id = None
                        st.session_state.messages = []
                        st.session_state.pending_new_chat = True
                        st.session_state.title_updated = False
                        st.query_params["chat_id"] = "newchat"

                    st.rerun()

async def chat_loop():
    for message in st.session_state.messages:
        with st.chat_message(message["role"], avatar="👤" if message["role"] == "user" else "🤖"):
            if message["msg_type"] == "text":
                st.markdown(message["content"], unsafe_allow_html=True)
            elif message["msg_type"] == "section_download":
                render_section_download(message["content"])

    if prompt := st.chat_input("Type a message…", key="chat_input_big"):
        if st.session_state.conversation_id is None:
            new_id = create_conversation("New Chat")
            st.session_state.conversation_id = new_id
            st.session_state.selected_conversation_id = new_id
            st.session_state.pending_new_chat = False
            st.query_params["chat_id"] = str(new_id)

        st.session_state.messages.append({"role": "user", "msg_type": "text", "content": prompt})
        save_message(st.session_state.conversation_id, "user", "text", prompt)

        with st.chat_message("user", avatar="👤"):
            st.markdown(prompt)

        with st.status("🔄 Thinking…", expanded=False) as status:
            try:
                if should_run_sdlc(prompt):
                    status.update(label="🔄 Running multi-agent SDLC pipeline…")
                    start_time = datetime.now()
                    task_name = generate_task_name(prompt)

                    orchestrator = SDLCOrchestrator()
                    result = await orchestrator.execute(task_name, prompt)

                    execution_time = (datetime.now() - start_time).total_seconds()

                    result_data = {
                        "task_name": task_name,
                        "timestamp": datetime.now().isoformat(),
                        "user_request": prompt,
                        "sections": result,
                        "execution_time": execution_time
                    }

                    display_sdlc_result_inline(result_data)
                    status.update(label="✅ SDLC pipeline completed.")

                    if st.session_state.conversation_id and not st.session_state.title_updated:
                        chat_agent = ChatAgent()
                        ai_title = await generate_chat_title(
                            chat_agent,
                            prompt,
                            result_data["sections"].get("code_review", result_data["sections"].get("documentation", "New Chat"))
                        )
                        update_conversation_title(st.session_state.conversation_id, ai_title)
                        st.session_state.title_updated = True
                else:
                    status.update(label="🔄 Chatting…")
                    chat_agent = ChatAgent()

                    lines = []
                    for m in st.session_state.messages[-10:]:
                        if m.get("msg_type") == "text":
                            if m["role"] == "user":
                                lines.append(f"User: {m['content']}")
                            else:
                                lines.append(f"Assistant: {m['content']}")

                    lines.append(f"User: {prompt}")
                    chat_prompt = "\n".join(lines)

                    chat_result = await chat_agent.run(chat_prompt)

                    if chat_result is None:
                        text = "(No response from chat agent)"
                    elif hasattr(chat_result, "text"):
                        text = chat_result.text or "(Empty response)"
                    elif isinstance(chat_result, dict):
                        text = chat_result.get("content") or chat_result.get("text") or "(Empty response)"
                    else:
                        text = str(chat_result)

                    if not text.strip():
                        text = "(Empty response from chat agent)"

                    st.session_state.messages.append({"role": "assistant", "msg_type": "text", "content": text})
                    save_message(st.session_state.conversation_id, "assistant", "text", text)

                    if st.session_state.conversation_id and not st.session_state.title_updated:
                        ai_title = await generate_chat_title(chat_agent, prompt, text)
                        update_conversation_title(st.session_state.conversation_id, ai_title)
                        st.session_state.title_updated = True

                    status.update(label="✅ Response ready.")
            except Exception as e:
                err = "❌ Error: " + str(e)
                st.error(err)
                save_message(st.session_state.conversation_id, "assistant", "text", err)

        st.rerun()


async def main():
    await chat_loop()


if __name__ == "__main__":
    asyncio.run(main())