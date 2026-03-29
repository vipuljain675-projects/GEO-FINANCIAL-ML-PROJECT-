// Chat State
let chatHistory = [];

const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');
const messagesContainer = document.getElementById('chat-messages');

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
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: text,
        history: chatHistory
      })
    });

    const data = await res.json();
    
    // Remove thinking
    document.getElementById(thinkingId).remove();

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
    document.getElementById(thinkingId).remove();
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
    <div class="msg-bubble">Analyzing strategic parameters...</div>
  `;
  
  messagesContainer.appendChild(div);
  scrollToBottom();
}

function scrollToBottom() {
  messagesContainer.scrollTop = messagesContainer.scrollHeight;
}
