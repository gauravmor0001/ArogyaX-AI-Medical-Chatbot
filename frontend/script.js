// ─────────────────────────────────────────────
// STATE
// ─────────────────────────────────────────────
let pendingImage   = null;   // image in modal, not yet attached
let attachedImage  = null;   // image attached to current message
let isTyping       = false;
let chatStarted    = false;  // whether welcome screen should hide

// Report mode state
let reportMode     = false;  // are we in report-chat mode?
let reportFile     = null;   // the actual File object
let sessionId      = generateSessionId();

const API_BASE = 'http://localhost:8000';

// ─────────────────────────────────────────────
// HELPERS
// ─────────────────────────────────────────────
function generateSessionId() {
  return 'sess_' + Math.random().toString(36).slice(2, 11);
}

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 140) + 'px';
}

function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

function scrollToBottom() {
  const wrap = document.getElementById('chatWrap');
  wrap.scrollTop = wrap.scrollHeight;
}

// ─────────────────────────────────────────────
// WELCOME → CHAT TRANSITION
// ─────────────────────────────────────────────
function hideWelcome() {
  if (!chatStarted) {
    chatStarted = true;
    const ws = document.getElementById('welcomeScreen');
    ws.style.transition = 'opacity 0.3s ease';
    ws.style.opacity = '0';
    setTimeout(() => ws.classList.add('hidden'), 300);
  }
}

// ─────────────────────────────────────────────
// MODE SELECTION (from welcome screen cards)
// ─────────────────────────────────────────────
function selectMode(mode) {
  if (mode === 'chat') {
    // Just go straight to chat
    hideWelcome();
    document.getElementById('msgInput').focus();

  } else if (mode === 'report') {
    // Open the report upload panel
    openReportPanel();
  }
}

// Quick chip — shortcut to chat mode
function sendChip(text) {
  hideWelcome();
  document.getElementById('msgInput').value = text;
  sendMessage();
}

// ─────────────────────────────────────────────
// REPORT PANEL
// ─────────────────────────────────────────────
function openReportPanel() {
  document.getElementById('reportPanel').classList.add('open');
}

function closeReportPanel() {
  document.getElementById('reportPanel').classList.remove('open');
}

function cancelReportMode() {
  closeReportPanel();
  clearReportFile();
}

function reportFileSelected(input) {
  const file = input.files[0];
  if (!file) return;
  reportFile = file;

  // Show chip in panel
  const chip = document.getElementById('reportFileChip');
  document.getElementById('reportFileName').textContent = file.name;
  chip.classList.add('visible');

  // Enable start button
  document.getElementById('btnStartReport').classList.add('ready');
}

function clearReportFile() {
  reportFile = null;
  document.getElementById('reportFileChip').classList.remove('visible');
  document.getElementById('btnStartReport').classList.remove('ready');
  document.getElementById('reportFileInput').value = '';
}

async function startReportChat() {
  if (!reportFile) return;

  const btn = document.getElementById('btnStartReport');
  btn.textContent = 'Uploading…';
  btn.classList.remove('ready');

  try {
    const formData = new FormData();
    formData.append('session_id', sessionId);

    // Route file to correct field based on type
    if (reportFile.type === 'application/pdf') {
      formData.append('pdf_file', reportFile);
    } else {
      formData.append('image_files', reportFile);
    }

    const res = await fetch(`${API_BASE}/report/upload`, {
      method: 'POST',
      body: formData,
    });

    const data = await res.json();

    // Close panel & enter report mode
    closeReportPanel();
    enterReportMode(reportFile.name, data);

  } catch (err) {
    console.error('Upload failed:', err);
    btn.textContent = 'Upload failed — retry';
    btn.classList.add('ready');
  }
}

function enterReportMode(fileName, uploadResult) {
  reportMode = true;

  // Hide welcome, show chat
  hideWelcome();

  // Show mode pill in header
  document.getElementById('headerMode').innerHTML = `
    <div class="mode-pill">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
        <polyline points="14 2 14 8 20 8"/>
      </svg>
      Report Mode
    </div>`;

  // Show context pill in input area
  const pill = document.getElementById('reportContextPill');
  document.getElementById('reportPillName').textContent = fileName;
  pill.classList.add('active');

  // Show input placeholder
  document.getElementById('msgInput').placeholder = 'Ask about this report…';

  // Greet with a bot message
  let greeting = `📋 <b>Report loaded:</b> ${fileName}<br><br>`;
  if (uploadResult.extracted_findings && uploadResult.extracted_findings.length > 0) {
    greeting += `<b>Image findings detected:</b><br>`;
    uploadResult.extracted_findings.forEach(f => {
      greeting += `• ${f}<br>`;
    });
    greeting += `<br>`;
  }
  if (uploadResult.pdf_text_preview) {
    greeting += `<b>PDF preview:</b> "${uploadResult.pdf_text_preview.slice(0, 120)}…"<br><br>`;
  }
  greeting += `You can now ask me to <b>summarize this report</b>, explain findings, or ask any specific question. I'll also draw from my medical textbook knowledge.`;

  appendMsg('bot', greeting);
  scrollToBottom();

  document.getElementById('msgInput').focus();
}

function exitReportMode() {
  reportMode = false;
  reportFile = null;
  sessionId  = generateSessionId(); // fresh session

  document.getElementById('headerMode').innerHTML = '';
  document.getElementById('reportContextPill').classList.remove('active');
  document.getElementById('msgInput').placeholder = 'Ask a health question…';

  appendMsg('bot', 'Report removed. You\'re back in regular chat mode. Ask me any medical question!');
  scrollToBottom();
}

// ─────────────────────────────────────────────
// IMAGE MODAL
// ─────────────────────────────────────────────
function openModal() {
  document.getElementById('uploadModal').classList.add('open');
}

function closeModal() {
  document.getElementById('uploadModal').classList.remove('open');
  pendingImage = null;
  document.getElementById('modalPreview').classList.remove('visible');
  document.getElementById('modalPreview').src = '';
  document.getElementById('attachBtn').classList.remove('ready');
  document.getElementById('modalFileInput').value = '';
}

function previewModal(input) {
  const file = input.files[0];
  if (!file) return;
  pendingImage = file;
  const reader = new FileReader();
  reader.onload = e => {
    const preview = document.getElementById('modalPreview');
    preview.src = e.target.result;
    preview.classList.add('visible');
    document.getElementById('attachBtn').classList.add('ready');
  };
  reader.readAsDataURL(file);
}

function attachImage() {
  if (!pendingImage) return;
  attachedImage = pendingImage;

  // Show in preview strip
  const strip = document.getElementById('previewStrip');
  const item  = document.createElement('div');
  item.className = 'preview-item';
  item.innerHTML = `
    <img src="${URL.createObjectURL(attachedImage)}" alt="attached"/>
    <button class="remove-img" onclick="removeAttachedImage()">✕</button>`;
  strip.innerHTML = '';
  strip.appendChild(item);
  strip.classList.add('visible');

  closeModal();
}

function removeAttachedImage() {
  attachedImage = null;
  const strip = document.getElementById('previewStrip');
  strip.innerHTML = '';
  strip.classList.remove('visible');
}

// ─────────────────────────────────────────────
// APPEND MESSAGE
// ─────────────────────────────────────────────
function appendMsg(role, html, imageUrl) {
  const msgs    = document.getElementById('messages');
  const wrapper = document.createElement('div');
  wrapper.className = `msg ${role}`;

  const avatarLabel = role === 'bot' ? 'A' : 'U';
  const avatarClass = role === 'bot' ? 'bot' : 'user-av';

  let imgHtml = '';
  if (imageUrl) {
    imgHtml = `<img src="${imageUrl}" alt="attached image"/><div class="img-caption">Attached image</div>`;
  }

  wrapper.innerHTML = `
    <div class="avatar ${avatarClass}">${avatarLabel}</div>
    <div class="bubble">${imgHtml}${html}</div>`;

  msgs.appendChild(wrapper);
  scrollToBottom();
  return wrapper;
}

function appendTyping() {
  return appendMsg('bot', '<div class="typing-indicator"><span></span><span></span><span></span></div>');
}

// ─────────────────────────────────────────────
// SEND MESSAGE
// ─────────────────────────────────────────────
async function sendMessage() {
  if (isTyping) return;

  const input = document.getElementById('msgInput');
  const text  = input.value.trim();
  if (!text) return;

  // Hide welcome if still visible
  hideWelcome();

  // Show user message
  const imageUrl = attachedImage ? URL.createObjectURL(attachedImage) : null;
  appendMsg('user', text, imageUrl);
  input.value = '';
  input.style.height = 'auto';

  // Clear attached image
  const hadImage = !!attachedImage;
  removeAttachedImage();

  isTyping = true;
  const typingEl = appendTyping();

  try {
    let reply, sources;

    if (reportMode) {
      // ── Report + Books RAG ──
      const res = await fetch(`${API_BASE}/report/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, message: text }),
      });
      const data = await res.json();
      reply   = data.reply;
      sources = data.sources || [];

    } else {
      // ── Regular books RAG (existing bot.py) ──
      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
      });
      const data = await res.json();
      reply   = data.reply;
      sources = data.sources || [];
    }

    // Remove typing indicator
    typingEl.remove();

    // Format reply
    let finalHtml = reply;
    if (sources && sources.length > 0) {
      finalHtml += `<br><br><b>Sources:</b><br>`;
      sources.forEach(s => {
        finalHtml += `<span class="tag">${s}</span> `;
      });
    }

    appendMsg('bot', finalHtml);

  } catch (err) {
    console.error('Error:', err);
    typingEl.remove();
    appendMsg('bot', '⚠️ Cannot connect to the ArogyaX server. Please make sure Python is running.');
  }

  isTyping = false;
}

// ─────────────────────────────────────────────
// DRAG & DROP for report panel
// ─────────────────────────────────────────────
const dropZone = document.getElementById('reportDropZone');
if (dropZone) {
  dropZone.addEventListener('dragover', e => {
    e.preventDefault();
    dropZone.classList.add('drag-over');
  });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
  dropZone.addEventListener('drop', e => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (file) {
      reportFile = file;
      document.getElementById('reportFileName').textContent = file.name;
      document.getElementById('reportFileChip').classList.add('visible');
      document.getElementById('btnStartReport').classList.add('ready');
    }
  });
}

// Close report panel on overlay click
document.getElementById('reportPanel').addEventListener('click', function(e) {
  if (e.target === this) cancelReportMode();
});

// Close image modal on overlay click
document.getElementById('uploadModal').addEventListener('click', function(e) {
  if (e.target === this) closeModal();
});