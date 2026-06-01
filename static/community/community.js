const communityUser = (() => {
  try {
    return JSON.parse(document.body.dataset.communityUser || "null");
  } catch {
    return null;
  }
})();

const participantRole = communityUser?.account_type === "B2B" || communityUser?.role === "distributor"
  ? "Distributor"
  : "User";

const authorName = communityUser?.name || communityUser?.email || "Guest Builder";

const state = {
  signals: [
    {
      id: crypto.randomUUID(),
      type: "Part Available",
      title: "ESP32-WROOM restock spotted",
      details: "Distributor update: 74 units available for same-day dispatch. Good fit for IoT gateways and BLE sensor nodes.",
      author: "Microchip Cart Distributor",
      role: "Distributor",
      replies: 3
    },
    {
      id: crypto.randomUUID(),
      type: "Need Eyes",
      title: "Buck converter heating on 12V input",
      details: "Using MP1584 module at 1.2A load. Looking for layout or heatsink suggestions before I swap the board.",
      author: "Rohan",
      role: "User",
      replies: 5
    },
    {
      id: crypto.randomUUID(),
      type: "Recommendation",
      title: "STM32F407 for motor control lab",
      details: "Enough timers, ADC channels, and headroom for a student BLDC controller. Pair with isolated gate drivers.",
      author: "Neha",
      role: "User",
      replies: 2
    }
  ],
  chat: [
    { author: "Aarav", role: "User", message: "Anyone used ATmega328P-PU for a low-power sensor logger?", time: "09:40" },
    { author: "Verified Distributor", role: "Distributor", message: "Yes. We recommend checking sleep current and using an external 32 kHz crystal if timing matters.", time: "09:42" }
  ],
  projects: [
    {
      id: crypto.randomUUID(),
      tag: "IoT",
      title: "Cold-chain temperature logger",
      details: "ESP32, DS18B20, Li-ion charger, and a tiny dashboard for delivery monitoring.",
      likes: 18,
      liked: false
    },
    {
      id: crypto.randomUUID(),
      tag: "Automation",
      title: "Pick-and-place nozzle controller",
      details: "STM32 board driving TMC2209 steppers with vacuum feedback.",
      likes: 24,
      liked: false
    },
    {
      id: crypto.randomUUID(),
      tag: "Repair",
      title: "Connector identification board",
      details: "Community-sourced part matches for JST-GH, SH, and odd 1.25 mm headers.",
      likes: 11,
      liked: false
    }
  ]
};

const els = {
  form: document.querySelector("#sendSignalForm"),
  author: document.querySelector("#signalAuthor"),
  type: document.querySelector("#signalType"),
  title: document.querySelector("#signalTitle"),
  details: document.querySelector("#signalDetails"),
  previewType: document.querySelector("#previewType"),
  previewRole: document.querySelector("#previewRole"),
  previewTitle: document.querySelector("#previewTitle"),
  previewDetails: document.querySelector("#previewDetails"),
  previewAuthor: document.querySelector("#previewAuthor"),
  feed: document.querySelector("#signalFeed"),
  chat: document.querySelector("#liveChatMessages"),
  chatForm: document.querySelector("#liveChatForm"),
  projects: document.querySelector("#projectShowcase"),
  toast: document.querySelector("#communityToast")
};

function escapeHtml(value) {
  return String(value || "").replace(/[&<>"']/g, char => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#39;"
  }[char]));
}

function toast(message) {
  if (!els.toast) return;
  els.toast.textContent = message;
  els.toast.classList.add("show");
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => els.toast.classList.remove("show"), 2200);
}

function roleLabel(role) {
  return role === "Distributor" ? "Distributor" : "User";
}

function renderSignals() {
  if (!els.feed) return;
  els.feed.innerHTML = state.signals.map(signal => `
    <article class="signal-card" data-signal-id="${signal.id}">
      <div class="signal-card-top">
        <span class="signal-type">${escapeHtml(signal.type)}</span>
        <small>${escapeHtml(roleLabel(signal.role))}</small>
      </div>
      <h3>${escapeHtml(signal.title)}</h3>
      <p>${escapeHtml(signal.details)}</p>
      <footer>
        <span>${escapeHtml(signal.author)}</span>
        <span>${signal.replies} replies</span>
      </footer>
    </article>
  `).join("");
}

function renderChat() {
  if (!els.chat) return;
  els.chat.innerHTML = state.chat.map(item => `
    <article class="chat-message">
      <header>
        <strong>${escapeHtml(item.author)}</strong>
        <span class="chat-role">${escapeHtml(roleLabel(item.role))}</span>
        <time>${escapeHtml(item.time)}</time>
      </header>
      <p>${escapeHtml(item.message)}</p>
    </article>
  `).join("");
  els.chat.scrollTop = els.chat.scrollHeight;
}

function renderProjects() {
  if (!els.projects) return;
  els.projects.innerHTML = state.projects.map(project => `
    <article class="project-card" data-project-id="${project.id}">
      <span class="project-tag">${escapeHtml(project.tag)}</span>
      <h3>${escapeHtml(project.title)}</h3>
      <p>${escapeHtml(project.details)}</p>
      <footer>
        <span>${project.likes} likes</span>
        <button type="button" data-like-project="${project.id}">${project.liked ? "Liked" : "Like project"}</button>
      </footer>
    </article>
  `).join("");
}

function updatePreview() {
  const title = els.title?.value.trim();
  const details = els.details?.value.trim();
  const type = els.type?.value || "Need Eyes";
  const author = els.author?.value.trim() || authorName;

  els.previewType.textContent = type;
  els.previewRole.textContent = `${participantRole} preview`;
  els.previewTitle.textContent = title || "Your signal preview";
  els.previewDetails.textContent = details || "Start typing and this preview will update before posting.";
  els.previewAuthor.textContent = author;
}

function bindEvents() {
  if (els.author) {
    els.author.value = authorName;
  }
  updatePreview();

  els.form?.addEventListener("input", updatePreview);
  els.form?.addEventListener("change", updatePreview);
  els.form?.addEventListener("submit", event => {
    event.preventDefault();
    const formData = new FormData(els.form);
    const signal = {
      id: crypto.randomUUID(),
      type: String(formData.get("type") || "Need Eyes"),
      title: String(formData.get("title") || "").trim(),
      details: String(formData.get("details") || "").trim(),
      author: String(formData.get("author") || authorName).trim(),
      role: participantRole,
      replies: 0
    };

    if (!signal.title || !signal.details) {
      toast("Add a title and details first.");
      return;
    }

    state.signals.unshift(signal);
    els.form.reset();
    if (els.author) els.author.value = authorName;
    updatePreview();
    renderSignals();
    toast("Signal posted locally.");
  });

  els.chatForm?.addEventListener("submit", event => {
    event.preventDefault();
    const input = els.chatForm.elements.message;
    const message = input.value.trim();
    if (!message) return;
    state.chat.push({
      author: authorName,
      role: participantRole,
      message,
      time: new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })
    });
    input.value = "";
    renderChat();
    toast("Chat message added locally.");
  });

  els.projects?.addEventListener("click", event => {
    const button = event.target.closest("[data-like-project]");
    if (!button) return;
    const project = state.projects.find(item => item.id === button.dataset.likeProject);
    if (!project) return;
    project.liked = !project.liked;
    project.likes += project.liked ? 1 : -1;
    renderProjects();
  });
}

function initCommunityHub() {
  document.body.dataset.theme = localStorage.getItem("mc_theme") || "dark";
  renderSignals();
  renderChat();
  renderProjects();
  bindEvents();
  if (window.lucide) window.lucide.createIcons();
}

initCommunityHub();
