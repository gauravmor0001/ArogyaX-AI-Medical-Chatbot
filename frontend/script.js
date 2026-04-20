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
// Send message
async function sendMessage() {
  const input = document.getElementById('msgInput');
  const text = input.value.trim();

  if (!text) return;

  // Show user message on screen
  appendMsg('user', text);
  input.value = '';

  // Show a temporary "Bot is thinking..." message (optional but good UX)
  const typingId = 'typing-' + Date.now();
  appendMsg('bot', '<div class="typing-indicator"><span></span><span></span><span></span></div>');
  
  try {
    // 1. Point exactly to your local FastAPI server
    const response = await fetch('http://localhost:8000/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text })
    });

    const data = await response.json();
    
    // Remove the typing indicator (by removing the last added message)
    const msgs = document.getElementById('messages');
    msgs.lastChild.remove();

    // 2. Format the bot's reply and the sources
    let finalHtml = data.reply;
    
    // If the backend sent sources, format them nicely at the bottom of the bubble
    if (data.sources && data.sources.length > 0) {
        finalHtml += "<br><br><b>📚 Sources:</b><ul>";
        data.sources.forEach(source => {
            finalHtml += `<li><span class="tag">${source}</span></li>`;
        });
        finalHtml += "</ul>";
    }

    // Append the final formatted answer to the chat UI
    appendMsg('bot', finalHtml);

  } catch (error) {
    console.error("Backend Error:", error);
    const msgs = document.getElementById('messages');
    msgs.lastChild.remove(); // Remove typing indicator
    appendMsg('bot', "⚠️ Cannot connect to the Arogya Server. Please ensure Python is running.");
  }
}