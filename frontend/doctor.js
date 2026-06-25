/**
 * ARIA Doctor Dashboard
 * 
 * Connects to Marlon's in-clinic-service backend:
 * - GET /patients → doctor's review queue (unviewed briefings, urgent first)
 * - POST /briefing → generate/regenerate a clinical briefing
 * - POST /diagnosis → AI diagnostic recommendation after doctor's exam
 * 
 * Base URL: https://jhn2lkbr66.execute-api.us-east-1.amazonaws.com
 */

// === API CONFIG ===
const API_BASE = 'https://jhn2lkbr66.execute-api.us-east-1.amazonaws.com';
// /briefing/reviewed lives on the consolidated aria-api gateway, not jhn2lkbr66.
const REVIEW_API_BASE = 'https://ju4c4od7u1.execute-api.us-east-1.amazonaws.com';

// Store all patients for filtering
let allPatients = [];

// Currently selected patient (for briefing detail view)
let selectedPatient = null;

// === LOAD ON PAGE OPEN ===
document.addEventListener('DOMContentLoaded', loadPatients);

async function loadPatients() {
    const container = document.getElementById('briefingsContainer');
    const loadingState = document.getElementById('loadingState');
    const emptyState = document.getElementById('emptyState');

    loadingState.classList.remove('hidden');
    emptyState.classList.add('hidden');

    try {
        const response = await fetch(`${API_BASE}/patients`);
        
        if (!response.ok) {
            throw new Error(`API returned ${response.status}`);
        }

        const data = await response.json();

        // Map API response fields to our card format
        allPatients = (data.patients || []).map(mapPatientFromAPI);
        renderBriefings(allPatients);
        updateStats(allPatients);

    } catch (err) {
        console.error('Failed to load from API, using mock data:', err);
        // Fallback to mock data so the demo always works
        allPatients = getMockBriefings();
        renderBriefings(allPatients);
        updateStats(allPatients);
    }

    loadingState.classList.add('hidden');
}

/**
 * Maps Marlon's API response (snake_case) to our frontend field names.
 * Also parses JSON-encoded arrays (recommended_actions, protocol_references).
 */
function mapPatientFromAPI(patient) {
    // Parse JSON-encoded arrays safely
    let actions = [];
    try {
        actions = typeof patient.recommended_actions === 'string' 
            ? JSON.parse(patient.recommended_actions) 
            : (patient.recommended_actions || []);
    } catch (e) { actions = []; }

    let protocols = [];
    try {
        protocols = typeof patient.protocol_references === 'string'
            ? JSON.parse(patient.protocol_references)
            : (patient.protocol_references || []);
    } catch (e) { protocols = []; }

    return {
        briefingId: patient.briefing_id,
        patientId: patient.patient_id,
        sessionId: patient.session_id,
        clinicId: patient.clinic_id,
        patientName: patient.patient_name,
        language: patient.preferred_language,
        interactionTime: patient.interaction_time,
        sessionType: patient.session_type,
        urgencyLevel: patient.urgency_level,
        sessionStatus: patient.session_status,
        chiefComplaint: patient.chief_complaint,
        severity: patient.severity,
        aiAssessment: patient.ai_assessment,
        recommendedActions: actions,
        protocolReferences: protocols,
        needsInPerson: patient.needs_in_person,
        flaggedForReview: patient.flagged_for_review,
        imageFinding: patient.image_finding,
        imageConfidence: patient.image_confidence,
        imageUrl: patient.image_url,
        processingStatus: patient.processing_status,
        reviewed: false
    };
}

// === RENDER PATIENT CARDS ===

function renderBriefings(patients) {
    const container = document.getElementById('briefingsContainer');
    const emptyState = document.getElementById('emptyState');
    const loadingState = document.getElementById('loadingState');

    loadingState.classList.add('hidden');

    // Clear existing cards
    const cards = container.querySelectorAll('.briefing-card');
    cards.forEach(c => c.remove());

    if (patients.length === 0) {
        emptyState.classList.remove('hidden');
        return;
    }

    emptyState.classList.add('hidden');

    patients.forEach(patient => {
        const card = createBriefingCard(patient);
        container.appendChild(card);
    });
}

function createBriefingCard(patient) {
    const severityColors = {
        'critical': { bg: 'bg-red-50', border: 'border-red-200', badge: 'bg-red-100 text-red-800', dot: 'bg-red-500' },
        'severe': { bg: 'bg-orange-50', border: 'border-orange-200', badge: 'bg-orange-100 text-orange-800', dot: 'bg-orange-500' },
        'moderate': { bg: 'bg-yellow-50', border: 'border-yellow-200', badge: 'bg-yellow-100 text-yellow-800', dot: 'bg-yellow-500' },
        'mild': { bg: 'bg-green-50', border: 'border-green-200', badge: 'bg-green-100 text-green-800', dot: 'bg-green-500' }
    };

    const colors = severityColors[patient.severity] || severityColors['moderate'];
    const timeAgo = getTimeAgo(patient.interactionTime);
    const severityDisplay = patient.severity || 'moderate';

    // Format recommended actions as a list
    const actionsHTML = Array.isArray(patient.recommendedActions) && patient.recommendedActions.length > 0
        ? `<ul class="list-disc list-inside space-y-1">${patient.recommendedActions.map(a => `<li class="text-sm text-gray-700">${a}</li>`).join('')}</ul>`
        : `<p class="text-sm text-gray-700">${patient.recommendedActions || 'Awaiting assessment'}</p>`;

    // Language display
    const langMap = { 'sw': 'Swahili', 'en': 'English', 'zu': 'Zulu', 'fr': 'French', 'ar': 'Arabic', 'am': 'Amharic' };
    const langDisplay = langMap[patient.language] || patient.language;

    const card = document.createElement('div');
    card.className = `briefing-card fade-in bg-white rounded-xl border ${colors.border} overflow-hidden cursor-pointer`;
    card.dataset.severity = patient.severity;
    card.onclick = () => openBriefingDetail(patient);

    card.innerHTML = `
        <!-- Card Header -->
        <div class="${colors.bg} px-5 py-3 flex items-center justify-between">
            <div class="flex items-center gap-3">
                <div class="w-2 h-2 ${colors.dot} rounded-full animate-pulse"></div>
                <span class="font-semibold text-gray-900">${patient.patientName}</span>
                <span class="text-xs text-gray-500">${langDisplay}</span>
            </div>
            <div class="flex items-center gap-2">
                <span class="px-2 py-0.5 rounded-full text-xs font-medium ${colors.badge}">
                    ${severityDisplay.toUpperCase()}
                </span>
                <span class="text-xs text-gray-500">${timeAgo}</span>
            </div>
        </div>

        <!-- Card Body -->
        <div class="px-5 py-4 space-y-3">
            <!-- Chief Complaint -->
            <div>
                <p class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Chief Complaint</p>
                <p class="text-sm font-medium text-gray-900">${patient.chiefComplaint}</p>
            </div>

            <!-- Session Type Badge -->
            <div class="flex items-center gap-2">
                <span class="px-2 py-0.5 rounded text-xs font-medium ${patient.sessionType === 'emergency' ? 'bg-red-50 text-red-700' : 'bg-blue-50 text-blue-700'}">
                    ${patient.sessionType === 'emergency' ? 'Emergency' : 'Non-Emergency'}
                </span>
                ${patient.imageFinding ? `<span class="px-2 py-0.5 rounded text-xs font-medium bg-purple-50 text-purple-700">Image: ${patient.imageFinding}</span>` : ''}
            </div>

            <!-- AI Assessment -->
            ${patient.aiAssessment ? `
            <div class="bg-gray-50 rounded-lg p-3">
                <p class="text-xs font-medium text-blue-600 mb-1">AI Assessment</p>
                <p class="text-sm text-gray-700">${patient.aiAssessment}</p>
            </div>
            ` : ''}

            <!-- Suggested Preparation (pre-exam) -->
            <div>
                <p class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Suggested Preparation <span class="normal-case text-gray-400">(before exam)</span></p>
                ${actionsHTML}
            </div>
        </div>

        <!-- Card Footer -->
        <div class="px-5 py-3 bg-gray-50 border-t border-gray-100 flex items-center justify-between">
            <span class="text-xs text-gray-500">Urgency: ${patient.urgencyLevel}/5</span>
            <div class="flex gap-2">
                <button onclick="event.stopPropagation(); openBriefingDetail(allPatients.find(p => p.sessionId === '${patient.sessionId}'))" 
                        class="px-3 py-1.5 bg-blue-600 text-white text-xs font-medium rounded-lg hover:bg-blue-700">
                    View Briefing
                </button>
                <button onclick="event.stopPropagation(); markReviewed('${patient.sessionId}')" 
                        class="px-3 py-1.5 bg-gray-200 text-gray-700 text-xs font-medium rounded-lg hover:bg-gray-300">
                    Dismiss
                </button>
            </div>
        </div>
    `;

    return card;
}

// === BRIEFING DETAIL VIEW ===

function openBriefingDetail(patient) {
    selectedPatient = patient;
    
    // Hide the queue, show the detail view
    document.getElementById('queueView').classList.add('hidden');
    document.getElementById('briefingDetail').classList.remove('hidden');

    // Populate detail view
    const detail = document.getElementById('briefingDetail');
    const severity = patient.severity || 'moderate';
    const severityColors = {
        'critical': 'bg-red-100 text-red-800',
        'severe': 'bg-orange-100 text-orange-800',
        'moderate': 'bg-yellow-100 text-yellow-800',
        'mild': 'bg-green-100 text-green-800'
    };
    const badge = severityColors[severity] || severityColors['moderate'];

    // Recommended actions as checklist
    const actionsChecklist = Array.isArray(patient.recommendedActions)
        ? patient.recommendedActions.map(a => `
            <label class="flex items-start gap-3 py-2">
                <input type="checkbox" class="mt-1 rounded border-gray-300 text-blue-600 focus:ring-blue-500">
                <span class="text-sm text-gray-700">${a}</span>
            </label>
        `).join('')
        : '<p class="text-sm text-gray-500">No actions specified</p>';

    // Protocol sources
    const protocolsHTML = patient.protocolReferences.length > 0
        ? patient.protocolReferences.map(p => `<span class="px-2 py-1 bg-gray-100 rounded text-xs text-gray-600">${p}</span>`).join(' ')
        : '';

    detail.innerHTML = `
        <!-- Back button -->
        <button onclick="closeBriefingDetail()" class="flex items-center gap-2 text-gray-500 hover:text-gray-900 mb-4">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
            </svg>
            <span class="text-sm font-medium">Back to queue</span>
        </button>

        <!-- Patient Header -->
        <div class="bg-white rounded-xl border border-gray-200 overflow-hidden mb-4">
            <div class="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
                <div>
                    <h2 class="text-lg font-bold text-gray-900">${patient.patientName}</h2>
                    <p class="text-sm text-gray-500">Language: ${patient.language} | ${patient.sessionType === 'emergency' ? 'Emergency' : 'Non-Emergency'}</p>
                </div>
                <span class="px-3 py-1 rounded-full text-sm font-medium ${badge}">${severity.toUpperCase()}</span>
            </div>

            <!-- Chief Complaint -->
            <div class="px-6 py-4 border-b border-gray-100">
                <p class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Chief Complaint</p>
                <p class="text-base text-gray-900 font-medium">${patient.chiefComplaint}</p>
            </div>

            <!-- AI Assessment -->
            ${patient.aiAssessment ? `
            <div class="px-6 py-4 border-b border-gray-100 bg-blue-50">
                <p class="text-xs font-medium text-blue-700 uppercase tracking-wide mb-2">AI Assessment</p>
                <p class="text-sm text-gray-800">${patient.aiAssessment}</p>
            </div>
            ` : ''}

            <!-- Suggested Preparation (pre-exam) -->
            <div class="px-6 py-4 border-b border-gray-100">
                <p class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">Suggested Preparation <span class="normal-case text-gray-400">(before you examine)</span></p>
                <div class="space-y-1">
                    ${actionsChecklist}
                </div>
            </div>

            <!-- Protocol Sources -->
            ${protocolsHTML ? `
            <div class="px-6 py-3 border-b border-gray-100">
                <p class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">Protocol Sources</p>
                <div class="flex flex-wrap gap-2">${protocolsHTML}</div>
            </div>
            ` : ''}

            <!-- Image finding (if present) -->
            ${patient.imageFinding ? `
            <div class="px-6 py-4 border-b border-gray-100">
                <p class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Image Analysis</p>
                <p class="text-sm text-gray-700">${patient.imageFinding} (confidence: ${(patient.imageConfidence * 100).toFixed(0)}%)</p>
            </div>
            ` : ''}
        </div>

        <!-- Examination Remarks Form -->
        <div class="bg-white rounded-xl border border-gray-200 p-6 mb-4">
            <h3 class="font-semibold text-gray-900 mb-3">Examination Remarks</h3>
            <p class="text-xs text-gray-500 mb-3">After examining the patient, enter your clinical findings. ARIA will provide a diagnostic recommendation.</p>
            <textarea id="clinicianRemarks" 
                      class="w-full h-28 px-4 py-3 border border-gray-200 rounded-xl text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                      placeholder="e.g. BP 150/95, oedema noted in lower extremities, patient reports persistent headache..."></textarea>
            <button onclick="submitDiagnosis()" 
                    id="diagnosisBtn"
                    class="mt-3 w-full py-3 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 active:scale-[0.98] transition-transform">
                Get AI Diagnostic Recommendation
            </button>
        </div>

        <!-- Diagnosis Result (hidden until submitted) -->
        <div id="diagnosisResult" class="hidden"></div>

        <!-- Finalize Consultation panel (hidden until a diagnosis is shown) -->
        <div id="finalizePanel" class="hidden mt-4"></div>

        <!-- Disclaimer -->
        <p class="text-xs text-gray-400 text-center mt-4">
            This is AI-generated decision support for a licensed clinician. It is not a diagnosis and must be reviewed before any action is taken.
        </p>
    `;
}

function closeBriefingDetail() {
    document.getElementById('queueView').classList.remove('hidden');
    document.getElementById('briefingDetail').classList.add('hidden');
    selectedPatient = null;
}

// === DIAGNOSIS SUBMISSION ===

async function submitDiagnosis() {
    const remarks = document.getElementById('clinicianRemarks').value.trim();
    if (!remarks) {
        alert('Please enter your examination findings before submitting.');
        return;
    }

    const btn = document.getElementById('diagnosisBtn');
    btn.textContent = 'Analyzing...';
    btn.disabled = true;
    btn.classList.add('opacity-50');

    try {
        const response = await fetch(`${API_BASE}/diagnosis`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                briefing_id: selectedPatient.briefingId,
                clinician_remarks: remarks
            })
        });

        if (!response.ok) throw new Error(`API returned ${response.status}`);

        const data = await response.json();
        renderDiagnosisResult(data);

    } catch (err) {
        console.error('Diagnosis API error:', err);
        document.getElementById('diagnosisResult').innerHTML = `
            <div class="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">
                Failed to get diagnostic recommendation. Please try again.
            </div>
        `;
        document.getElementById('diagnosisResult').classList.remove('hidden');
    }

    btn.textContent = 'Get AI Diagnostic Recommendation';
    btn.disabled = false;
    btn.classList.remove('opacity-50');
}

function renderDiagnosisResult(data) {
    const resultDiv = document.getElementById('diagnosisResult');
    const diagnosis = data.diagnosis;

    const severityColors = {
        'critical': 'bg-red-100 text-red-800',
        'severe': 'bg-orange-100 text-orange-800',
        'moderate': 'bg-yellow-100 text-yellow-800',
        'mild': 'bg-green-100 text-green-800'
    };
    const badge = severityColors[diagnosis.severity] || severityColors['moderate'];

    // Actions list
    const actionsHTML = (diagnosis.ai_diagnosis_actions || [])
        .map(a => `<li class="text-sm text-gray-700">${a}</li>`)
        .join('');

    // Divergence banner (the key safety feature)
    const divergenceBanner = diagnosis.agreement_with_clinician === 'diverges' ? `
        <div class="bg-amber-50 border-2 border-amber-300 rounded-xl p-4 mb-4">
            <div class="flex items-center gap-2 mb-2">
                <svg class="w-5 h-5 text-amber-600" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
                </svg>
                <span class="font-semibold text-amber-800">AI Assessment Diverges from Clinician Findings</span>
            </div>
            <p class="text-sm text-amber-700">${diagnosis.divergence_note}</p>
        </div>
    ` : '';

    // Protocol sources
    const sourcesHTML = (data.protocol_sources || [])
        .map(s => `<a href="${s}" target="_blank" class="text-xs text-blue-600 hover:underline block truncate">${s.split('/').pop()}</a>`)
        .join('');

    resultDiv.innerHTML = `
        ${divergenceBanner}
        <div class="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div class="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
                <h3 class="font-semibold text-gray-900">AI Diagnostic Recommendation</h3>
                <span class="px-3 py-1 rounded-full text-xs font-medium ${badge}">${diagnosis.severity.toUpperCase()}</span>
            </div>

            <div class="px-6 py-4 border-b border-gray-100">
                <p class="text-sm text-gray-800">${diagnosis.ai_diagnosis}</p>
            </div>

            <div class="px-6 py-4 border-b border-gray-100">
                <p class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">Recommended Management <span class="normal-case text-gray-400">(based on your findings)</span></p>
                <ol class="list-decimal list-inside space-y-1">
                    ${actionsHTML}
                </ol>
            </div>

            ${sourcesHTML ? `
            <div class="px-6 py-3 border-b border-gray-100">
                <p class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">Sources</p>
                ${sourcesHTML}
            </div>
            ` : ''}

            <div class="px-6 py-3 bg-gray-50">
                <p class="text-xs text-gray-400">${data.disclaimer || 'AI-generated decision support. Not a diagnosis.'}</p>
            </div>
        </div>
    `;

    resultDiv.classList.remove('hidden');

    // Now that the doctor has the AI recommendation, show the finalize panel.
    renderFinalizePanel();
}

// === FINALIZE CONSULTATION (decision + prescription + follow-up + notify) ===

function renderFinalizePanel() {
    const panel = document.getElementById('finalizePanel');
    panel.innerHTML = `
        <div class="bg-white rounded-xl border border-gray-200 p-6">
            <h3 class="font-semibold text-gray-900 mb-4">Finalize Consultation</h3>

            <!-- Decision -->
            <p class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">Your decision on the AI recommendation</p>
            <div class="flex gap-2 mb-4">
                <label class="flex-1">
                    <input type="radio" name="decision" value="accepted" class="peer hidden" onchange="toggleModifiedRec()">
                    <span class="block text-center text-sm py-2 rounded-lg border border-gray-200 cursor-pointer peer-checked:bg-green-600 peer-checked:text-white peer-checked:border-green-600">Accept</span>
                </label>
                <label class="flex-1">
                    <input type="radio" name="decision" value="modified" class="peer hidden" onchange="toggleModifiedRec()">
                    <span class="block text-center text-sm py-2 rounded-lg border border-gray-200 cursor-pointer peer-checked:bg-amber-500 peer-checked:text-white peer-checked:border-amber-500">Modify</span>
                </label>
                <label class="flex-1">
                    <input type="radio" name="decision" value="rejected" class="peer hidden" onchange="toggleModifiedRec()">
                    <span class="block text-center text-sm py-2 rounded-lg border border-gray-200 cursor-pointer peer-checked:bg-red-600 peer-checked:text-white peer-checked:border-red-600">Reject</span>
                </label>
            </div>

            <!-- Modified recommendation (only when Modify) -->
            <div id="modifiedRecWrap" class="hidden mb-4">
                <label class="text-xs font-medium text-gray-500 uppercase tracking-wide">Your revised recommendation</label>
                <textarea id="modifiedRec" class="mt-1 w-full h-20 px-3 py-2 border border-gray-200 rounded-lg text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
                          placeholder="Describe the management you are recommending instead..."></textarea>
            </div>

            <!-- Prescriptions -->
            <div class="mb-4">
                <div class="flex items-center justify-between mb-2">
                    <p class="text-xs font-medium text-gray-500 uppercase tracking-wide">Prescription</p>
                    <button onclick="addPrescriptionRow()" class="text-xs text-blue-600 font-medium hover:underline">+ Add medication</button>
                </div>
                <div id="rxRows" class="space-y-2"></div>
            </div>

            <!-- Follow-up -->
            <div class="mb-4">
                <p class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">Follow-up visit (optional)</p>
                <div class="flex gap-2">
                    <input type="date" id="followUpDate" class="px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
                    <input type="text" id="followUpReason" placeholder="Reason (e.g. BP review)" class="flex-1 px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
                </div>
            </div>

            <button onclick="finalizeConsultation()" id="finalizeBtn"
                    class="w-full py-3 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 active:scale-[0.98] transition-transform">
                Finalize &amp; Draft Patient Message
            </button>
        </div>

        <!-- Draft / send result -->
        <div id="finalizeResult" class="hidden mt-4"></div>
    `;
    panel.classList.remove('hidden');
    addPrescriptionRow();  // start with one empty row
}

function toggleModifiedRec() {
    const decision = document.querySelector('input[name="decision"]:checked')?.value;
    document.getElementById('modifiedRecWrap').classList.toggle('hidden', decision !== 'modified');
}

function addPrescriptionRow() {
    const row = document.createElement('div');
    row.className = 'rx-row grid grid-cols-12 gap-2 items-center';
    row.innerHTML = `
        <input type="text" class="rx-drug col-span-3 px-2 py-1.5 border border-gray-200 rounded text-sm" placeholder="Drug">
        <input type="text" class="rx-dosage col-span-2 px-2 py-1.5 border border-gray-200 rounded text-sm" placeholder="Dose">
        <input type="text" class="rx-frequency col-span-2 px-2 py-1.5 border border-gray-200 rounded text-sm" placeholder="Frequency">
        <input type="text" class="rx-duration col-span-2 px-2 py-1.5 border border-gray-200 rounded text-sm" placeholder="Duration">
        <input type="text" class="rx-instructions col-span-2 px-2 py-1.5 border border-gray-200 rounded text-sm" placeholder="Notes">
        <button onclick="this.parentElement.remove()" class="col-span-1 text-gray-400 hover:text-red-600 text-lg leading-none">&times;</button>
    `;
    document.getElementById('rxRows').appendChild(row);
}

function collectPrescriptions() {
    return [...document.querySelectorAll('#rxRows .rx-row')].map(r => ({
        drug_name: r.querySelector('.rx-drug').value.trim(),
        dosage: r.querySelector('.rx-dosage').value.trim(),
        frequency: r.querySelector('.rx-frequency').value.trim(),
        duration: r.querySelector('.rx-duration').value.trim(),
        instructions: r.querySelector('.rx-instructions').value.trim(),
    })).filter(rx => rx.drug_name);
}

async function finalizeConsultation() {
    const decision = document.querySelector('input[name="decision"]:checked')?.value;
    if (!decision) {
        alert('Please choose a decision: Accept, Modify, or Reject.');
        return;
    }
    const modifiedRec = decision === 'modified'
        ? document.getElementById('modifiedRec').value.trim()
        : null;
    const date = document.getElementById('followUpDate').value;
    const reason = document.getElementById('followUpReason').value.trim();
    const followUp = date ? { scheduled_date: date, reason } : {};

    const payload = {
        briefing_id: selectedPatient.briefingId,
        clinician_decision: decision,
        clinician_modified_recommendation: modifiedRec,
        prescriptions: collectPrescriptions(),
        follow_up: followUp
    };

    const btn = document.getElementById('finalizeBtn');
    btn.textContent = 'Drafting message...';
    btn.disabled = true;
    btn.classList.add('opacity-50');

    try {
        const resp = await fetch(`${API_BASE}/consultation/finalize`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!resp.ok) throw new Error(`API returned ${resp.status}`);
        const data = await resp.json();
        renderDraft(data);
    } catch (err) {
        console.error('Finalize error:', err);
        const el = document.getElementById('finalizeResult');
        el.innerHTML = `<div class="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">Failed to finalize. Please try again.</div>`;
        el.classList.remove('hidden');
    }

    btn.textContent = 'Finalize & Draft Patient Message';
    btn.disabled = false;
    btn.classList.remove('opacity-50');
}

function renderDraft(data) {
    const el = document.getElementById('finalizeResult');
    el.innerHTML = `
        <div class="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div class="px-6 py-3 border-b border-gray-100 flex items-center justify-between">
                <h3 class="font-semibold text-gray-900">Patient Message — Draft</h3>
                <span class="text-xs text-gray-500">Language: ${data.language || 'en'} | To: ${data.recipient || 'no email on file'}</span>
            </div>
            <div class="px-6 py-4 border-b border-gray-100">
                <p class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">Message to patient (their language)</p>
                <pre class="text-sm text-gray-800 whitespace-pre-wrap font-sans">${data.summary_translated || data.summary_en}</pre>
            </div>
            <div class="px-6 py-3 bg-gray-50 flex items-center justify-between">
                <span class="text-xs text-gray-500">Review the message, then send.</span>
                <button onclick="sendNotification('${data.notification_id}')" id="sendBtn"
                        class="px-4 py-2 bg-green-600 text-white text-sm font-medium rounded-lg hover:bg-green-700 disabled:opacity-50"
                        ${data.recipient ? '' : 'disabled title="No patient email on file"'}>
                    Send to Patient
                </button>
            </div>
        </div>
    `;
    el.classList.remove('hidden');
}

async function sendNotification(notificationId) {
    const btn = document.getElementById('sendBtn');
    btn.textContent = 'Sending...';
    btn.disabled = true;

    try {
        const resp = await fetch(`${API_BASE}/notification/send`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ notification_id: notificationId })
        });
        if (!resp.ok) throw new Error(`API returned ${resp.status}`);
        const data = await resp.json();
        btn.outerHTML = `<span class="text-sm font-medium text-green-700">✓ Sent to ${data.recipient}</span>`;
    } catch (err) {
        console.error('Send error:', err);
        btn.textContent = 'Send failed — retry';
        btn.disabled = false;
    }
}

// === UTILITY FUNCTIONS ===

function updateStats(patients) {
    const critical = patients.filter(p => p.severity === 'critical').length;
    const pending = patients.length;
    const total = patients.length;

    document.getElementById('criticalCount').textContent = critical;
    document.getElementById('pendingCount').textContent = pending;
    document.getElementById('totalCount').textContent = total;
}

function filterCards() {
    const filter = document.getElementById('filterSeverity').value;
    if (filter === 'all') {
        renderBriefings(allPatients);
    } else {
        renderBriefings(allPatients.filter(p => (p.severity || 'moderate') === filter));
    }
}

async function markReviewed(sessionId) {
    const patient = allPatients.find(p => p.sessionId === sessionId);
    if (!patient) return;

    // Persist the dismissal first, so the card stays gone after a refresh.
    // (GET /patients only returns briefings where viewed_by_clinician = false.)
    try {
        const resp = await fetch(`${REVIEW_API_BASE}/briefing/reviewed`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ briefing_id: patient.briefingId })
        });
        if (!resp.ok) throw new Error(`API returned ${resp.status}`);
    } catch (err) {
        console.error('Failed to mark reviewed:', err);
        alert('Could not dismiss this briefing — please try again.');
        return; // leave the card in place on failure
    }

    // Success → remove the card from the UI.
    const cards = document.querySelectorAll('.briefing-card');
    cards.forEach(card => {
        if (card.querySelector(`button[onclick*="${sessionId}"]`)) {
            card.style.opacity = '0.5';
            card.style.transition = 'opacity 0.3s';
            setTimeout(() => card.remove(), 300);
        }
    });

    allPatients = allPatients.filter(p => p.sessionId !== sessionId);
    updateStats(allPatients);
}

function getTimeAgo(timestamp) {
    if (!timestamp) return 'Just now';
    const now = new Date();
    const then = new Date(timestamp);
    const diffMin = Math.floor((now - then) / 60000);

    if (diffMin < 1) return 'Just now';
    if (diffMin < 60) return `${diffMin}m ago`;
    if (diffMin < 1440) return `${Math.floor(diffMin / 60)}h ago`;
    return `${Math.floor(diffMin / 1440)}d ago`;
}

// === MOCK DATA (fallback when API is unavailable) ===

function getMockBriefings() {
    return [
        // {
        //     briefingId: '33333333-3333-3333-3333-333333333333',
        //     patientId: '11111111-1111-1111-1111-111111111111',
        //     sessionId: 'sess-001',
        //     clinicId: '99999999-9999-9999-9999-999999999999',
        //     patientName: 'Amara Wanjiku',
        //     language: 'sw',
        //     interactionTime: new Date(Date.now() - 5 * 60000).toISOString(),
        //     sessionType: 'emergency',
        //     urgencyLevel: 5,
        //     sessionStatus: 'active',
        //     chiefComplaint: 'Heavy vaginal bleeding with severe abdominal pain at 28 weeks gestation',
        //     severity: 'critical',
        //     aiAssessment: 'Critical obstetric emergency. Possible abruptio placentae, ruptured uterus, or placenta previa. The combination of symptoms meets red flag criteria for immediate escalation.',
        //     recommendedActions: ['Assess vital signs and check for shock', 'Start IV, cross-match blood', 'Assess fetal heart sounds', 'Do NOT perform vaginal examination until placenta previa is ruled out'],
        //     protocolReferences: ['OB_001', 'MCPC-2nd-ed.pdf'],
        //     needsInPerson: true,
        //     flaggedForReview: true,
        //     imageFinding: null,
        //     imageConfidence: null,
        //     imageUrl: null,
        //     processingStatus: 'complete',
        //     reviewed: false
        // },
        // {
        //     briefingId: '66666666-6666-6666-6666-666666666666',
        //     patientId: '44444444-4444-4444-4444-444444444444',
        //     sessionId: 'sess-002',
        //     clinicId: '99999999-9999-9999-9999-999999999999',
        //     patientName: 'Juma Ochieng',
        //     language: 'sw',
        //     interactionTime: new Date(Date.now() - 12 * 60000).toISOString(),
        //     sessionType: 'non_emergency',
        //     urgencyLevel: 2,
        //     sessionStatus: 'active',
        //     chiefComplaint: 'Burn on left forearm, blistering',
        //     severity: 'moderate',
        //     aiAssessment: 'Partial-thickness burn to the forearm. Clean and dress; assess depth and surface area.',
        //     recommendedActions: ['Cool with clean running water', 'Cover with clean dressing', 'Assess depth and % body surface area'],
        //     protocolReferences: ['who-emergency-triage.md'],
        //     needsInPerson: true,
        //     flaggedForReview: false,
        //     imageFinding: 'partial-thickness burn',
        //     imageConfidence: 0.88,
        //     imageUrl: null,
        //     processingStatus: 'complete',
        //     reviewed: false
        // }
    ];
}
