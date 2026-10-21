const CASE_SESSION_API_URL = window.API_URL || 'http://localhost:8000';

async function loadCaseSessionOptions() {
  const caseSelect = document.getElementById('caseNameSelect');
  const sessionSelect = document.getElementById('caseSessionSelect');
  if (!caseSelect) return;

  const response = await fetch(`${CASE_SESSION_API_URL}/case-session-options`);
  if (!response.ok) {
    throw new Error('Failed to load case names.');
  }

  const { cases } = await response.json();
  const pendingAnalysisId = sessionStorage.getItem('forensight-evidence-analysis');
  caseSelect.innerHTML = '<option value="">Select a case</option>';
  cases.forEach((item, index) => {
    const option = document.createElement('option');
    option.value = String(index);
    option.textContent = item.case_name;
    caseSelect.appendChild(option);
  });

  function getLatestSession(selectedCase) {
    return [...(selectedCase?.sessions || [])].sort((first, second) => (
      new Date(second.created_at || 0).getTime()
      - new Date(first.created_at || 0).getTime()
    ))[0];
  }

  function notifySelection(selectedCase, selectedSession) {
    const analysisInput = document.querySelector(
      '#evidenceAnalysisIdInput, #timelineAnalysisIdInput, #reportAnalysisIdInput, #aiAnalysisIdInput'
    );
    if (analysisInput) analysisInput.value = selectedSession?.analysis_id || '';
    document.dispatchEvent(new CustomEvent('caseSessionSelected', {
      detail: {
        caseName: selectedCase?.case_name || '',
        analysisId: selectedSession?.analysis_id || '',
        autoLoad: Boolean(
          pendingAnalysisId
          && selectedSession?.analysis_id === pendingAnalysisId
        ),
      },
    }));
    if (selectedSession?.analysis_id === pendingAnalysisId) {
      sessionStorage.removeItem('forensight-evidence-analysis');
    }
  }

  if (sessionSelect) {
    function populateSessions() {
      sessionSelect.innerHTML = '<option value="">Select a video</option>';
      const selectedCase = cases[Number(caseSelect.value)];
      (selectedCase?.sessions || []).forEach((session) => {
        const option = document.createElement('option');
        option.value = session.analysis_id;
        const isGeneratedName = /^[0-9a-f]{8}-[0-9a-f-]{27}\.[^.]+$/i
          .test(session.video_name || '');
        const videoName = session.video_name && !isGeneratedName
          ? session.video_name
          : 'Video';
        const analyzedAt = session.created_at
          ? new Date(session.created_at).toLocaleString()
          : 'Date unavailable';
        option.textContent = `${videoName} — ${analyzedAt}`;
        sessionSelect.appendChild(option);
      });
      sessionSelect.dispatchEvent(new Event('change'));
    }

    caseSelect.addEventListener('change', populateSessions);
    sessionSelect.addEventListener('change', () => {
      const selectedCase = cases[Number(caseSelect.value)];
      const selectedSession = selectedCase?.sessions.find(
        (session) => session.analysis_id === sessionSelect.value
      );
      notifySelection(selectedCase, selectedSession);
    });
  } else {
    caseSelect.addEventListener('change', () => {
      const selectedCase = cases[Number(caseSelect.value)];
      notifySelection(selectedCase, getLatestSession(selectedCase));
    });
  }

  if (cases.length) {
    const recent = JSON.parse(
      localStorage.getItem('forensight-recent-investigations') || '[]'
    );
    const requestedCaseName = new URLSearchParams(window.location.search)
      .get('caseName')
      ?.trim()
      .toLocaleLowerCase();
    const requestedCaseIndex = requestedCaseName
      ? cases.findIndex((item) => (
        item.case_name?.trim().toLocaleLowerCase() === requestedCaseName
      ))
      : -1;
    const mostRecentId = recent[0]?.id;
    const preferredCaseIndex = cases.findIndex((item) => (
      item.sessions.some((session) => (
        session.analysis_id === pendingAnalysisId
        || session.analysis_id === mostRecentId
      ))
    ));
    const selectedCaseIndex = requestedCaseIndex >= 0
      ? requestedCaseIndex
      : preferredCaseIndex >= 0
        ? preferredCaseIndex
        : 0;
    caseSelect.value = String(selectedCaseIndex);
    if (sessionSelect) {
      caseSelect.dispatchEvent(new Event('change'));
      const selectedCase = cases[selectedCaseIndex];
      const preferredSessionId = pendingAnalysisId
        && selectedCase.sessions.some(
          (session) => session.analysis_id === pendingAnalysisId
        )
        ? pendingAnalysisId
        : mostRecentId;
      if (preferredSessionId) sessionSelect.value = preferredSessionId;
      sessionSelect.dispatchEvent(new Event('change'));
    } else {
      caseSelect.dispatchEvent(new Event('change'));
    }
  }

  const caseNameByAnalysis = new Map();
  cases.forEach((item) => {
    item.sessions.forEach((session) => {
      caseNameByAnalysis.set(session.analysis_id, item.case_name);
    });
  });
  try {
    const recent = JSON.parse(
      localStorage.getItem('forensight-recent-investigations') || '[]'
    );
    localStorage.setItem(
      'forensight-recent-investigations',
      JSON.stringify(recent.map((item) => ({
        ...item,
        caseName: item.caseName || caseNameByAnalysis.get(item.id) || '',
      })))
    );
    document.dispatchEvent(new Event('caseNamesResolved'));
  } catch (error) {
    console.error('Could not update recent case names:', error);
  }
}

loadCaseSessionOptions().catch((error) => {
  console.error('Could not load case/video choices:', error);
});
