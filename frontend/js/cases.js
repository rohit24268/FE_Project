const API_URL = window.API_URL || 'http://localhost:8000';
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

  casesList.innerHTML = cases.map((c) => {
    const createdDate = formatDate(c.created_at);
    const analysisCount = c.analysis_count ?? (c.analysis_ids || []).length;
    const caseTitle = c.title || c.case_name || 'Untitled Case';

    return `
      <div class="case-card">
        <div class="case-card-main">
          <div class="case-card-meta">
            <h3>${escapeHtml(caseTitle)}</h3>
            <span class="threat-pill ${c.status === 'open' ? 'safe' : 'medium'}">${escapeHtml((c.status || 'OPEN').toUpperCase())}</span>
          </div>
          <p>${escapeHtml(c.description || 'No description provided.')}</p>
          <div class="case-card-details">
            <span><strong>Investigator:</strong> ${escapeHtml(c.investigator || 'Unassigned')}</span>
            <span><strong>Created:</strong> ${createdDate}</span>
            <span><strong>Analyses:</strong> ${analysisCount}</span>
          </div>
          <form class="case-edit-form hidden" data-case-id="${escapeHtml(c.case_id)}">
            <div class="form-group">
              <label for="investigator-${escapeHtml(c.case_id)}">Assign Investigator</label>
              <input type="text" id="investigator-${escapeHtml(c.case_id)}" name="investigator" value="${escapeHtml(c.investigator || '')}" placeholder="Enter investigator name" />
            </div>
            <div class="form-group">
              <label for="description-${escapeHtml(c.case_id)}">Case Description</label>
              <textarea id="description-${escapeHtml(c.case_id)}" name="description" rows="3" placeholder="Add a case description">${escapeHtml(c.description || '')}</textarea>
            </div>
            <p class="inline-error hidden case-edit-error" role="alert"></p>
            <div class="case-edit-actions">
              <button type="submit" class="primary-btn">Save Changes</button>
              <button type="button" class="secondary-btn case-edit-cancel">Cancel</button>
            </div>
          </form>
          <div class="case-details hidden" id="case-details-${escapeHtml(c.case_id)}"></div>
        </div>
        <div class="case-card-actions">
          <div class="case-primary-actions">
            <button type="button" class="secondary-btn case-edit-btn" aria-expanded="false">
              Edit Details
            </button>
            <button type="button" class="secondary-btn case-details-btn" data-case-id="${escapeHtml(c.case_id)}" aria-expanded="false">
              View Details
            </button>
          </div>
          <button type="button" class="case-delete-btn" data-case-id="${escapeHtml(c.case_id)}" data-case-title="${escapeHtml(caseTitle)}">
            Delete
          </button>
        </div>
      </div>
    `;
  }).join('');
}

function renderCaseDetails(details) {
  const analyses = details.analyses || [];
  const caseName = details.case?.title || details.case?.case_name;
  if (!analyses.length) {
    return '<p class="empty-state">No saved video analyses for this case.</p>';
  }

  return analyses.map((analysis) => {
    const threat = analysis.threat_analysis || {};
    const threatLevel = (threat.overall_threat_level || 'UNKNOWN').toUpperCase();
    const objectCounts = Object.entries(analysis.object_counts || {})
      .map(([name, count]) => `${escapeHtml(name)}: ${escapeHtml(count)}`)
      .join(', ') || 'No object summary available';
    const links = [
      analysis.annotated_video_url
        ? `<a class="secondary-btn" href="${API_URL}${analysis.annotated_video_url}" target="_blank" rel="noreferrer">View Video</a>`
        : '',
      caseName
        ? `<a class="secondary-btn" href="reports.html?caseName=${encodeURIComponent(caseName)}">Generate Report</a>`
        : '',
    ].filter(Boolean).join('');

    return `
      <article class="case-analysis-detail">
        <h4>Analysis from ${escapeHtml(formatDate(analysis.created_at))}</h4>
        <div class="case-card-details">
          <span><strong>Detections:</strong> ${escapeHtml(analysis.total_detections ?? 0)}</span>
          <span><strong>Threat level:</strong> ${escapeHtml(threatLevel)}</span>
          <span><strong>Threat score:</strong> ${Math.round(Number(threat.max_threat_score || 0) * 100)}%</span>
        </div>
        <p><strong>Objects:</strong> ${objectCounts}</p>
        <div class="case-detail-actions">${links}</div>
      </article>
    `;
  }).join('');
}

if (casesList) casesList.addEventListener('click', async (event) => {
  const editButton = event.target.closest('.case-edit-btn');
  if (editButton) {
    const card = editButton.closest('.case-card');
    const editForm = card?.querySelector('.case-edit-form');
    if (!editForm) return;
    editForm.classList.toggle('hidden');
    const expanded = !editForm.classList.contains('hidden');
    editButton.textContent = expanded ? 'Close Edit' : 'Edit Details';
    editButton.setAttribute('aria-expanded', String(expanded));
    return;
  }

  if (event.target.closest('.case-edit-cancel')) {
    const card = event.target.closest('.case-card');
    const editForm = card?.querySelector('.case-edit-form');
    const editButton = card?.querySelector('.case-edit-btn');
    if (editForm) editForm.classList.add('hidden');
    if (editButton) {
      editButton.textContent = 'Edit Details';
      editButton.setAttribute('aria-expanded', 'false');
    }
    return;
  }

  const deleteButton = event.target.closest('.case-delete-btn');
  if (deleteButton) {
    const caseId = deleteButton.dataset.caseId;
    const caseTitle = deleteButton.dataset.caseTitle;
    const confirmed = window.confirm(
      `Delete "${caseTitle}" and all linked analyses, reports, evidence, and stored files? This cannot be undone.`
    );
    if (!confirmed) return;

    deleteButton.disabled = true;
    deleteButton.textContent = 'Deleting...';
    try {
      const response = await fetch(`${API_URL}/cases/${encodeURIComponent(caseId)}`, {
        method: 'DELETE'
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || 'Failed to delete case.');
      }
      await loadCases();
    } catch (error) {
      deleteButton.disabled = false;
      deleteButton.textContent = 'Delete';
      alert(`Error deleting case: ${error.message}`);
    }
    return;
  }

  const button = event.target.closest('.case-details-btn');
  if (!button) return;

  const caseId = button.dataset.caseId;
  const detailsPanel = document.getElementById(`case-details-${caseId}`);
  if (!detailsPanel) return;

  if (!detailsPanel.classList.contains('hidden')) {
    detailsPanel.classList.add('hidden');
    button.textContent = 'View Details';
    button.setAttribute('aria-expanded', 'false');
    return;
  }

  button.disabled = true;
  button.textContent = 'Loading...';
  detailsPanel.classList.remove('hidden');
  detailsPanel.innerHTML = '<p class="empty-state">Loading case details...</p>';
  try {
    const response = await fetch(`${API_URL}/cases/${encodeURIComponent(caseId)}/details`);
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || 'Failed to load case details.');
    }
    const details = await response.json();
    detailsPanel.innerHTML = renderCaseDetails(details);
    button.textContent = 'Hide Details';
    button.setAttribute('aria-expanded', 'true');
  } catch (error) {
    detailsPanel.innerHTML = `<p class="inline-error">Error loading details: ${escapeHtml(error.message)}</p>`;
    button.textContent = 'Retry Details';
    button.setAttribute('aria-expanded', 'true');
  } finally {
    button.disabled = false;
  }
});

if (casesList) casesList.addEventListener('submit', async (event) => {
  const editForm = event.target.closest('.case-edit-form');
  if (!editForm) return;
  event.preventDefault();

  const saveButton = editForm.querySelector('button[type="submit"]');
  const errorMessage = editForm.querySelector('.case-edit-error');
  const payload = {
    investigator: editForm.elements.investigator.value.trim(),
    description: editForm.elements.description.value.trim(),
  };
  saveButton.disabled = true;
  saveButton.textContent = 'Saving...';
  errorMessage.classList.add('hidden');

  try {
    const response = await fetch(
      `${API_URL}/cases/${encodeURIComponent(editForm.dataset.caseId)}`,
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      }
    );
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || 'Failed to update case details.');
    }
    await loadCases();
  } catch (error) {
    errorMessage.textContent = `Error saving case: ${error.message}`;
    errorMessage.classList.remove('hidden');
  } finally {
    saveButton.disabled = false;
    saveButton.textContent = 'Save Changes';
  }
});

if (createCaseForm) {
  createCaseForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const nameInput = document.getElementById('caseNameInput');
    const investigatorInput = document.getElementById('caseInvestigatorInput');
    const descInput = document.getElementById('caseDescriptionInput');

    const payload = {
      title: nameInput.value.trim(),
      case_name: nameInput.value.trim(),
      investigator: investigatorInput.value.trim(),
      description: descInput.value.trim(),
      status: 'open'
    };

    try {
      const res = await fetch(`${API_URL}/cases`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        let msg = errorData.detail;
        if (Array.isArray(msg)) msg = msg.map(m => m.msg).join(', ');
        throw new Error(msg || 'Failed to create case.');
      }

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

// Initial load
loadCases();
