const API_URL = 'http://localhost:8000';
const RECENT_INVESTIGATIONS_KEY = 'forensight-recent-investigations';

const loadEvidenceBtn = document.getElementById('loadEvidenceBtn');
const evidenceAnalysisIdInput = document.getElementById('evidenceAnalysisIdInput');
const btnViewEvidence = document.getElementById('btnViewEvidence');
const btnViewTimeline = document.getElementById('btnViewTimeline');
const evidenceListSection = document.getElementById('evidenceListSection');
const timelineSection = document.getElementById('timelineSection');
const evidenceTableBody = document.getElementById('evidenceTableBody');
const timelineContainer = document.getElementById('timelineContainer');
const evidenceQuickLinksChips = document.getElementById('evidenceQuickLinksChips');

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
  if (!evidenceQuickLinksChips) return;
  const recent = getRecentInvestigations();

  if (!recent.length) {
    evidenceQuickLinksChips.innerHTML = '<span style="color:var(--muted)">No analysis sessions completed yet. Run a Video Analysis first.</span>';
    return;
  }

  evidenceQuickLinksChips.innerHTML = recent.map((item) => `
    <button type="button" class="analysis-quick-link" data-analysis-id="${item.id}">
      #${item.id.slice(0, 8)} (${escapeHtml(item.fileName)})
    </button>
  `).join(' ');
}

if (btnViewEvidence && btnViewTimeline) {
  btnViewEvidence.addEventListener('click', () => {
    btnViewEvidence.classList.add('active');
    btnViewTimeline.classList.remove('active');
    evidenceListSection.classList.remove('hidden');
    timelineSection.classList.add('hidden');
  });

  btnViewTimeline.addEventListener('click', () => {
    btnViewTimeline.classList.add('active');
    btnViewEvidence.classList.remove('active');
    timelineSection.classList.remove('hidden');
    evidenceListSection.classList.add('hidden');
  });
}

if (loadEvidenceBtn) {
  loadEvidenceBtn.addEventListener('click', () => {
    const id = evidenceAnalysisIdInput ? evidenceAnalysisIdInput.value.trim() : '';
    if (id) loadEvidence(id);
  });
}

document.addEventListener('click', (e) => {
  const chip = e.target.closest('.analysis-quick-link');
  if (chip && chip.dataset.analysisId) {
    const id = chip.dataset.analysisId;
    if (evidenceAnalysisIdInput) evidenceAnalysisIdInput.value = id;
    loadEvidence(id);
  }
});

async function loadEvidence(analysisId) {
  if (!evidenceTableBody) return;
  evidenceTableBody.innerHTML = '<tr><td colspan="6">Loading evidence data...</td></tr>';

  try {
    const res = await fetch(`${API_URL}/evidence/${encodeURIComponent(analysisId)}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Evidence not found.');

    renderEvidenceTable(data.evidence || []);
    renderEvidenceTimeline(data.evidence || []);
  } catch (err) {
    evidenceTableBody.innerHTML = `<tr><td colspan="6" class="inline-error">Error: ${escapeHtml(err.message)}</td></tr>`;
    if (timelineContainer) timelineContainer.innerHTML = `<p class="inline-error">Error: ${escapeHtml(err.message)}</p>`;
  }
}

function renderEvidenceTable(items) {
  const countPill = document.getElementById('evidenceCountPill');
  if (countPill) countPill.textContent = `${items.length} Item${items.length === 1 ? '' : 's'}`;

  if (!items.length) {
    evidenceTableBody.innerHTML = '<tr><td colspan="6">No evidence detections recorded for this analysis.</td></tr>';
    return;
  }

  evidenceTableBody.innerHTML = items.map((ev) => {
    const isThreat = ev.is_threat;
    const typeLabel = isThreat ? ev.threat_category.replace('_', ' ') : 'DETECTION';
    const tagClass = isThreat ? 'threat-tag' : '';

    return `
      <tr class="${isThreat ? 'threat-row' : ''}">
        <td><span class="${tagClass}">${escapeHtml(typeLabel)}</span></td>
        <td>F#${ev.frame ?? '-'} (${Number(ev.timestamp || 0).toFixed(2)}s)</td>
        <td><strong>${escapeHtml(ev.object)}</strong></td>
        <td>${formatConfidence(ev.confidence)}</td>
        <td>${ev.track_id ?? '-'}</td>
        <td>${escapeHtml(ev.description)}</td>
      </tr>
    `;
  }).join('');
}

function renderEvidenceTimeline(items) {
  const timelinePill = document.getElementById('timelineCountPill');
  if (timelinePill) timelinePill.textContent = `${items.length} Events`;

  if (!items.length) {
    if (timelineContainer) timelineContainer.innerHTML = '<p class="empty-state">No timeline events found.</p>';
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
if (recent.length && evidenceAnalysisIdInput) {
  evidenceAnalysisIdInput.value = recent[0].id;
  loadEvidence(recent[0].id);
}
