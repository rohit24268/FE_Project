const API_URL = 'http://localhost:8000';
const RECENT_INVESTIGATIONS_KEY = 'forensight-recent-investigations';

const timelineAnalysisIdInput = document.getElementById('timelineAnalysisIdInput');
const loadTimelineBtn = document.getElementById('loadTimelineBtn');
const timelineContainer = document.getElementById('timelineContainer');
const timelineQuickLinksChips = document.getElementById('timelineQuickLinksChips');
const timelineCountPill = document.getElementById('timelineCountPill');

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
  if (!timelineQuickLinksChips) return;
  const recent = getRecentInvestigations();

  if (!recent.length) {
    timelineQuickLinksChips.innerHTML = '<span style="color:var(--muted)">No analysis sessions completed yet. Run a Video Analysis on Dashboard first.</span>';
    return;
  }

  timelineQuickLinksChips.innerHTML = recent.map((item) => `
    <button type="button" class="analysis-quick-link" data-analysis-id="${item.id}">
      #${item.id.slice(0, 8)} (${escapeHtml(item.fileName)})
    </button>
  `).join(' ');
}

if (loadTimelineBtn) {
  loadTimelineBtn.addEventListener('click', () => {
    const id = timelineAnalysisIdInput ? timelineAnalysisIdInput.value.trim() : '';
    if (id) loadTimeline(id);
  });
}

document.addEventListener('click', (e) => {
  const chip = e.target.closest('.analysis-quick-link');
  if (chip && chip.dataset.analysisId) {
    const id = chip.dataset.analysisId;
    if (timelineAnalysisIdInput) timelineAnalysisIdInput.value = id;
    loadTimeline(id);
  }
});

async function loadTimeline(analysisId) {
  if (!timelineContainer) return;
  timelineContainer.innerHTML = '<p class="empty-state">Loading timeline events...</p>';

  try {
    const res = await fetch(`${API_URL}/evidence/${encodeURIComponent(analysisId)}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Timeline data not found.');

    renderTimelineEvents(data.evidence || []);
  } catch (err) {
    timelineContainer.innerHTML = `<p class="inline-error">Error: ${escapeHtml(err.message)}</p>`;
  }
}

function renderTimelineEvents(items) {
  if (timelineCountPill) timelineCountPill.textContent = `${items.length} Events`;

  if (!items.length) {
    timelineContainer.innerHTML = '<p class="empty-state">No timeline events recorded for this analysis.</p>';
    return;
  }

  const sorted = [...items].sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));

  timelineContainer.innerHTML = sorted.map((ev) => {
    const isThreat = ev.is_threat;
    const markerClass = isThreat ? 'threat' : 'safe';
    const ts = Number(ev.timestamp || 0).toFixed(2);

    return `
      <div class="timeline-event">
        <div class="timeline-marker ${markerClass}"></div>
        <div class="timeline-event-body">
          <strong>${escapeHtml(ev.object.toUpperCase())} ${isThreat ? '— THREAT DETECTED' : 'Detected'}</strong>
          <span>${escapeHtml(ev.description)}</span>
        </div>
        <div class="timeline-time">${ts}s</div>
      </div>
    `;
  }).join('');
}

// Initial load
renderQuickLinks();
const recent = getRecentInvestigations();
if (recent.length && timelineAnalysisIdInput) {
  timelineAnalysisIdInput.value = recent[0].id;
  loadTimeline(recent[0].id);
}
