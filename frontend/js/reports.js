const API_URL = window.API_URL || 'http://localhost:8000';
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
  const recent = [...new Map(getRecentInvestigations().filter(
    (item) => item.caseName && item.caseName !== 'Case unavailable'
  ).map((item) => [item.caseName, item])).values()];

  if (!recent.length) {
    reportQuickLinksChips.innerHTML = '<span style="color:var(--muted)">No recent cases found.</span>';
    return;
  }

  reportQuickLinksChips.innerHTML = recent.map((item) => `
    <button type="button" class="analysis-quick-link" data-case-name="${escapeHtml(item.caseName)}">
      ${escapeHtml(item.caseName)}
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
  if (chip && chip.dataset.caseName) {
    const caseSelect = document.getElementById('caseNameSelect');
    const option = [...(caseSelect?.options || [])].find(
      (item) => item.textContent === chip.dataset.caseName
    );
    if (!caseSelect || !option) return;
    caseSelect.value = option.value;
    caseSelect.dispatchEvent(new Event('change'));
    const id = reportAnalysisIdInput?.value.trim();
    if (id) loadReport(id);
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
  const overallLevel = (threatData.overall_threat_level || 'SAFE').toUpperCase();
  const levelClass = overallLevel.toLowerCase();
  const scorePct = Math.round((threatData.max_threat_score || 0) * 100);
  const incidentCount = threatData.total_incidents || 0;

  document.getElementById('reportStatId').textContent = data.case_name || 'Case name unavailable';
  document.getElementById('reportStatDetections').textContent = data.total_detections;
  document.getElementById('reportStatThreatScore').textContent = `${scorePct}%`;
  document.getElementById('reportStatIncidents').textContent = incidentCount;

  // Threat pill with severity coloring
  const pill = document.getElementById('reportThreatPill');
  if (pill) {
    pill.textContent = overallLevel;
    pill.className = `threat-level-pill ${levelClass}`;
  }

  // Threat Assessment Banner
  const reportThreatBanner = document.getElementById('reportThreatBanner');
  if (reportThreatBanner) {
    reportThreatBanner.className = `threat-banner threat-${levelClass}`;
  }
  const reportThreatLevelBadge = document.getElementById('reportThreatLevelBadge');
  if (reportThreatLevelBadge) {
    reportThreatLevelBadge.textContent = overallLevel;
    reportThreatLevelBadge.className = `threat-level-pill ${levelClass}`;
  }
  const reportThreatScoreLabel = document.getElementById('reportThreatScoreLabel');
  if (reportThreatScoreLabel) {
    reportThreatScoreLabel.textContent = `${scorePct}%`;
  }
  const reportThreatIncidentsLabel = document.getElementById('reportThreatIncidentsLabel');
  if (reportThreatIncidentsLabel) {
    reportThreatIncidentsLabel.textContent = `${incidentCount} Incident${incidentCount === 1 ? '' : 's'} Detected`;
  }

  // Threat Incidents Breakdown
  const reportIncidentsList = document.getElementById('reportIncidentsList');
  const reportIncidentsSummaryText = document.getElementById('reportIncidentsSummaryText');
  const incidents = threatData.incidents || [];

  if (reportIncidentsSummaryText) {
    const criticalCount = incidents.filter(i => i.peak_level === 'CRITICAL').length;
    const highCount = incidents.filter(i => i.peak_level === 'HIGH').length;
    const mediumCount = incidents.filter(i => i.peak_level === 'MEDIUM').length;
    const parts = [];
    if (criticalCount) parts.push(`${criticalCount} Critical`);
    if (highCount) parts.push(`${highCount} High`);
    if (mediumCount) parts.push(`${mediumCount} Medium`);
    reportIncidentsSummaryText.textContent = parts.length ? parts.join(' • ') : 'No incidents';
  }

  if (reportIncidentsList) {
    if (incidents.length === 0) {
      reportIncidentsList.innerHTML = '<div class="no-incidents">No threat incidents identified in this analysis.</div>';
    } else {
      reportIncidentsList.innerHTML = incidents.map((inc, index) => {
        const incLevelClass = (inc.peak_level || 'medium').toLowerCase();
        const types = (inc.threat_types || []).join(', ') || 'Threat';
        const isArmed = inc.armed_person;

        return `
          <div class="incident-card ${incLevelClass}">
            <div class="incident-header">
              <span class="incident-badge ${incLevelClass}">Incident #${index + 1} • ${escapeHtml(inc.peak_level)}</span>
              <span class="incident-time">${Number(inc.start_time || 0).toFixed(1)}s – ${Number(inc.end_time || 0).toFixed(1)}s (${inc.duration}s)</span>
            </div>
            <div class="incident-body">
              <div class="incident-info">
                <strong>Threat Types:</strong> ${escapeHtml(types)}
                ${isArmed ? ' • <span class="armed-badge">Armed Suspect</span>' : ''}
              </div>
              <div class="incident-info">
                <strong>Peak Score:</strong> ${Math.round((inc.peak_score || 0) * 100)}%
                • <strong>Frames:</strong> ${inc.frame_count || 0}
              </div>
            </div>
          </div>
        `;
      }).join('');
    }
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
      ? timeline.map((item) => {
        const threatCatLabel = item.is_threat && item.threat_category && item.threat_category !== 'NONE'
          ? ` <span class="threat-tag">${escapeHtml(item.threat_category.replace('_', ' '))}</span>`
          : '';

        return `
          <div class="timeline-event">
            <div class="timeline-marker ${item.is_threat ? 'threat' : 'safe'}"></div>
            <div class="timeline-event-body">
              <strong>${escapeHtml(item.event)}${threatCatLabel}</strong>
              <span>Confidence: ${formatConfidence(item.confidence)}${item.attributes ? ` • ${escapeHtml(item.attributes)}` : ''}</span>
            </div>
            <div class="timeline-time">${Number(item.timestamp || 0).toFixed(2)}s</div>
          </div>
        `;
      }).join('')
      : '<p class="empty-state">No timeline available.</p>';
  }

  reportDisplayPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

document.addEventListener('caseNamesResolved', renderQuickLinks);

document.addEventListener('caseSessionSelected', (event) => {
  const { analysisId } = event.detail || {};
  if (analysisId) loadReport(analysisId);
});

// Initial load
renderQuickLinks();
