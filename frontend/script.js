const chatList = document.getElementById("chatList");
const chatMessages = document.getElementById("chatMessages");
const chatForm = document.getElementById("chatForm");
const messageInput = document.getElementById("messageInput");
const newChatBtn = document.getElementById("newChatBtn");

let chats = [];
let currentChatId = null;
let turns = [];
let isLoading = false;

function escapeHtml(str) {
  return String(str || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function markdownToHtml(md) {
  let html = escapeHtml(md || "");
  html = html.replace(/^### (.*$)/gim, "<h3>$1</h3>");
  html = html.replace(/^## (.*$)/gim, "<h2>$1</h2>");
  html = html.replace(/^# (.*$)/gim, "<h1>$1</h1>");
  html = html.replace(/\*\*(.*?)\*\*/gim, "<strong>$1</strong>");
  html = html.replace(/`([^`]+)`/gim, "<code>$1</code>");
  html = html.replace(/\n/g, "<br>");
  return html;
}

function setUrlToNewChat() {
  history.pushState({ chatId: "new" }, "", "/chat/new");
}

function setUrlToChatId(chatId) {
  const cleanId = String(chatId).trim();
  history.replaceState({ chatId: cleanId }, "", `/chat/${encodeURIComponent(cleanId)}`);
}

function renderCodeBlock(code) {
  const pre = document.createElement("pre");
  pre.className = "code-block";
  const codeEl = document.createElement("code");
  codeEl.textContent = code || "";
  pre.appendChild(codeEl);
  return pre;
}

function buildSection(title, content, isCode, projectFolder, fileName) {
  if (!String(content || "").trim()) return null;

  const wrap = document.createElement("div");
  wrap.className = "sdlc-section-block agent-card-block";
  wrap.style.marginBottom = "20px";

  const headRow = document.createElement("div");
  headRow.className = "agent-card-header";

  const headTitle = document.createElement("span");
  headTitle.textContent = title;
  headRow.appendChild(headTitle);
  wrap.appendChild(headRow);

  const body = document.createElement("div");
  body.className = "agent-card-body";
  if (isCode) {
    body.appendChild(renderCodeBlock(content));
  } else {
    body.innerHTML = markdownToHtml(content);
  }
  wrap.appendChild(body);

  if (projectFolder && fileName) {
    const dBtn = document.createElement("button");
    dBtn.type = "button";
    dBtn.className = "individual-agent-dl";
    dBtn.innerHTML = `<i class="fa-solid fa-download"></i> Download ${fileName}`;
    dBtn.onclick = () => {
      const url = `/api/download/file?project_folder=${encodeURIComponent(projectFolder)}&file_name=${encodeURIComponent(fileName)}`;
      window.open(url, "_blank");
    };
    wrap.appendChild(dBtn);
  }

  return wrap;
}

function buildSdlcCard(data) {
  const container = document.createElement("div");
  container.className = "sdlc-output-container";

  // Removing title and folder tags per user request


  const files = data?.files && typeof data.files === "object" ? data.files : {};
  Object.keys(files).forEach((key) => {
    const fileConfig = files[key];
    const block = buildSection(
      fileConfig.title || key,
      fileConfig.content,
      !!fileConfig.is_code,
      data.project_folder,
      fileConfig.file_name
    );
    if (block) container.appendChild(block);
  });

  if (data?.project_folder && data?.has_zip) {
    const globalZipBtn = document.createElement("button");
    globalZipBtn.type = "button";
    globalZipBtn.className = "download-btn";
    globalZipBtn.style.width = "100%";
    globalZipBtn.style.padding = "12px";
    globalZipBtn.style.marginTop = "10px";
    globalZipBtn.innerHTML = '<i class="fa-solid fa-box-archive"></i> Download Entire Project Workspace (.zip)';
    globalZipBtn.onclick = () => {
      window.open(`/api/download/project/${encodeURIComponent(data.project_folder)}`, "_blank");
    };
    container.appendChild(globalZipBtn);
  }

  return container;
}

function buildMessage(role, content, isSdlc = false, sdlcData = null) {
  const div = document.createElement("div");
  div.className = `message ${role}`;

  const contentDiv = document.createElement("div");
  contentDiv.className = "message-content";

  if (isSdlc && sdlcData) {
    if (content) {
      const textDiv = document.createElement("div");
      textDiv.innerHTML = markdownToHtml(content);
      textDiv.style.marginBottom = "16px";
      contentDiv.appendChild(textDiv);
    }
    contentDiv.appendChild(buildSdlcCard(sdlcData));
  } else {
    contentDiv.innerHTML = markdownToHtml(content);
  }

  div.appendChild(contentDiv);
  return div;
}

function renderMessages() {
  chatMessages.innerHTML = "";

  turns.forEach((turn) => {
    chatMessages.appendChild(buildMessage("user", turn.user, false, null));

    if (turn.loading) {
      const loadingDiv = document.createElement("div");
      loadingDiv.className = "message assistant loading";
      
      const dots = `<span class="typing-dots"><span></span><span></span><span></span></span>`;
      const loadingText = turn.expectedMode === "sdlc" ? `Generating SDLC... ${dots}` : `Typing... ${dots}`;
      
      loadingDiv.innerHTML = `<div class="message-content">${loadingText}</div>`;
      chatMessages.appendChild(loadingDiv);
      return;
    }

    if (turn.mode === "sdlc") {
      chatMessages.appendChild(buildMessage("assistant", turn.sdlcData?.reply || "", true, turn.sdlcData));
    } else if (turn.assistant) {
      chatMessages.appendChild(buildMessage("assistant", turn.assistant, false, null));
    }
  });

  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function renderChatList() {
  chatList.innerHTML = "";

  chats.forEach((chat) => {
    const item = document.createElement("div");
    item.className = `chat-item ${String(chat.id) === String(currentChatId) ? "active" : ""}`;

    const title = document.createElement("span");
    title.textContent = chat.title || "Chat Workspace";
    title.onclick = () => openChat(chat.id);

    const del = document.createElement("button");
    del.type = "button";
    del.textContent = "Delete";
    del.onclick = async (e) => {
      e.stopPropagation();
      await fetch(`/api/chats/${chat.id}`, { method: "DELETE" });
      chats = chats.filter((c) => String(c.id) !== String(chat.id));

      if (String(currentChatId) === String(chat.id)) {
        currentChatId = null;
        turns = [];
        setUrlToNewChat();
        renderMessages();
      }

      renderChatList();
    };

    item.appendChild(title);
    item.appendChild(del);
    chatList.appendChild(item);
  });
}

async function loadChats() {
  const res = await fetch("/api/chats");
  chats = await res.json();
  renderChatList();
}

async function openChat(chatId) {
  const cleanId = String(chatId).trim();
  currentChatId = cleanId;
  setUrlToChatId(cleanId);

  turns = [];
  renderMessages();
  renderChatList();

  const res = await fetch(`/api/chat/${encodeURIComponent(cleanId)}`);
  const data = await res.json();

  if (Array.isArray(data.messages)) {
    let lastTurn = null;

    data.messages.forEach((msg) => {
      if (msg.role === "user") {
        lastTurn = {
          user: msg.content || "",
          assistant: "",
          mode: "chat",
          loading: false,
          sdlcData: null,
        };
        turns.push(lastTurn);
      } else if (msg.role === "assistant" && lastTurn) {
        if (msg.msg_type === "sdlc") {
          let parsed = msg.content;
          if (typeof parsed === "string") {
            try {
              parsed = JSON.parse(parsed);
            } catch {
              parsed = {};
            }
          }
          lastTurn.mode = "sdlc";
          lastTurn.sdlcData = parsed;
        } else {
          lastTurn.mode = "chat";
          lastTurn.assistant = msg.content || "";
        }
      }
    });
  }

  renderChatList();
  renderMessages();
}

function guessIntent(text) {
  const lower = text.toLowerCase();
  const projectVerbs = ["create", "build", "develop", "generate", "design", "implement", "make", "construct", "code", "program"];
  const projectNouns = ["system", "application", "app", "project", "platform", "api", "website", "webapp", "service", "tool", "dashboard", "software", "crud"];
  
  const hasVerb = projectVerbs.some(v => lower.includes(v));
  const hasNoun = projectNouns.some(n => lower.includes(n));
  const hasExplicit = lower.includes("sdlc") || lower.includes("pipeline") || lower.includes("only code");
  
  return (hasVerb && hasNoun) || hasExplicit ? "sdlc" : "chat";
}

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();

  const text = messageInput.value.trim();
  if (!text || isLoading) return;

  isLoading = true;

  if (!currentChatId || currentChatId === "new") {
    try {
      const res = await fetch("/api/chats/new", { method: "POST" });
      const data = await res.json();
      currentChatId = String(data.chat_id);
      setUrlToChatId(currentChatId);
    } catch (err) {
      console.error("Failed to provision chat entry row:", err);
      isLoading = false;
      return;
    }
  }

  const expectedMode = guessIntent(text);

  const turn = {
    user: text,
    assistant: "",
    mode: "chat",
    expectedMode: expectedMode,
    loading: true,
    sdlcData: null,
  };

  turns.push(turn);
  messageInput.value = "";
  renderMessages();

  try {
    const res = await fetch(`/api/chat/${encodeURIComponent(currentChatId)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });

    const data = await res.json();
    const lastTurn = turns[turns.length - 1];

    if (data.mode === "sdlc") {
      lastTurn.mode = "sdlc";
      lastTurn.sdlcData = data;
    } else {
      lastTurn.mode = "chat";
      lastTurn.assistant = data.reply || "";
    }

    await loadChats();
  } catch (err) {
    console.error(err);
    const lastTurn = turns[turns.length - 1];
    if (lastTurn) lastTurn.assistant = "Something went wrong during generation.";
  } finally {
    const lastTurn = turns[turns.length - 1];
    if (lastTurn) lastTurn.loading = false;
    isLoading = false;
    
    renderChatList();
    renderMessages();
    
    setTimeout(() => {
      const main = document.querySelector('.main');
      if (main) main.scrollTop = main.scrollHeight;
    }, 100);
  }
});

messageInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    if (!isLoading) chatForm.requestSubmit();
  }
});

newChatBtn.onclick = async () => {
  currentChatId = "new";
  turns = [];
  setUrlToNewChat();
  renderMessages();
  renderChatList();
};

window.onload = async () => {
  await loadChats();

  const chatId = window.location.pathname.split("/")[2];
  if (chatId && chatId !== "new") {
    await openChat(chatId);
  } else if (chatId === "new") {
    currentChatId = "new";
    turns = [];
    renderMessages();
    renderChatList();
  }
};

window.addEventListener("popstate", async () => {
  const chatId = window.location.pathname.split("/")[2];
  if (chatId && chatId !== "new") {
    await openChat(chatId);
  }
});