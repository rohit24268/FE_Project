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
const RECENT_INVESTIGATIONS_KEY = 'forensight-recent-investigations';
let annotatedVideoURL = '';

function getRecentInvestigations() {
  try {
    return JSON.parse(localStorage.getItem(RECENT_INVESTIGATIONS_KEY) || '[]');
  } catch (error) {
    return [];
  }
}

function saveRecentInvestigation(file, payload) {
  const recent = getRecentInvestigations();
  const investigation = {
    id: payload.analysis_id,
    fileName: file.name,
    createdAt: new Date().toISOString(),
    totalDetections: payload.total_detections ?? (payload.detections || []).length,
    objectCounts: payload.object_counts || {},
    annotatedVideo: payload.annotated_video,
    detectionsFile: payload.detections_file
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
    return `
      <article class="recent-item">
        <div class="recent-item-main">
          <strong>${escapeHtml(item.fileName)}</strong>
          <span>${formatDate(item.createdAt)} · ${item.totalDetections} detections</span>
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
  downloadVideoLink.href = `${API_URL}/download-video/${encodeURIComponent(videoFile)}`;
  videoPreview.classList.remove('hidden');
  annotatedVideo.pause();
  annotatedVideo.addEventListener('loadedmetadata', () => {
    annotatedVideo.currentTime = 0;
  }, { once: true });
  annotatedVideo.load();
  videoPreview.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

renderRecentInvestigations();

function renderAnalysisResults(payload) {
  if (!analysisResults) return;

  const counts = payload.object_counts || {};
  const detections = payload.detections || [];
  totalDetections.textContent = payload.total_detections ?? detections.length;
  objectCounts.innerHTML = Object.entries(counts).length
    ? Object.entries(counts).map(([name, count]) => (
      `<span class="object-count"><strong>${escapeHtml(name)}</strong> ${count}</span>`
    )).join('')
    : 'No objects detected';

  detectionsTable.innerHTML = detections.length
    ? detections.slice(0, 100).map((detection) => `
      <tr>
        <td>${detection.frame ?? '-'}</td>
        <td>${Number(detection.timestamp ?? 0).toFixed(2)}s</td>
        <td>${escapeHtml(detection.object ?? 'Unknown')}</td>
        <td>${formatConfidence(detection.confidence)}</td>
        <td>${detection.track_id ?? '-'}</td>
      </tr>
    `).join('')
    : '<tr><td colspan="5">No detections available.</td></tr>';

  resultNote.textContent = detections.length > 100
    ? `Showing the first 100 of ${detections.length} detection events.`
    : `${detections.length} detection event${detections.length === 1 ? '' : 's'} recorded.`;

  if (payload.detections_file) {
    detectionsLink.href = `${API_URL}${payload.detections_file}`;
  }
  if (payload.annotated_video) {
    const resultVideoURL = new URL(payload.annotated_video, API_URL).href;
    const filename = payload.annotated_video.split('/').pop();
    annotatedVideoURL = resultVideoURL;
    annotatedVideo.src = annotatedVideoURL;
    downloadVideoLink.href = `${API_URL}/download-video/${encodeURIComponent(filename)}`;
  }

  analysisResults.classList.remove('hidden');
  analysisResults.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

if (annotatedVideoLink) {
  annotatedVideoLink.addEventListener('click', () => {
    showVideo(annotatedVideoURL, annotatedVideoURL.split('/').pop());
  });
}

if (recentInvestigationsList) {
  recentInvestigationsList.addEventListener('click', (event) => {
    const button = event.target.closest('.recent-video-btn');
    if (button) showVideo(button.dataset.videoUrl, button.dataset.videoFile);
  });
}

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
