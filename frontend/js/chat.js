// Chat State
let chatHistory = [];
const THINKING_STAGES = [
  'Scanning live event memory...',
  'Pulling market and geopolitical context...',
  'Cross-checking recent signals...',
  'Composing strategic answer...'
];

const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');
const messagesContainer = document.getElementById('chat-messages');
let analystHistoryLoaded = false;
let analystHistoryKey = null;
const defaultAnalystMarkup = messagesContainer ? messagesContainer.innerHTML : '';

sendBtn.addEventListener('click', sendMessage);
chatInput.addEventListener('keypress', (e) => {
  if (e.key === 'Enter') sendMessage();
});

// Setup Quick Queries
document.querySelectorAll('.qq-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    chatInput.value = btn.dataset.q;
    sendMessage();
  });
});

async function sendMessage() {
  const text = chatInput.value.trim();
  if (!text) return;

  // Add user message to UI
  appendMessage('user', text);
  chatInput.value = '';
  chatInput.disabled = true;
  sendBtn.disabled = true;

  // Add thinking indicator
  const thinkingId = 'msg-' + Date.now();
  appendThinking(thinkingId);

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: (typeof getAuthHeaders === 'function') ? getAuthHeaders() : { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: text,
        history: chatHistory
      })
    });
    const raw = await res.text();
    let data = {};
    if (raw) {
      try {
        data = JSON.parse(raw);
      } catch (_err) {
        throw new Error(raw.slice(0, 300));
      }
    }
    
    // Remove thinking
    removeThinking(thinkingId);

    if (!res.ok) {
      throw new Error(data.detail || data.error || raw || `Request failed with status ${res.status}`);
    }

    if (data.response) {
      appendMessage('sentinel', data.response);
      
      // Update history
      chatHistory.push({ role: 'user', content: text });
      chatHistory.push({ role: 'assistant', content: data.response });
      
      // Keep history manageable
      if (chatHistory.length > 20) chatHistory = chatHistory.slice(-20);
    } else {
      appendMessage('sentinel', '⚠️ Null response received from intelligence feed.');
    }

  } catch (err) {
    removeThinking(thinkingId);
    appendMessage('sentinel', '⚠️ Comm-link failure: ' + err.message);
  } finally {
    chatInput.disabled = false;
    sendBtn.disabled = false;
    chatInput.focus();
  }
}

function appendMessage(role, text) {
  const div = document.createElement('div');
  div.className = role === 'user' ? 'msg-user' : 'msg-sentinel';
  
  const avatar = role === 'user' ? 'U' : 'S';
  
  // Basic markdown-like parsing for bold and line breaks
  const formattedText = text
    .replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>')
    .replace(/\\n/g, '<br>');

  div.innerHTML = `
    <div class="msg-avatar">${avatar}</div>
    <div class="msg-bubble">${formattedText}</div>
  `;
  
  messagesContainer.appendChild(div);
  scrollToBottom();
}

function appendThinking(id) {
  const div = document.createElement('div');
  div.className = 'msg-sentinel msg-thinking';
  div.id = id;
  
  div.innerHTML = `
    <div class="msg-avatar">S</div>
    <div class="msg-bubble">
      <div class="thinking-label">SENTINEL is working</div>
      <div class="thinking-stage">Scanning live event memory...</div>
    </div>
  `;
  
  messagesContainer.appendChild(div);
  scrollToBottom();
  const stageNode = div.querySelector('.thinking-stage');
  let index = 0;
  const timer = setInterval(() => {
    if (!document.body.contains(div)) {
      clearInterval(timer);
      return;
    }
    index = (index + 1) % THINKING_STAGES.length;
    if (stageNode) stageNode.textContent = THINKING_STAGES[index];
  }, 1200);
  div.dataset.timerId = String(timer);
}

function removeThinking(id) {
  const node = document.getElementById(id);
  if (!node) return;
  if (node.dataset.timerId) {
    clearInterval(Number(node.dataset.timerId));
  }
  node.remove();
}

function scrollToBottom() {
  messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

async function loadAnalystHistory() {
  if (!messagesContainer) return;
  const token = (typeof localStorage !== 'undefined') ? localStorage.getItem('sentinel_token') : null;
  if (!token) {
    analystHistoryLoaded = false;
    analystHistoryKey = null;
    return;
  }
  const nextKey = token.slice(-16);
  if (analystHistoryLoaded && analystHistoryKey === nextKey) return;
  analystHistoryLoaded = true;
  analystHistoryKey = nextKey;
  try {
    const headers = (typeof getAuthHeaders === 'function') ? getAuthHeaders() : { 'Content-Type': 'application/json' };
    const res = await fetch('/api/chat/history?scope=analyst', { headers });
    const raw = await res.text();
    if (!raw) return;
    const data = JSON.parse(raw);
    const messages = data.messages || [];
    if (!messages.length) return;
    messagesContainer.innerHTML = '';
    chatHistory = [];
    messages.forEach((msg) => {
      appendMessage(msg.role === 'assistant' ? 'sentinel' : 'user', msg.content);
      chatHistory.push({ role: msg.role, content: msg.content });
    });
  } catch (_err) {
    analystHistoryLoaded = false;
  }
}

function resetAnalystHistoryState() {
  analystHistoryLoaded = false;
  analystHistoryKey = null;
  chatHistory = [];
  if (messagesContainer) {
    messagesContainer.innerHTML = defaultAnalystMarkup;
  }
}

window.loadAnalystHistory = loadAnalystHistory;
window.resetAnalystHistoryState = resetAnalystHistoryState;
loadAnalystHistory();
