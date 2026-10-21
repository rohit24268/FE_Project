const API_URL = window.API_URL || 'http://localhost:8000';
const RECENT_INVESTIGATIONS_KEY = 'forensight-recent-investigations';

const loadEvidenceBtn = document.getElementById('loadEvidenceBtn');
const evidenceAnalysisIdInput = document.getElementById('evidenceAnalysisIdInput');
const analysisCaseName = document.getElementById('analysisCaseName');
const evidenceTableBody = document.getElementById('evidenceTableBody');
const evidenceQuickLinksChips = document.getElementById('evidenceQuickLinksChips');
const viewAnnotatedVideoBtn = document.getElementById('viewAnnotatedVideoBtn');

// Threat UI Elements
const evidenceThreatBanner = document.getElementById('evidenceThreatBanner');
const evidenceThreatLevelPill = document.getElementById('evidenceThreatLevelPill');
const evidenceThreatScoreValue = document.getElementById('evidenceThreatScoreValue');
const evidenceThreatIncidentsCount = document.getElementById('evidenceThreatIncidentsCount');
const threatFilterBtn = document.getElementById('threatFilterBtn');

let allEvidenceItems = [];
let showThreatsOnly = false;
const caseNameLookups = new Set();
const unavailableCaseNames = new Set();

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

  const namedCases = [...new Map(recent.filter(
    (item) => item.caseName && item.caseName !== 'Case unavailable'
      && !unavailableCaseNames.has(item.id)
  ).map((item) => [item.caseName, item])).values()];
  const pendingLookups = recent.some(
    (item) => (
      item.id
      && (!item.caseName || item.caseName === 'Case unavailable')
      && !unavailableCaseNames.has(item.id)
    )
  );

  evidenceQuickLinksChips.innerHTML = namedCases.length
    ? namedCases.map((item) => `
        <button type="button" class="analysis-quick-link" data-case-name="${escapeHtml(item.caseName)}">
          ${escapeHtml(item.caseName)}
        </button>
      `).join(' ')
    : `<span style="color:var(--muted)">${
        pendingLookups ? 'Loading recent case names...' : 'No recent cases found.'
      }</span>`;

  recent
    .filter((item) => (
      (!item.caseName || item.caseName === 'Case unavailable')
      && item.id
      && !caseNameLookups.has(item.id)
      && !unavailableCaseNames.has(item.id)
    ))
    .forEach(async (item) => {
      caseNameLookups.add(item.id);
      try {
        const response = await fetch(
          `${API_URL}/cases/by-analysis/${encodeURIComponent(item.id)}`
        );
        if (!response.ok) {
          const error = await response.json().catch(() => ({}));
          throw new Error(error.detail || 'Failed to load case name.');
        }

        const { case_name: caseName } = await response.json();
        if (!caseName) throw new Error('No case name returned for this analysis.');
        const updatedRecent = getRecentInvestigations().map((entry) => (
          entry.id === item.id ? { ...entry, caseName } : entry
        ));
        localStorage.setItem(RECENT_INVESTIGATIONS_KEY, JSON.stringify(updatedRecent));
        caseNameLookups.delete(item.id);
        renderQuickLinks();
      } catch (error) {
        caseNameLookups.delete(item.id);
        unavailableCaseNames.add(item.id);
        console.error(`Could not load case name for analysis ${item.id}:`, error);
        renderQuickLinks();
      }
    });
}

// --------------------------------------------------
// THREAT ASSESSMENT BANNER
// --------------------------------------------------

function renderEvidenceThreatBanner(threatAnalysis) {
  if (!threatAnalysis || !evidenceThreatBanner) return;

  const level = (threatAnalysis.overall_threat_level || 'SAFE').toUpperCase();
  const levelClass = level.toLowerCase();
  const scorePct = Math.round((threatAnalysis.max_threat_score || 0) * 100);
  const incidentCount = threatAnalysis.total_incidents || 0;

  evidenceThreatBanner.className = `threat-banner threat-${levelClass}`;
  evidenceThreatBanner.classList.remove('hidden');

  if (evidenceThreatLevelPill) {
    evidenceThreatLevelPill.textContent = level;
    evidenceThreatLevelPill.className = `threat-level-pill ${levelClass}`;
  }
  if (evidenceThreatScoreValue) {
    evidenceThreatScoreValue.textContent = `${scorePct}%`;
  }
  if (evidenceThreatIncidentsCount) {
    evidenceThreatIncidentsCount.textContent = `${incidentCount} Incident${incidentCount === 1 ? '' : 's'} Detected`;
  }
}

// --------------------------------------------------
// THREAT FILTER TOGGLE
// --------------------------------------------------

if (threatFilterBtn) {
  threatFilterBtn.addEventListener('click', () => {
    showThreatsOnly = !showThreatsOnly;
    threatFilterBtn.textContent = showThreatsOnly ? 'Show All Evidence' : 'Show Threats Only';
    threatFilterBtn.classList.toggle('active', showThreatsOnly);
    renderEvidenceTable(allEvidenceItems);
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
  if (chip && chip.dataset.caseName) {
    const caseSelect = document.getElementById('caseNameSelect');
    const option = [...(caseSelect?.options || [])].find(
      (item) => item.textContent === chip.dataset.caseName
    );
    if (!caseSelect || !option) return;
    caseSelect.value = option.value;
    caseSelect.dispatchEvent(new Event('change'));
    const id = evidenceAnalysisIdInput?.value.trim();
    if (id) loadEvidence(id);
  }
});

document.addEventListener('caseNamesResolved', renderQuickLinks);

document.addEventListener('caseSessionSelected', (event) => {
  const { analysisId, autoLoad } = event.detail || {};
  if (autoLoad && analysisId) loadEvidence(analysisId);
});

async function loadEvidence(analysisId) {
  if (!evidenceTableBody) return;
  evidenceTableBody.innerHTML = '<tr><td colspan="6">Loading evidence data...</td></tr>';
  if (viewAnnotatedVideoBtn) {
    viewAnnotatedVideoBtn.classList.add('hidden');
    viewAnnotatedVideoBtn.removeAttribute('href');
  }
  if (analysisCaseName) {
    analysisCaseName.classList.add('hidden');
    analysisCaseName.textContent = '';
  }

  try {
    const res = await fetch(`${API_URL}/evidence/${encodeURIComponent(analysisId)}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Evidence not found.');

    if (analysisCaseName) {
      analysisCaseName.textContent = data.case_name
        ? `Case: ${data.case_name}`
        : 'No case linked to this analysis session.';
      analysisCaseName.classList.remove('hidden');
    }
    allEvidenceItems = data.evidence || [];
    if (viewAnnotatedVideoBtn && data.annotated_video_url) {
      viewAnnotatedVideoBtn.href = new URL(
        data.annotated_video_url,
        API_URL
      ).href;
      viewAnnotatedVideoBtn.classList.remove('hidden');
    }
    renderEvidenceThreatBanner(data.threat_analysis);
    renderEvidenceTable(allEvidenceItems);
  } catch (err) {
    evidenceTableBody.innerHTML = `<tr><td colspan="6" class="inline-error">Error: ${escapeHtml(err.message)}</td></tr>`;
  }
}

function renderEvidenceTable(items) {
  const filtered = showThreatsOnly ? items.filter(ev => ev.is_threat) : items;
  const countPill = document.getElementById('evidenceCountPill');
  if (countPill) {
    const suffix = showThreatsOnly ? ' Threats' : ' Items';
    countPill.textContent = `${filtered.length}${filtered.length === 1 ? suffix.replace('s', '') : suffix}`;
  }

  if (!filtered.length) {
    evidenceTableBody.innerHTML = `<tr><td colspan="6">${showThreatsOnly ? 'No threat detections found.' : 'No evidence or timeline events recorded for this analysis.'}</td></tr>`;
    return;
  }

  const chronological = [...filtered].sort(
    (first, second) => Number(first.timestamp || 0) - Number(second.timestamp || 0)
  );
  evidenceTableBody.innerHTML = chronological.map((ev) => {
    const isThreat = ev.is_threat;
    const typeLabel = isThreat ? (ev.threat_category || 'THREAT').replace('_', ' ') : 'DETECTION';
    const tagClass = isThreat ? 'threat-tag' : '';

    return `
      <tr class="${isThreat ? 'threat-row' : ''}">
        <td><span class="${tagClass}">${escapeHtml(typeLabel)}</span></td>
        <td>F#${ev.frame ?? '-'} (${Number(ev.timestamp || 0).toFixed(2)}s)</td>
        <td><strong>${escapeHtml(ev.object)}</strong></td>
        <td>${formatConfidence(ev.confidence)}</td>
        <td>${escapeHtml(ev.threat_category && ev.threat_category !== 'NONE' ? ev.threat_category.replace('_', ' ') : '-')}</td>
        <td>${escapeHtml(ev.description)}</td>
      </tr>
    `;
  }).join('');
}

// Initial load
renderQuickLinks();
