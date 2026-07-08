const chatList = document.getElementById("chatList");
const chatMessages = document.getElementById("chatMessages");
const chatForm = document.getElementById("chatForm");
const messageInput = document.getElementById("messageInput");
const newChatBtn = document.getElementById("newChatBtn");

const sidebar = document.getElementById("sidebar");
const sidebarToggle = document.getElementById("sidebarToggle");
const sidebarBackdrop = document.getElementById("sidebarBackdrop");

let msalInstance = null;
const loginPage = document.getElementById("loginPage");
const chatApp = document.getElementById("chatApp");
const msLoginBtn = document.getElementById("msLoginBtn");
const logoutBtn = document.getElementById("logoutBtn");
const sidebarProfile = document.getElementById("sidebarProfile");
const profileMenu = document.getElementById("profileMenu");
const profileAvatar = document.getElementById("profileAvatar");



const attachWrapper = document.getElementById("attachWrapper");
const attachBtn = document.getElementById("attachBtn");
const attachMenu = document.getElementById("attachMenu");
const attachMenuUpload = document.getElementById("attachMenuUpload");
const attachFileInput = document.getElementById("attachFileInput");
const attachmentPreview = document.getElementById("attachmentPreview");
const uploadStatusLine = document.getElementById("uploadStatusLine");
const dropOverlay = document.getElementById("dropOverlay");
const sendBtn = document.getElementById("sendBtn");
const mainEl = document.querySelector(".main");

// Files staged in the composer, not yet sent. Each entry:
// { localId, file, status: 'pending'|'uploading'|'processing'|'success'|'error',
//   progress, documentId, error, previewUrl }
let pendingAttachments = [];
let attachmentSeq = 0;

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

function getInitials(name) {
  if (!name) return "U";
  const parts = name.trim().split(" ");
  if (parts.length >= 2) {
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }
  return parts[0][0].toUpperCase();
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
      const a = document.createElement("a");
      a.href = url;
      a.download = fileName;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
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
      const url = `/api/download/project/${encodeURIComponent(data.project_folder)}`;
      const a = document.createElement("a");
      a.href = url;
      a.download = "";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    };
    container.appendChild(globalZipBtn);
  }

  return container;
}

function buildMessageAttachments(attachments) {
  if (!attachments || !attachments.length) return null;
  const list = document.createElement("div");
  list.className = "message-attachments";
  attachments.forEach((att) => {
    const chip = document.createElement("div");
    chip.className = `message-attachment-chip${att.status === "error" ? " is-error" : ""}`;
    const icon = att.status === "error" ? "fa-triangle-exclamation" : getFileIconClass(att.filename);
    chip.innerHTML = `<i class="fa-solid ${icon}"></i> <span>${escapeHtml(att.filename)}</span>`;
    if (att.status === "error") chip.title = att.error || "Upload failed";
    list.appendChild(chip);
  });
  return list;
}

function buildMessage(role, content, isSdlc = false, sdlcData = null, sources = [], attachments = []) {
  const div = document.createElement("div");
  div.className = `message ${role}${isSdlc ? " is-wide" : ""}`;

  const contentDiv = document.createElement("div");
  contentDiv.className = "message-content";

  if (role === "user") {
    const attachmentsEl = buildMessageAttachments(attachments);
    if (attachmentsEl) contentDiv.appendChild(attachmentsEl);
  }

  if (isSdlc && sdlcData) {
    if (content) {
      const textDiv = document.createElement("div");
      textDiv.innerHTML = markdownToHtml(content);
      textDiv.style.marginBottom = "16px";
      contentDiv.appendChild(textDiv);
    }
    contentDiv.appendChild(buildSdlcCard(sdlcData));
    sources = sdlcData.sources || sources;
  } else {
    const textDiv = document.createElement("div");
    textDiv.innerHTML = markdownToHtml(content);
    contentDiv.appendChild(textDiv);
  }

  div.appendChild(contentDiv);
  return div;
}

function renderMessages() {
  chatMessages.innerHTML = "";

  turns.forEach((turn) => {
    chatMessages.appendChild(buildMessage("user", turn.user, false, null, [], turn.attachments || []));

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
      chatMessages.appendChild(buildMessage("assistant", turn.assistant, false, null, turn.sources || []));
    }
  });

  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function closeAllChatItemMenus() {
  document.querySelectorAll(".chat-item-menu").forEach((m) => m.classList.add("hidden"));
  document.querySelectorAll(".chat-item-more").forEach((b) => b.classList.remove("is-open"));
}

function renderChatList() {
  chatList.innerHTML = "";

  chats.forEach((chat) => {
    const item = document.createElement("div");
    item.className = `chat-item ${String(chat.id) === String(currentChatId) ? "active" : ""}`;

    const title = document.createElement("span");
    title.textContent = chat.title || "Chat Workspace";
    title.onclick = () => {
      openChat(chat.id);
      closeSidebar();
    };

    const actions = document.createElement("div");
    actions.className = "chat-item-actions";

    const moreBtn = document.createElement("button");
    moreBtn.type = "button";
    moreBtn.className = "chat-item-more";
    moreBtn.setAttribute("aria-label", "Chat options");
    moreBtn.innerHTML = `<i class="fa-solid fa-ellipsis"></i>`;

    const menu = document.createElement("div");
    menu.className = "chat-item-menu hidden";

    const del = document.createElement("button");
    del.type = "button";
    del.className = "chat-item-menu-item";
    del.innerHTML = `<i class="fa-solid fa-trash"></i> Delete`;
    del.onclick = async (e) => {
      e.stopPropagation();
      closeAllChatItemMenus();
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
    menu.appendChild(del);

    moreBtn.onclick = (e) => {
      e.stopPropagation();
      const isHidden = menu.classList.contains("hidden");
      closeAllChatItemMenus();
      if (isHidden) {
        menu.classList.remove("hidden");
        moreBtn.classList.add("is-open");
      }
    };

    actions.appendChild(moreBtn);
    actions.appendChild(menu);

    item.appendChild(title);
    item.appendChild(actions);
    chatList.appendChild(item);
  });
}

document.addEventListener("click", (e) => {
  if (!e.target.closest(".chat-item-actions")) closeAllChatItemMenus();
});

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
          attachments: (msg.attachment_filenames || []).map((filename) => ({ filename, status: "success" })),
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

const IMAGE_EXTENSIONS = new Set(["png", "jpg", "jpeg", "gif", "webp", "bmp", "svg"]);

function getFileIconClass(filename) {
  const ext = String(filename || "").split(".").pop().toLowerCase();
  if (ext === "pdf") return "fa-file-pdf";
  if (ext === "docx" || ext === "doc") return "fa-file-word";
  if (ext === "xlsx" || ext === "xls" || ext === "csv") return "fa-file-excel";
  if (ext === "pptx" || ext === "ppt") return "fa-file-powerpoint";
  if (ext === "json") return "fa-file-code";
  if (ext === "zip") return "fa-file-zipper";
  if (IMAGE_EXTENSIONS.has(ext)) return "fa-file-image";
  return "fa-file-lines"; // .txt / .md
}

function isImageFile(filename) {
  const ext = String(filename || "").split(".").pop().toLowerCase();
  return IMAGE_EXTENSIONS.has(ext);
}

function formatFileSize(bytes) {
  if (!bytes && bytes !== 0) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function buildAttachmentCard(att) {
  const card = document.createElement("div");
  card.className = `attachment-card is-${att.status}`;

  const iconWrap = document.createElement("div");
  iconWrap.className = "attachment-file-icon";
  if (att.previewUrl) {
    iconWrap.innerHTML = `<img src="${att.previewUrl}" alt="" class="attachment-thumb" />`;
  } else if (att.status === "error") {
    iconWrap.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i>`;
  } else {
    iconWrap.innerHTML = `<i class="fa-solid ${getFileIconClass(att.file.name)}"></i>`;
  }
  card.appendChild(iconWrap);

  const info = document.createElement("div");
  info.className = "attachment-file-info";

  const name = document.createElement("span");
  name.className = "attachment-file-name";
  name.textContent = att.file.name;
  info.appendChild(name);

  const meta = document.createElement("span");
  meta.className = "attachment-file-meta";
  if (att.status === "uploading") {
    meta.textContent = `Uploading… ${att.progress}%`;
  } else if (att.status === "processing") {
    meta.textContent = att.statusText || "Processing…";
  } else if (att.status === "success") {
    meta.textContent = formatFileSize(att.file.size);
  } else if (att.status === "error") {
    meta.textContent = att.error || "Upload failed";
  } else {
    meta.textContent = formatFileSize(att.file.size);
  }
  info.appendChild(meta);

  card.appendChild(info);

  if (att.status === "uploading" || att.status === "processing") {
    const track = document.createElement("div");
    track.className = "attachment-progress-track";
    const bar = document.createElement("div");
    bar.className = "attachment-progress-bar";
    bar.style.width = `${att.status === "processing" ? 100 : att.progress}%`;
    track.appendChild(bar);
    card.appendChild(track);
  }

  const statusIcon = document.createElement("span");
  statusIcon.className = "attachment-status-icon";
  if (att.status === "success") statusIcon.innerHTML = `<i class="fa-solid fa-circle-check"></i>`;
  if (att.status === "error") statusIcon.innerHTML = `<i class="fa-solid fa-rotate-right"></i>`;
  if (statusIcon.innerHTML) card.appendChild(statusIcon);

  const removeBtn = document.createElement("button");
  removeBtn.type = "button";
  removeBtn.className = "attachment-remove-btn";
  removeBtn.innerHTML = `<i class="fa-solid fa-xmark"></i>`;
  removeBtn.disabled = att.status === "uploading" || att.status === "processing";
  removeBtn.onclick = () => removeAttachment(att.localId);
  card.appendChild(removeBtn);

  return card;
}

function renderAttachmentPreview() {
  attachmentPreview.innerHTML = "";

  if (!pendingAttachments.length) {
    attachmentPreview.classList.add("hidden");
    return;
  }

  attachmentPreview.classList.remove("hidden");
  pendingAttachments.forEach((att) => attachmentPreview.appendChild(buildAttachmentCard(att)));
}

function setUploadStatusLine(text) {
  if (!text) {
    uploadStatusLine.classList.add("hidden");
    uploadStatusLine.innerHTML = "";
    return;
  }
  uploadStatusLine.classList.remove("hidden");
  uploadStatusLine.innerHTML = `<span class="typing-dots"><span></span><span></span><span></span></span> ${escapeHtml(text)}`;
}

function addFiles(fileList) {
  Array.from(fileList || []).forEach((file) => {
    const att = {
      localId: ++attachmentSeq,
      file,
      status: "pending",
      progress: 0,
      documentId: null,
      error: null,
      previewUrl: isImageFile(file.name) ? URL.createObjectURL(file) : null,
    };
    pendingAttachments.push(att);
  });
  renderAttachmentPreview();
}

function removeAttachment(localId) {
  const att = pendingAttachments.find((a) => a.localId === localId);
  if (att && att.previewUrl) URL.revokeObjectURL(att.previewUrl);
  pendingAttachments = pendingAttachments.filter((a) => a.localId !== localId);
  renderAttachmentPreview();
}

function uploadFileWithProgress(file, conversationId, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/documents/upload");
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      let data = {};
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        // non-JSON error body, fall through with generic message below
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(data);
      } else {
        reject(new Error(data.detail || `Upload failed (HTTP ${xhr.status})`));
      }
    };
    xhr.onerror = () => reject(new Error("Network error during upload"));
    const formData = new FormData();
    formData.append("file", file);
    // Files attached from inside a chat are private to that conversation --
    // only the Knowledge Base modal (which omits this) shares a file everywhere.
    if (conversationId) formData.append("conversation_id", conversationId);
    xhr.send(formData);
  });
}

async function uploadAttachment(att) {
  att.status = "uploading";
  att.progress = 0;
  att.error = null;
  renderAttachmentPreview();

  try {
    const data = await uploadFileWithProgress(att.file, currentChatId, (pct) => {
      att.progress = pct;
      renderAttachmentPreview();
    });

    att.status = "processing";
    att.statusText = "Processing document…";
    renderAttachmentPreview();
    await new Promise((r) => setTimeout(r, 300));

    att.statusText = "Generating embeddings…";
    renderAttachmentPreview();
    await new Promise((r) => setTimeout(r, 300));

    att.documentId = data.id;
    att.status = "success";
  } catch (err) {
    att.status = "error";
    att.error = err.message || "Upload failed";
  }
  renderAttachmentPreview();
}

async function uploadPendingAttachments() {
  const toUpload = pendingAttachments.filter((a) => a.status !== "success");
  if (!toUpload.length) return;

  sendBtn.disabled = true;
  setUploadStatusLine("Uploading files...");
  await Promise.all(toUpload.map((att) => uploadAttachment(att)));

  const anyFailed = pendingAttachments.some((a) => a.status === "error");
  setUploadStatusLine(anyFailed ? "" : "Ready.");
  if (!anyFailed) {
    setTimeout(() => setUploadStatusLine(""), 600);
  }
  sendBtn.disabled = false;
}

function closeAttachMenu() {
  attachMenu.classList.add("hidden");
}

attachBtn.onclick = () => {
  attachMenu.classList.toggle("hidden");
};

attachMenuUpload.onclick = () => {
  closeAttachMenu();
  attachFileInput.click();
};

document.addEventListener("click", (e) => {
  if (!attachWrapper.contains(e.target)) closeAttachMenu();
});

attachFileInput.addEventListener("change", () => {
  addFiles(attachFileInput.files);
  attachFileInput.value = "";
});

// Drag and drop: dragging files anywhere over the chat window highlights a
// drop zone; dropping stages the files exactly like picking them manually.
let dragDepth = 0;

mainEl.addEventListener("dragenter", (e) => {
  if (!e.dataTransfer || !Array.from(e.dataTransfer.types || []).includes("Files")) return;
  e.preventDefault();
  dragDepth++;
  dropOverlay.classList.remove("hidden");
});

mainEl.addEventListener("dragover", (e) => {
  if (!e.dataTransfer || !Array.from(e.dataTransfer.types || []).includes("Files")) return;
  e.preventDefault();
});

mainEl.addEventListener("dragleave", (e) => {
  e.preventDefault();
  dragDepth = Math.max(0, dragDepth - 1);
  if (dragDepth === 0) dropOverlay.classList.add("hidden");
});

mainEl.addEventListener("drop", (e) => {
  e.preventDefault();
  dragDepth = 0;
  dropOverlay.classList.add("hidden");
  if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) {
    addFiles(e.dataTransfer.files);
  }
});

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();

  const text = messageInput.value.trim();
  if ((!text && !pendingAttachments.length) || isLoading) return;

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

  if (pendingAttachments.length) {
    await uploadPendingAttachments();
  }

  const attachmentsForTurn = pendingAttachments.map((att) => ({
    filename: att.file.name,
    status: att.status,
    error: att.error,
  }));
  const successfulAttachments = pendingAttachments.filter((a) => a.status === "success");

  if (!text) {
    // Files-only send: leave successfully uploaded files staged (already
    // associated with this chat's document pool) until the user actually
    // types something to ask about them; failed ones stay staged for retry.
    isLoading = false;
    renderAttachmentPreview();
    return;
  }

  const expectedMode = guessIntent(text);

  const turn = {
    user: text,
    assistant: "",
    mode: "chat",
    expectedMode: expectedMode,
    loading: true,
    sdlcData: null,
    sources: [],
    attachments: attachmentsForTurn,
  };

  turns.push(turn);
  messageInput.value = "";
  pendingAttachments.forEach((att) => {
    if (att.previewUrl) URL.revokeObjectURL(att.previewUrl);
  });
  pendingAttachments = [];
  renderAttachmentPreview();
  renderMessages();

  try {
    const res = await fetch(`/api/chat/${encodeURIComponent(currentChatId)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: text,
        attachment_filenames: successfulAttachments.map((a) => a.file.name),
        attachment_document_ids: successfulAttachments.map((a) => a.documentId),
      }),
    });

    const data = await res.json();
    const lastTurn = turns[turns.length - 1];

    if (!res.ok) {
      throw new Error(data.detail || `Request failed (HTTP ${res.status})`);
    }

    if (data.mode === "sdlc") {
      lastTurn.mode = "sdlc";
      lastTurn.sdlcData = data;
    } else {
      lastTurn.mode = "chat";
      lastTurn.assistant = data.reply || "";
      lastTurn.sources = data.sources || [];
    }

    await loadChats();
  } catch (err) {
    console.error(err);
    const lastTurn = turns[turns.length - 1];
    if (lastTurn) lastTurn.assistant = `Something went wrong during generation: ${err.message}`;
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
  closeSidebar();
};

function openSidebar() {
  sidebar.classList.add("is-open");
  sidebarBackdrop.classList.remove("hidden");
}

function closeSidebar() {
  sidebar.classList.remove("is-open");
  sidebarBackdrop.classList.add("hidden");
}

sidebarToggle.addEventListener("click", () => {
  if (sidebar.classList.contains("is-open")) {
    closeSidebar();
  } else {
    openSidebar();
  }
});

sidebarBackdrop.addEventListener("click", closeSidebar);

function wireSidebarProfileMenu() {
  if (!sidebarProfile || !profileMenu) return;
  sidebarProfile.onclick = (e) => {
    e.stopPropagation();
    profileMenu.classList.toggle("hidden");
  };
  document.addEventListener("click", (e) => {
    if (!sidebarProfile.contains(e.target) && !profileMenu.contains(e.target)) {
      profileMenu.classList.add("hidden");
    }
  });
}

async function initAuth() {
  wireSidebarProfileMenu();

  try {
    const res = await fetch("/api/auth-config");
    const config = await res.json();

    if (!config.clientId) {
      console.warn("No VITE_CLIENT_ID found. Running in local dev auth mode.");
      const userNameDisplay = document.getElementById("userNameDisplay");
      if (userNameDisplay) userNameDisplay.textContent = "Local User";
      if (profileAvatar) profileAvatar.textContent = "U";

      if (msLoginBtn) {
        msLoginBtn.onclick = () => showChatApp();
      }
      if (logoutBtn) {
        logoutBtn.onclick = () => {
          profileMenu.classList.add("hidden");
          showLoginPage();
        };
      }

      showLoginPage();
      return;
    }

    const msalConfig = {
      auth: {
        clientId: config.clientId,
        authority: `https://login.microsoftonline.com/${config.tenantId}`,
        redirectUri: window.location.origin
      },
      cache: {
        cacheLocation: "sessionStorage",
        storeAuthStateInCookie: false,
      }
    };
    
    msalInstance = new msal.PublicClientApplication(msalConfig);

    // Wire the login/logout buttons up front so they work regardless of
    // which branch below returns early (e.g. right after a login redirect).
    msLoginBtn.onclick = () => {
      // Use redirect instead of popup for a full-page experience
      msalInstance.loginRedirect({ scopes: ["user.read"] });
    };

    if (logoutBtn) {
      logoutBtn.onclick = () => {
        if (profileMenu) profileMenu.classList.add("hidden");
        const account = msalInstance.getAllAccounts()[0];
        msalInstance.logoutRedirect({
          account,
          postLogoutRedirectUri: window.location.origin
        });
      };
    }

    // Handle redirect response
    const response = await msalInstance.handleRedirectPromise();
    if (response) {
      // Successful login from redirect
      const userNameDisplay = document.getElementById("userNameDisplay");
      const displayStr = response.account.username || response.account.name;
      if (userNameDisplay) userNameDisplay.textContent = displayStr;
      if (profileAvatar) profileAvatar.textContent = getInitials(response.account.name || displayStr);

      showChatApp();
      return;
    }

    const accounts = msalInstance.getAllAccounts();
    if (accounts.length > 0) {
      const userNameDisplay = document.getElementById("userNameDisplay");
      const displayStr = accounts[0].username || accounts[0].name;
      if (userNameDisplay) userNameDisplay.textContent = displayStr;
      if (profileAvatar) profileAvatar.textContent = getInitials(accounts[0].name || displayStr);

      showChatApp();
    } else {
      showLoginPage();
    }
  } catch (err) {
    console.error("Failed to load auth config or login", err);
    showChatApp(); // Fallback if API fails
  }
}

async function showChatApp() {
  if (loginPage) loginPage.style.display = "none";
  if (chatApp) chatApp.style.display = "flex";
  
  await loadChats();

  const chatId = window.location.pathname.split("/")[2];
  if (chatId && chatId !== "new") {
    await openChat(chatId);
  } else {
    currentChatId = "new";
    turns = [];
    setUrlToNewChat();
    renderMessages();
    renderChatList();
  }
}

function showLoginPage() {
  if (loginPage) loginPage.style.display = "flex";
  if (chatApp) chatApp.style.display = "none";
  if (window.location.pathname !== "/login") {
    history.replaceState({ page: "login" }, "", "/login");
  }
}

window.onload = async () => {
  await initAuth();
};

window.addEventListener("popstate", async () => {
  const chatId = window.location.pathname.split("/")[2];
  if (chatId && chatId !== "new") {
    await openChat(chatId);
  }
});
