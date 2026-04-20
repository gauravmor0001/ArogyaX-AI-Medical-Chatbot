const SYSTEM_PROMPT = `You are Arogya, a compassionate AI medical assistant...`;

let pendingImage = null;
let attachedImage = null;
let attachedFile = null;
let conversationHistory = [];
let isTyping = false;

// Modal
function openModal() {
  document.getElementById('uploadModal').classList.add('open');
}

function closeModal() {
  document.getElementById('uploadModal').classList.remove('open');
}

// Auto resize
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

function getTime() {
  return new Date().toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit'
  });
}

// Append message
function appendMsg(role, text) {
  const msgs = document.getElementById('messages');
  const div = document.createElement('div');
  div.className = `msg ${role}`;
  div.innerHTML = `<div class="bubble">${text}</div>`;
  msgs.appendChild(div);
}

// Send message
async function sendMessage() {
  const input = document.getElementById('msgInput');
  const text = input.value.trim();

  if (!text) return;

  appendMsg('user', text);
  input.value = '';

  try {
    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: 'claude-sonnet-4',
        messages: [{ role: 'user', content: text }]
      })
    });

    const data = await response.json();
    appendMsg('bot', data?.content || "Error");

  } catch {
    appendMsg('bot', "Connection error");
  }
}