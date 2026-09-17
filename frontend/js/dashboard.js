const API_URL = 'http://localhost:8000';

const videoInput = document.getElementById('videoInput');
const fileName = document.getElementById('fileName');
const analyzeBtn = document.getElementById('analyzeBtn');
const browseBtn = document.getElementById('browseBtn');
const statusPill = document.getElementById('statusPill');
const queueValue = document.getElementById('queueValue');
const analysisResults = document.getElementById('analysisResults');
const totalDetections = document.getElementById('totalDetections');
const objectCounts = document.getElementById('objectCounts');
const detectionsTable = document.getElementById('detectionsTable');
const resultNote = document.getElementById('resultNote');
const detectionsLink = document.getElementById('detectionsLink');
const annotatedVideoLink = document.getElementById('annotatedVideoLink');
const videoPreview = document.getElementById('videoPreview');
const annotatedVideo = document.getElementById('annotatedVideo');
const downloadVideoLink = document.getElementById('downloadVideoLink');
const recentInvestigationsList = document.getElementById('recentInvestigationsList');

// Threat UI Elements
const threatBanner = document.getElementById('threatBanner');
const threatLevelPill = document.getElementById('threatLevelPill');
const threatScoreValue = document.getElementById('threatScoreValue');
const threatIncidentsCount = document.getElementById('threatIncidentsCount');
const statThreatLevel = document.getElementById('statThreatLevel');
const statThreatIncidents = document.getElementById('statThreatIncidents');
const incidentsList = document.getElementById('incidentsList');
const threatsJsonLink = document.getElementById('threatsJsonLink');

// Chat UI Elements
const chatMessages = document.getElementById('chatMessages');
const chatForm = document.getElementById('chatForm');
const chatInput = document.getElementById('chatInput');
const chatSendBtn = document.getElementById('chatSendBtn');
const chatStatusPill = document.getElementById('chatStatusPill');
const chatQuickPrompts = document.getElementById('chatQuickPrompts');

const RECENT_INVESTIGATIONS_KEY = 'forensight-recent-investigations';
let annotatedVideoURL = '';
let currentAnalysisId = null;
let chatHistory = [];

// --------------------------------------------------
// RECENT INVESTIGATIONS HISTORY
// --------------------------------------------------

function getRecentInvestigations() {
  try {
    return JSON.parse(localStorage.getItem(RECENT_INVESTIGATIONS_KEY) || '[]');
  } catch (error) {
    return [];
  }
}

function saveRecentInvestigation(file, payload) {
  const recent = getRecentInvestigations();
  const threatAnalysis = payload.threat_analysis || {};
  const investigation = {
    id: payload.analysis_id,
    fileName: file.name,
    createdAt: new Date().toISOString(),
    totalDetections: payload.total_detections ?? (payload.detections || []).length,
    objectCounts: payload.object_counts || {},
    annotatedVideo: payload.annotated_video,
    detectionsFile: payload.detections_file,
    threatsFile: payload.threats_file,
    threatLevel: threatAnalysis.overall_threat_level || 'SAFE',
    threatScore: threatAnalysis.max_threat_score || 0,
  };

  const updated = [investigation, ...recent.filter((item) => item.id !== investigation.id)].slice(0, 5);
  localStorage.setItem(RECENT_INVESTIGATIONS_KEY, JSON.stringify(updated));
  renderRecentInvestigations();
}

function renderRecentInvestigations() {
  if (!recentInvestigationsList) return;
  const recent = getRecentInvestigations();

  if (!recent.length) {
    recentInvestigationsList.innerHTML = '<p class="empty-state">Completed investigations will appear here.</p>';
    return;
  }

  recentInvestigationsList.innerHTML = recent.map((item) => {
    const videoURL = item.annotatedVideo ? new URL(item.annotatedVideo, API_URL).href : '';
    const videoFile = item.annotatedVideo ? item.annotatedVideo.split('/').pop() : '';
    const objectNames = Object.keys(item.objectCounts || {}).join(', ') || 'No objects detected';
    const levelClass = (item.threatLevel || 'safe').toLowerCase();

    return `
      <article class="recent-item">
        <div class="recent-item-main">
          <div class="recent-item-title-row">
            <strong>${escapeHtml(item.fileName)}</strong>
            <span class="threat-pill ${levelClass}">${escapeHtml(item.threatLevel || 'SAFE')}</span>
          </div>
          <span>${formatDate(item.createdAt)} • ${item.totalDetections} detections</span>
          <small>${escapeHtml(objectNames)}</small>
        </div>
        <div class="recent-item-actions">
          ${item.detectionsFile ? `<a class="secondary-btn" href="${API_URL}${item.detectionsFile}" target="_blank" rel="noreferrer">JSON</a>` : ''}
          ${videoURL ? `<button type="button" class="secondary-btn recent-video-btn" data-video-url="${videoURL}" data-video-file="${videoFile}">View Video</button>` : ''}
        </div>
      </article>
    `;
  }).join('');
}

function formatDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Recently completed' : date.toLocaleString();
}

function showVideo(videoURL, videoFile) {
  if (!videoURL || !videoPreview) return;
  annotatedVideoURL = videoURL;
  annotatedVideo.src = videoURL;
  if (downloadVideoLink) {
    downloadVideoLink.href = `${API_URL}/download-video/${encodeURIComponent(videoFile)}`;
  }
  videoPreview.classList.remove('hidden');
  annotatedVideo.pause();
  annotatedVideo.addEventListener('loadedmetadata', () => {
    annotatedVideo.currentTime = 0;
  }, { once: true });
  annotatedVideo.load();
  videoPreview.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function jumpToTime(seconds) {
  if (!annotatedVideo) return;
  if (videoPreview && videoPreview.classList.contains('hidden')) {
    const videoFile = annotatedVideoURL.split('/').pop();
    showVideo(annotatedVideoURL, videoFile);
  }
  annotatedVideo.currentTime = Math.max(0, seconds - 0.1);
  annotatedVideo.play().catch(() => {});
  videoPreview.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

renderRecentInvestigations();

// --------------------------------------------------
// RENDER THREAT ASSESSMENT & INCIDENTS
// --------------------------------------------------

function renderThreatAssessment(threatAnalysis) {
  if (!threatAnalysis) return;

  const level = (threatAnalysis.overall_threat_level || 'SAFE').toUpperCase();
  const levelClass = level.toLowerCase();
  const scorePct = Math.round((threatAnalysis.max_threat_score || 0) * 100);
  const incidentCount = threatAnalysis.total_incidents || 0;

  if (threatBanner) {
    threatBanner.className = `threat-banner threat-${levelClass}`;
  }
  if (threatLevelPill) {
    threatLevelPill.textContent = level;
    threatLevelPill.className = `threat-level-pill ${levelClass}`;
  }
  if (threatScoreValue) {
    threatScoreValue.textContent = `${scorePct}%`;
  }
  if (threatIncidentsCount) {
    threatIncidentsCount.textContent = `${incidentCount} Incident${incidentCount === 1 ? '' : 's'} Detected`;
  }
  if (statThreatLevel) {
    statThreatLevel.textContent = level;
    statThreatLevel.className = `threat-level-text ${levelClass}`;
  }
  if (statThreatIncidents) {
    statThreatIncidents.textContent = incidentCount;
  }

  // Render Incidents List
  if (incidentsList) {
    const incidents = threatAnalysis.incidents || [];
    if (incidents.length === 0) {
      incidentsList.innerHTML = '<div class="no-incidents">No high-risk threat incidents identified in this footage.</div>';
    } else {
      incidentsList.innerHTML = incidents.map((inc, index) => {
        const incLevelClass = (inc.peak_level || 'medium').toLowerCase();
        const types = (inc.threat_types || []).join(', ') || 'Threat';
        const isArmed = inc.armed_person;

        return `
          <div class="incident-card ${incLevelClass}">
            <div class="incident-header">
              <span class="incident-badge ${incLevelClass}">Incident #${index + 1} • ${escapeHtml(inc.peak_level)}</span>
              <span class="incident-time">${inc.start_time.toFixed(1)}s – ${inc.end_time.toFixed(1)}s (${inc.duration}s)</span>
            </div>
            <div class="incident-body">
              <div class="incident-info">
                <strong>Threat Types:</strong> ${escapeHtml(types)}
                ${isArmed ? ' • <span class="armed-badge">Armed Suspect</span>' : ''}
              </div>
              <button type="button" class="jump-btn" data-jump-time="${inc.start_time}">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
                Jump to ${inc.start_time.toFixed(1)}s
              </button>
            </div>
          </div>
        `;
      }).join('');
    }
  }
}

// --------------------------------------------------
// RENDER MAIN ANALYSIS RESULTS
// --------------------------------------------------

function renderAnalysisResults(payload) {
  if (!analysisResults) return;

  currentAnalysisId = payload.analysis_id;
  chatHistory = [];

  const counts = payload.object_counts || {};
  const detections = payload.detections || [];
  totalDetections.textContent = payload.total_detections ?? detections.length;

  objectCounts.innerHTML = Object.entries(counts).length
    ? Object.entries(counts).map(([name, count]) => (
      `<span class="object-count"><strong>${escapeHtml(name)}</strong> ${count}</span>`
    )).join('')
    : 'No objects detected';

  // Render Threat Analysis
  renderThreatAssessment(payload.threat_analysis);

  // Table rows
  detectionsTable.innerHTML = detections.length
    ? detections.slice(0, 100).map((detection) => {
      const isThreat = detection.is_threat;
      const rowClass = isThreat ? 'threat-row' : '';
      return `
        <tr class="${rowClass}">
          <td>${detection.frame ?? '-'}</td>
          <td>${Number(detection.timestamp ?? 0).toFixed(2)}s</td>
          <td>
            ${escapeHtml(detection.object ?? 'Unknown')}
            ${isThreat ? `<span class="threat-tag">${escapeHtml(detection.threat_category || 'THREAT')}</span>` : ''}
          </td>
          <td>${formatConfidence(detection.confidence)}</td>
          <td>${detection.track_id ?? '-'}</td>
        </tr>
      `;
    }).join('')
    : '<tr><td colspan="5">No detections available.</td></tr>';

  resultNote.textContent = detections.length > 100
    ? `Showing the first 100 of ${detections.length} detection events.`
    : `${detections.length} detection event${detections.length === 1 ? '' : 's'} recorded.`;

  if (payload.detections_file && detectionsLink) {
    detectionsLink.href = `${API_URL}${payload.detections_file}`;
  }
  if (payload.threats_file && threatsJsonLink) {
    threatsJsonLink.href = `${API_URL}${payload.threats_file}`;
  }
  if (payload.annotated_video) {
    const resultVideoURL = new URL(payload.annotated_video, API_URL).href;
    const filename = payload.annotated_video.split('/').pop();
    annotatedVideoURL = resultVideoURL;
    annotatedVideo.src = annotatedVideoURL;
    if (downloadVideoLink) {
      downloadVideoLink.href = `${API_URL}/download-video/${encodeURIComponent(filename)}`;
    }
  }

  // Reset chat for new analysis
  if (chatMessages) {
    const threatLevel = payload.threat_analysis ? payload.threat_analysis.overall_threat_level : 'SAFE';
    chatMessages.innerHTML = `
      <div class="chat-bubble model">
        <p>Investigation session initialized for Analysis <code>#${currentAnalysisId.slice(0, 8)}</code>.</p>
        <p>Overall Footage Assessment: <strong>${threatLevel}</strong>. You can ask me to reconstruct the timeline, identify armed individuals, or prepare a dispatch report.</p>
      </div>
    `;
  }

  analysisResults.classList.remove('hidden');
  analysisResults.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// --------------------------------------------------
// EVENT LISTENERS: VIDEO & INCIDENTS
// --------------------------------------------------

if (annotatedVideoLink) {
  annotatedVideoLink.addEventListener('click', () => {
    showVideo(annotatedVideoURL, annotatedVideoURL.split('/').pop());
  });
}

if (incidentsList) {
  incidentsList.addEventListener('click', (event) => {
    const btn = event.target.closest('.jump-btn');
    if (btn && btn.dataset.jumpTime) {
      jumpToTime(parseFloat(btn.dataset.jumpTime));
    }
  });
}

if (recentInvestigationsList) {
  recentInvestigationsList.addEventListener('click', (event) => {
    const button = event.target.closest('.recent-video-btn');
    if (button) showVideo(button.dataset.videoUrl, button.dataset.videoFile);
  });
}

// --------------------------------------------------
// FORENSIC AI CHAT ASSISTANT
// --------------------------------------------------

function appendChatMessage(role, text, isLoading = false) {
  if (!chatMessages) return null;

  const bubble = document.createElement('div');
  bubble.className = `chat-bubble ${role}${isLoading ? ' loading' : ''}`;
  bubble.innerHTML = isLoading ? '<div class="typing-indicator"><span></span><span></span><span></span></div>' : `<p>${escapeHtml(text).replace(/\n/g, '<br/>')}</p>`;

  chatMessages.appendChild(bubble);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return bubble;
}

async function handleChatSubmit(question) {
  const trimmed = (question || '').trim();
  if (!trimmed) return;

  if (!currentAnalysisId) {
    appendChatMessage('model', 'Please upload and analyze a video before asking questions.');
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

// --------------------------------------------------
// UPLOAD & ANALYZE HANDLERS
// --------------------------------------------------

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    "'": '&#39;',
    '"': '&quot;'
  }[character]));
}

function formatConfidence(value) {
  const confidence = Number(value);
  return Number.isFinite(confidence) ? `${Math.round(confidence * 100)}%` : '-';
}

function setStatus(label, mode = 'ok') {
  if (!statusPill) return;
  statusPill.textContent = label;
  statusPill.className = 'status-pill';
  if (mode === 'processing') {
    statusPill.classList.add('processing');
  } else if (mode === 'ok') {
    statusPill.classList.add('ok');
  }
}

if (browseBtn && videoInput) {
  browseBtn.addEventListener('click', () => videoInput.click());
}

if (videoInput) {
  videoInput.addEventListener('change', () => {
    const file = videoInput.files && videoInput.files[0];
    if (!file) {
      fileName.textContent = 'No file selected';
      return;
    }

    const sizeMB = (file.size / (1024 * 1024)).toFixed(2);
    fileName.textContent = `${file.name} • ${sizeMB} MB`;
    fileName.classList.remove('warning');
  });
}

if (analyzeBtn) {
  analyzeBtn.addEventListener('click', async () => {
    const file = videoInput && videoInput.files && videoInput.files[0];

    if (!file) {
      fileName.textContent = 'Please select a video first';
      fileName.classList.add('warning');
      return;
    }

    fileName.classList.remove('warning');
    analyzeBtn.disabled = true;
    analyzeBtn.textContent = 'Processing...';
    setStatus('Processing', 'processing');

    if (queueValue) {
      queueValue.textContent = 'Analyzing';
    }

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch(`${API_URL}/analyze-video`, {
        method: 'POST',
        body: formData
      });

      const text = await response.text();
      let payload;

      try {
        payload = JSON.parse(text);
      } catch (error) {
        throw new Error('Backend returned invalid JSON: ' + text);
      }

      if (!response.ok) {
        throw new Error(payload.detail || 'Video analysis failed.');
      }

      if (queueValue) {
        queueValue.textContent = 'Complete';
      }

      setStatus('Ready', 'ok');
      fileName.textContent = `${file.name} • analyzed successfully`;
      renderAnalysisResults(payload);
      saveRecentInvestigation(file, payload);
    } catch (error) {
      console.error('Backend analysis error:', error);
      if (queueValue) {
        queueValue.textContent = 'Failed';
      }
      setStatus('Error', 'ok');
      fileName.textContent = error.message || 'Analysis failed';
      fileName.classList.add('warning');
    } finally {
      analyzeBtn.disabled = false;
      analyzeBtn.textContent = 'Analyze Footage';
    }
  });
}
