const API_URL = 'http://localhost:8000';
const RECENT_INVESTIGATIONS_KEY = 'forensight-recent-investigations';

const loadReportBtn = document.getElementById('loadReportBtn');
const reportAnalysisIdInput = document.getElementById('reportAnalysisIdInput');
const reportDisplayPanel = document.getElementById('reportDisplayPanel');
const reportQuickLinksChips = document.getElementById('reportQuickLinksChips');

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

function getRecentInvestigations() {
  try {
    return JSON.parse(localStorage.getItem(RECENT_INVESTIGATIONS_KEY) || '[]');
  } catch (error) {
    return [];
  }
}

function renderQuickLinks() {
  if (!reportQuickLinksChips) return;
  const recent = getRecentInvestigations();

  if (!recent.length) {
    reportQuickLinksChips.innerHTML = '<span style="color:var(--muted)">No analysis sessions completed yet. Run a Video Analysis first.</span>';
    return;
  }

  reportQuickLinksChips.innerHTML = recent.map((item) => `
    <button type="button" class="analysis-quick-link" data-analysis-id="${item.id}">
      #${item.id.slice(0, 8)} (${escapeHtml(item.fileName)})
    </button>
  `).join(' ');
}

if (loadReportBtn) {
  loadReportBtn.addEventListener('click', () => {
    const id = reportAnalysisIdInput ? reportAnalysisIdInput.value.trim() : '';
    if (id) loadReport(id);
  });
}

document.addEventListener('click', (e) => {
  const chip = e.target.closest('.analysis-quick-link');
  if (chip && chip.dataset.analysisId) {
    const id = chip.dataset.analysisId;
    if (reportAnalysisIdInput) reportAnalysisIdInput.value = id;
    loadReport(id);
  }
});

async function loadReport(analysisId) {
  if (!reportDisplayPanel) return;

  try {
    const res = await fetch(`${API_URL}/reports/${encodeURIComponent(analysisId)}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Report data not found.');

    renderReportPanel(data);
  } catch (err) {
    alert(`Report error: ${err.message}`);
  }
}

function renderReportPanel(data) {
  reportDisplayPanel.classList.remove('hidden');

  const threatData = data.threat_analysis || {};
  const overallLevel = threatData.overall_threat_level || 'SAFE';

  document.getElementById('reportStatId').textContent = data.analysis_id;
  document.getElementById('reportStatDetections').textContent = data.total_detections;
  document.getElementById('reportStatThreatScore').textContent = `${Math.round((threatData.max_threat_score || 0) * 100)}%`;
  document.getElementById('reportStatIncidents').textContent = threatData.total_incidents || 0;

  const pill = document.getElementById('reportThreatPill');
  if (pill) {
    pill.textContent = overallLevel;
    pill.className = `status-pill ${overallLevel.toLowerCase() === 'safe' ? 'ok' : 'processing'}`;
  }

  // Findings
  const findingsList = document.getElementById('reportFindingsList');
  const findings = data.findings || [];
  if (findingsList) {
    findingsList.innerHTML = findings.length
      ? findings.map((f) => `
        <div class="finding-item">
          <h4>${escapeHtml(f.title)}</h4>
          <p>${escapeHtml(f.detail)}</p>
        </div>
      `).join('')
      : '<p class="empty-state">No specific findings logged.</p>';
  }

  // Timeline
  const timelineList = document.getElementById('reportTimelineList');
  const timeline = data.timeline || [];
  if (timelineList) {
    timelineList.innerHTML = timeline.length
      ? timeline.map((item) => `
        <div class="timeline-event">
          <div class="timeline-marker ${item.is_threat ? 'threat' : 'safe'}"></div>
          <div class="timeline-event-body">
            <strong>${escapeHtml(item.event)}</strong>
            <span>Confidence: ${formatConfidence(item.confidence)}${item.track_id !== null ? ` • Track #${item.track_id}` : ''}</span>
          </div>
          <div class="timeline-time">${Number(item.timestamp || 0).toFixed(2)}s</div>
        </div>
      `).join('')
      : '<p class="empty-state">No timeline available.</p>';
  }

  reportDisplayPanel.scrollIntoView({ behavior: 'smooth' });
}

// Initial load
renderQuickLinks();
const recent = getRecentInvestigations();
if (recent.length && reportAnalysisIdInput) {
  reportAnalysisIdInput.value = recent[0].id;
  loadReport(recent[0].id);
}
