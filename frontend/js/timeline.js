const API_URL = window.API_URL || 'http://localhost:8000';
const RECENT_INVESTIGATIONS_KEY = 'forensight-recent-investigations';

const timelineAnalysisIdInput = document.getElementById('timelineAnalysisIdInput');
const loadTimelineBtn = document.getElementById('loadTimelineBtn');
const timelineContainer = document.getElementById('timelineContainer');
const timelineQuickLinksChips = document.getElementById('timelineQuickLinksChips');
const timelineCountPill = document.getElementById('timelineCountPill');

// Threat UI Elements
const timelineThreatBanner = document.getElementById('timelineThreatBanner');
const timelineThreatLevelPill = document.getElementById('timelineThreatLevelPill');
const timelineThreatScoreValue = document.getElementById('timelineThreatScoreValue');
const timelineThreatIncidentsCount = document.getElementById('timelineThreatIncidentsCount');
const timelineThreatFilterBtn = document.getElementById('timelineThreatFilterBtn');

let allTimelineItems = [];
let showThreatsOnly = false;

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
  const recent = getRecentInvestigations().filter(
    (item) => item.caseName && item.caseName !== 'Case unavailable'
  );

  if (!recent.length) {
    timelineQuickLinksChips.innerHTML = '<span style="color:var(--muted)">No recent cases found.</span>';
    return;
  }

  timelineQuickLinksChips.innerHTML = recent.map((item) => `
    <button type="button" class="analysis-quick-link" data-analysis-id="${item.id}">
      ${escapeHtml(item.caseName)}
    </button>
  `).join(' ');
}

// --------------------------------------------------
// THREAT ASSESSMENT BANNER
// --------------------------------------------------

function renderTimelineThreatBanner(threatAnalysis) {
  if (!threatAnalysis || !timelineThreatBanner) return;

  const level = (threatAnalysis.overall_threat_level || 'SAFE').toUpperCase();
  const levelClass = level.toLowerCase();
  const scorePct = Math.round((threatAnalysis.max_threat_score || 0) * 100);
  const incidentCount = threatAnalysis.total_incidents || 0;

  timelineThreatBanner.className = `threat-banner threat-${levelClass}`;
  timelineThreatBanner.classList.remove('hidden');

  if (timelineThreatLevelPill) {
    timelineThreatLevelPill.textContent = level;
    timelineThreatLevelPill.className = `threat-level-pill ${levelClass}`;
  }
  if (timelineThreatScoreValue) {
    timelineThreatScoreValue.textContent = `${scorePct}%`;
  }
  if (timelineThreatIncidentsCount) {
    timelineThreatIncidentsCount.textContent = `${incidentCount} Incident${incidentCount === 1 ? '' : 's'} Detected`;
  }
}

// --------------------------------------------------
// THREAT FILTER TOGGLE
// --------------------------------------------------

if (timelineThreatFilterBtn) {
  timelineThreatFilterBtn.addEventListener('click', () => {
    showThreatsOnly = !showThreatsOnly;
    timelineThreatFilterBtn.textContent = showThreatsOnly ? 'Show All Events' : 'Show Threats Only';
    timelineThreatFilterBtn.classList.toggle('active', showThreatsOnly);
    renderTimelineEvents(allTimelineItems);
  });
}

// --------------------------------------------------
// LOAD & RENDER
// --------------------------------------------------

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

    allTimelineItems = data.evidence || [];
    renderTimelineThreatBanner(data.threat_analysis);
    renderTimelineEvents(allTimelineItems);
  } catch (err) {
    timelineContainer.innerHTML = `<p class="inline-error">Error: ${escapeHtml(err.message)}</p>`;
  }
}

function renderTimelineEvents(items) {
  const filtered = showThreatsOnly ? items.filter(ev => ev.is_threat) : items;
  if (timelineCountPill) timelineCountPill.textContent = `${filtered.length} Events`;

  if (!filtered.length) {
    timelineContainer.innerHTML = `<p class="empty-state">${showThreatsOnly ? 'No threat events detected in this analysis.' : 'No timeline events recorded for this analysis.'}</p>`;
    return;
  }

  const sorted = [...filtered].sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));

  timelineContainer.innerHTML = sorted.map((ev) => {
    const isThreat = ev.is_threat;
    const markerClass = isThreat ? 'threat' : 'safe';
    const ts = Number(ev.timestamp || 0).toFixed(2);
    const threatCatLabel = isThreat && ev.threat_category && ev.threat_category !== 'NONE'
      ? ` <span class="threat-tag">${escapeHtml(ev.threat_category.replace('_', ' '))}</span>`
      : '';

    return `
      <div class="timeline-event">
        <div class="timeline-marker ${markerClass}"></div>
        <div class="timeline-event-body">
          <strong>${escapeHtml(ev.object.toUpperCase())} ${isThreat ? '— THREAT DETECTED' : 'Detected'}${threatCatLabel}</strong>
          <span>${escapeHtml(ev.description)}</span>
        </div>
        <div class="timeline-time">${ts}s</div>
      </div>
    `;
  }).join('');
}

document.addEventListener('caseNamesResolved', renderQuickLinks);

// Initial load
renderQuickLinks();
const recent = getRecentInvestigations();
const targetId = recent.length ? recent[0].id : null;
if (targetId && timelineAnalysisIdInput) {
  timelineAnalysisIdInput.value = targetId;
  loadTimeline(targetId);
}
