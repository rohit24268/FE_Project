const API_URL = 'http://localhost:8000';
const RECENT_INVESTIGATIONS_KEY = 'forensight-recent-investigations';

const chatMessages = document.getElementById('chatMessages');
const chatForm = document.getElementById('chatForm');
const chatInput = document.getElementById('chatInput');
const chatSendBtn = document.getElementById('chatSendBtn');
const chatStatusPill = document.getElementById('chatStatusPill');
const chatQuickPrompts = document.getElementById('chatQuickPrompts');
const aiAnalysisIdInput = document.getElementById('aiAnalysisIdInput');
const aiQuickLinksChips = document.getElementById('aiQuickLinksChips');
const activeSessionBadge = document.getElementById('activeSessionBadge');

let currentAnalysisId = null;
let chatHistory = [];

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    "'": '&#39;',
    '"': '&quot;'
  }[character]));
}

function getRecentInvestigations() {
  try {
    return JSON.parse(localStorage.getItem(RECENT_INVESTIGATIONS_KEY) || '[]');
  } catch (error) {
    return [];
  }
}

function renderQuickLinks() {
  if (!aiQuickLinksChips) return;
  const recent = getRecentInvestigations();

  if (!recent.length) {
    aiQuickLinksChips.innerHTML = '<span style="color:var(--muted)">No analysis sessions completed yet. Run a Video Analysis on Dashboard first.</span>';
    return;
  }

  aiQuickLinksChips.innerHTML = recent.map((item) => `
    <button type="button" class="analysis-quick-link" data-analysis-id="${item.id}">
      #${item.id.slice(0, 8)} (${escapeHtml(item.fileName)})
    </button>
  `).join(' ');
}

function setAnalysisSession(id) {
  currentAnalysisId = id;
  chatHistory = [];
  if (aiAnalysisIdInput) aiAnalysisIdInput.value = id;
  if (activeSessionBadge) activeSessionBadge.textContent = `#${id.slice(0, 8)}`;

  if (chatMessages) {
    chatMessages.innerHTML = `
      <div class="chat-bubble model">
        <p>AI Forensic Investigation session active for Analysis <code>#${id.slice(0, 8)}</code>.</p>
        <p>Ask me anything about detected weapons, timeline reconstruction, armed suspect trajectories, or generating dispatch reports.</p>
      </div>
    `;
  }
}

document.addEventListener('click', (e) => {
  const chip = e.target.closest('.analysis-quick-link');
  if (chip && chip.dataset.analysisId) {
    setAnalysisSession(chip.dataset.analysisId);
  }
});

const loadAnalysisAiBtn = document.getElementById('loadAnalysisAiBtn');
if (loadAnalysisAiBtn) {
  loadAnalysisAiBtn.addEventListener('click', () => {
    const val = aiAnalysisIdInput ? aiAnalysisIdInput.value.trim() : '';
    if (val) setAnalysisSession(val);
  });
}

function appendChatMessage(role, text, isLoading = false) {
  if (!chatMessages) return null;

  const bubble = document.createElement('div');
  bubble.className = `chat-bubble ${role}${isLoading ? ' loading' : ''}`;
  bubble.innerHTML = isLoading
    ? '<div class="typing-indicator"><span></span><span></span><span></span></div>'
    : `<p>${escapeHtml(text).replace(/\n/g, '<br/>')}</p>`;

  chatMessages.appendChild(bubble);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return bubble;
}

async function handleChatSubmit(question) {
  const trimmed = (question || '').trim();
  if (!trimmed) return;

  if (!currentAnalysisId) {
    appendChatMessage('model', 'Please select or enter an Analysis Session ID above before asking questions.');
    return;
  }

  appendChatMessage('user', trimmed);
  if (chatInput) chatInput.value = '';

  const loadingBubble = appendChatMessage('model', '', true);
  if (chatSendBtn) chatSendBtn.disabled = true;
  if (chatStatusPill) {
    chatStatusPill.textContent = 'Analyzing...';
    chatStatusPill.className = 'status-pill processing';
  }

  try {
    const response = await fetch(`${API_URL}/investigate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        analysis_id: currentAnalysisId,
        question: trimmed,
        history: chatHistory
      })
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || 'Investigation assistant error');
    }

    const answer = data.answer || 'No response provided.';
    loadingBubble.classList.remove('loading');
    loadingBubble.innerHTML = `<p>${escapeHtml(answer).replace(/\n/g, '<br/>')}</p>`;

    chatHistory.push({ role: 'user', content: trimmed });
    chatHistory.push({ role: 'assistant', content: answer });

    if (chatStatusPill) {
      chatStatusPill.textContent = 'Ready';
      chatStatusPill.className = 'status-pill ok';
    }
  } catch (error) {
    loadingBubble.classList.remove('loading');
    loadingBubble.classList.add('error');
    loadingBubble.innerHTML = `<p>Error: ${escapeHtml(error.message)}</p>`;
    if (chatStatusPill) {
      chatStatusPill.textContent = 'Error';
      chatStatusPill.className = 'status-pill';
    }
  } finally {
    if (chatSendBtn) chatSendBtn.disabled = false;
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }
}

if (chatForm) {
  chatForm.addEventListener('submit', (e) => {
    e.preventDefault();
    if (chatInput) handleChatSubmit(chatInput.value);
  });
}

if (chatQuickPrompts) {
  chatQuickPrompts.addEventListener('click', (e) => {
    const chip = e.target.closest('.prompt-chip');
    if (chip && chip.dataset.prompt) {
      handleChatSubmit(chip.dataset.prompt);
    }
  });
}

// Initial load
renderQuickLinks();
const recent = getRecentInvestigations();
if (recent.length) {
  setAnalysisSession(recent[0].id);
}
