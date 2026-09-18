const API_URL = 'http://localhost:8000';
const RECENT_INVESTIGATIONS_KEY = 'forensight-recent-investigations';

const showNewCaseModalBtn = document.getElementById('showNewCaseModalBtn');
const createCasePanel = document.getElementById('createCasePanel');
const cancelCaseBtn = document.getElementById('cancelCaseBtn');
const createCaseForm = document.getElementById('createCaseForm');
const casesList = document.getElementById('casesList');
const casesCountPill = document.getElementById('casesCountPill');

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    "'": '&#39;',
    '"': '&quot;'
  }[character]));
}

function formatDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Recently created' : date.toLocaleString();
}

function getRecentAnalysisId() {
  try {
    const recent = JSON.parse(localStorage.getItem(RECENT_INVESTIGATIONS_KEY) || '[]');
    return recent.length ? recent[0].id : null;
  } catch (err) {
    return null;
  }
}

if (showNewCaseModalBtn && createCasePanel) {
  showNewCaseModalBtn.addEventListener('click', () => {
    createCasePanel.classList.remove('hidden');
    createCasePanel.scrollIntoView({ behavior: 'smooth' });
  });
}

if (cancelCaseBtn && createCasePanel) {
  cancelCaseBtn.addEventListener('click', () => {
    createCasePanel.classList.add('hidden');
  });
}

async function loadCases() {
  if (!casesList) return;
  try {
    const res = await fetch(`${API_URL}/cases`);
    if (!res.ok) throw new Error('Failed to load cases from server.');
    const cases = await res.json();
    renderCases(cases);
  } catch (err) {
    casesList.innerHTML = `<p class="inline-error">Error loading cases: ${escapeHtml(err.message)}</p>`;
  }
}

function renderCases(cases) {
  if (!casesList) return;
  if (casesCountPill) casesCountPill.textContent = `${cases.length} Case${cases.length === 1 ? '' : 's'}`;

  if (!cases.length) {
    casesList.innerHTML = '<p class="empty-state">No cases created yet. Click "+ New Case" above to start a case.</p>';
    return;
  }

  const currentAnalysisId = getRecentAnalysisId();

  casesList.innerHTML = cases.map((c) => {
    const createdDate = formatDate(c.created_at);
    const analysisCount = (c.analysis_ids || []).length;
    const isCurrentLinked = currentAnalysisId && (c.analysis_ids || []).includes(currentAnalysisId);

    return `
      <div class="case-card">
        <div class="case-card-main">
          <div class="case-card-meta">
            <h3>${escapeHtml(c.case_name)}</h3>
            <span class="threat-pill ${c.status === 'open' ? 'safe' : 'medium'}">${escapeHtml(c.status.toUpperCase())}</span>
          </div>
          <p>${escapeHtml(c.description || 'No description provided.')}</p>
          <div class="case-card-details">
            <span><strong>Case ID:</strong> <code>${c.case_id}</code></span>
            <span><strong>Investigator:</strong> ${escapeHtml(c.investigator || 'Unassigned')}</span>
            <span><strong>Created:</strong> ${createdDate}</span>
            <span><strong>Linked Analyses:</strong> ${analysisCount}</span>
          </div>
        </div>
        <div class="case-card-actions">
          ${currentAnalysisId ? `
            <button type="button" class="secondary-btn link-analysis-btn" data-case-id="${c.case_id}" ${isCurrentLinked ? 'disabled' : ''}>
              ${isCurrentLinked ? 'Linked' : 'Link Current Analysis'}
            </button>
          ` : ''}
        </div>
      </div>
    `;
  }).join('');
}

if (createCaseForm) {
  createCaseForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const nameInput = document.getElementById('caseNameInput');
    const investigatorInput = document.getElementById('caseInvestigatorInput');
    const descInput = document.getElementById('caseDescriptionInput');

    const payload = {
      case_name: nameInput.value,
      investigator: investigatorInput.value,
      description: descInput.value,
      status: 'open'
    };

    try {
      const res = await fetch(`${API_URL}/cases`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (!res.ok) throw new Error('Failed to create case.');

      nameInput.value = '';
      investigatorInput.value = '';
      descInput.value = '';
      if (createCasePanel) createCasePanel.classList.add('hidden');
      loadCases();
    } catch (err) {
      alert(`Error creating case: ${err.message}`);
    }
  });
}

document.addEventListener('click', async (e) => {
  const btn = e.target.closest('.link-analysis-btn');
  const currentAnalysisId = getRecentAnalysisId();
  if (!btn || !currentAnalysisId) return;

  const caseId = btn.dataset.caseId;
  try {
    const res = await fetch(`${API_URL}/cases/${caseId}/link-analysis`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ analysis_id: currentAnalysisId })
    });
    if (!res.ok) throw new Error('Failed to link analysis to case.');
    loadCases();
  } catch (err) {
    alert(err.message);
  }
});

// Initial load
loadCases();
