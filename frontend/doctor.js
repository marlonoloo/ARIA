/**
 * ARIA Doctor Dashboard
 * 
 * Fetches patient briefings from Aurora (via API Gateway + Lambda)
 * and displays them as cards sorted by urgency.
 * 
 * For PoC: Uses the RDS Data API via a dedicated Lambda endpoint.
 * In production: This would use the doctor_dashboard view with proper auth.
 */

// === CONFIGURE ===
const DOCTOR_API_ENDPOINT = 'https://5lujwlh8lf.execute-api.us-east-1.amazonaws.com/dev/briefings';

// Store all briefings for filtering
let allBriefings = [];

// === LOAD ON PAGE OPEN ===
document.addEventListener('DOMContentLoaded', loadBriefings);

async function loadBriefings() {
    const container = document.getElementById('briefingsContainer');
    const loadingState = document.getElementById('loadingState');
    const emptyState = document.getElementById('emptyState');

    loadingState.classList.remove('hidden');
    emptyState.classList.add('hidden');

    try {
        const response = await fetch(DOCTOR_API_ENDPOINT);
        const data = await response.json();

        allBriefings = data.briefings || [];
        renderBriefings(allBriefings);
        updateStats(allBriefings);

    } catch (err) {
        console.error('Failed to load briefings:', err);
        // Show mock data for demo purposes
        allBriefings = getMockBriefings();
        renderBriefings(allBriefings);
        updateStats(allBriefings);
    }

    loadingState.classList.add('hidden');
}

function renderBriefings(briefings) {
    const container = document.getElementById('briefingsContainer');
    const emptyState = document.getElementById('emptyState');
    const loadingState = document.getElementById('loadingState');

    // Remove loading
    loadingState.classList.add('hidden');

    // Clear existing cards (keep loading/empty states)
    const cards = container.querySelectorAll('.briefing-card');
    cards.forEach(c => c.remove());

    if (briefings.length === 0) {
        emptyState.classList.remove('hidden');
        return;
    }

    emptyState.classList.add('hidden');

    briefings.forEach(briefing => {
        const card = createBriefingCard(briefing);
        container.appendChild(card);
    });
}

function createBriefingCard(briefing) {
    const severityColors = {
        'critical': { bg: 'bg-red-50', border: 'border-red-200', badge: 'bg-red-100 text-red-800', dot: 'bg-red-500' },
        'severe': { bg: 'bg-orange-50', border: 'border-orange-200', badge: 'bg-orange-100 text-orange-800', dot: 'bg-orange-500' },
        'moderate': { bg: 'bg-yellow-50', border: 'border-yellow-200', badge: 'bg-yellow-100 text-yellow-800', dot: 'bg-yellow-500' },
        'mild': { bg: 'bg-green-50', border: 'border-green-200', badge: 'bg-green-100 text-green-800', dot: 'bg-green-500' }
    };

    const colors = severityColors[briefing.severity] || severityColors['moderate'];
    const timeAgo = getTimeAgo(briefing.timestamp);

    const card = document.createElement('div');
    card.className = `briefing-card fade-in bg-white rounded-xl border ${colors.border} overflow-hidden`;
    card.dataset.severity = briefing.severity;

    card.innerHTML = `
        <!-- Card Header -->
        <div class="${colors.bg} px-5 py-3 flex items-center justify-between">
            <div class="flex items-center gap-3">
                <div class="w-2 h-2 ${colors.dot} rounded-full animate-pulse"></div>
                <span class="font-semibold text-aria-dark">${briefing.patientName}</span>
                <span class="text-xs text-gray-500">${briefing.language || ''}</span>
            </div>
            <div class="flex items-center gap-2">
                <span class="px-2 py-0.5 rounded-full text-xs font-medium ${colors.badge}">
                    ${briefing.severity.toUpperCase()}
                </span>
                <span class="text-xs text-gray-500">${timeAgo}</span>
            </div>
        </div>

        <!-- Card Body -->
        <div class="px-5 py-4 space-y-3">
            <!-- Chief Complaint -->
            <div>
                <p class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Chief Complaint</p>
                <p class="text-sm text-aria-dark">${briefing.chiefComplaint}</p>
            </div>

            <!-- Location -->
            <div class="flex items-center gap-2">
                <svg class="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M15 10.5a3 3 0 11-6 0 3 3 0 016 0z" />
                    <path stroke-linecap="round" stroke-linejoin="round" d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1115 0z" />
                </svg>
                <span class="text-sm text-gray-600">${briefing.location}</span>
            </div>

            <!-- AI Assessment -->
            ${briefing.aiAssessment ? `
            <div class="bg-gray-50 rounded-lg p-3">
                <p class="text-xs font-medium text-aria-primary mb-1">AI Assessment</p>
                <p class="text-sm text-gray-700">${briefing.aiAssessment}</p>
            </div>
            ` : ''}

            <!-- Recommended Actions -->
            ${briefing.recommendedActions ? `
            <div>
                <p class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Recommended Actions</p>
                <p class="text-sm text-gray-700">${briefing.recommendedActions}</p>
            </div>
            ` : ''}
        </div>

        <!-- Card Footer -->
        <div class="px-5 py-3 bg-gray-50 border-t border-gray-100 flex items-center justify-between">
            <span class="text-xs text-gray-500">Urgency: ${briefing.urgencyLevel}/5</span>
            <button onclick="markReviewed('${briefing.sessionId}')" 
                    class="px-3 py-1.5 bg-aria-primary text-white text-xs font-medium rounded-lg hover:bg-teal-700">
                Mark Reviewed
            </button>
        </div>
    `;

    return card;
}

function updateStats(briefings) {
    const critical = briefings.filter(b => b.severity === 'critical').length;
    const pending = briefings.filter(b => !b.reviewed).length;

    document.getElementById('criticalCount').textContent = critical;
    document.getElementById('pendingCount').textContent = pending;
    document.getElementById('totalCount').textContent = briefings.length;
}

function filterCards() {
    const filter = document.getElementById('filterSeverity').value;
    if (filter === 'all') {
        renderBriefings(allBriefings);
    } else {
        renderBriefings(allBriefings.filter(b => b.severity === filter));
    }
}

function markReviewed(sessionId) {
    // Remove the card visually
    const cards = document.querySelectorAll('.briefing-card');
    cards.forEach(card => {
        if (card.querySelector(`button[onclick*="${sessionId}"]`)) {
            card.style.opacity = '0.5';
            card.style.transition = 'opacity 0.3s';
            setTimeout(() => card.remove(), 300);
        }
    });

    // Update stats
    allBriefings = allBriefings.filter(b => b.sessionId !== sessionId);
    updateStats(allBriefings);

    // TODO: Call API to mark as reviewed in DB
    // fetch(`${DOCTOR_API_ENDPOINT}/reviewed`, { method: 'POST', body: JSON.stringify({ sessionId }) });
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

// === MOCK DATA (used when API isn't connected yet) ===

function getMockBriefings() {
    return [
        {
            sessionId: 'sess-001',
            patientName: 'Amara Wanjiku',
            severity: 'critical',
            urgencyLevel: 5,
            chiefComplaint: 'Water broke, severe cramping and bleeding. 38 weeks pregnant.',
            location: 'Westlands, Nairobi',
            language: 'Swahili',
            aiAssessment: 'Possible premature rupture of membranes (PROM) with hemorrhage. High risk of cord prolapse given active bleeding.',
            recommendedActions: 'Prepare delivery room. Have blood type cross-matched. Monitor fetal heart rate immediately on arrival.',
            timestamp: new Date(Date.now() - 5 * 60000).toISOString(),
            reviewed: false
        },
        {
            sessionId: 'sess-002',
            patientName: 'Fatima Hassan',
            severity: 'severe',
            urgencyLevel: 4,
            chiefComplaint: 'Intense abdominal pain, dizziness, spotting. 12 weeks pregnant.',
            location: 'Kisumu CBD',
            language: 'Swahili',
            aiAssessment: 'Symptoms consistent with threatened miscarriage or ectopic pregnancy. Dizziness suggests possible internal bleeding.',
            recommendedActions: 'Urgent ultrasound to confirm pregnancy location. Check hemoglobin. Prepare for possible surgical intervention.',
            timestamp: new Date(Date.now() - 12 * 60000).toISOString(),
            reviewed: false
        },
        {
            sessionId: 'sess-003',
            patientName: 'Grace Mutua',
            severity: 'moderate',
            urgencyLevel: 3,
            chiefComplaint: 'Regular contractions every 8 minutes. 36 weeks. First pregnancy.',
            location: 'Thika Road, Nairobi',
            language: 'English',
            aiAssessment: 'Early labor signs at 36 weeks (late preterm). Contractions regular but not yet in active labor phase.',
            recommendedActions: 'Monitor contraction frequency. Prepare NICU awareness for preterm delivery. Standard admission protocol.',
            timestamp: new Date(Date.now() - 25 * 60000).toISOString(),
            reviewed: false
        },
        {
            sessionId: 'sess-004',
            patientName: 'Zainab Ochieng',
            severity: 'mild',
            urgencyLevel: 2,
            chiefComplaint: 'Mild cramping and back pain. 32 weeks. No bleeding.',
            location: 'Mombasa Road',
            language: 'Swahili',
            aiAssessment: 'Likely Braxton Hicks contractions. No red flags present. Patient reports normal fetal movement.',
            recommendedActions: 'Reassurance and monitoring. Advise hydration and rest. Schedule follow-up if symptoms persist.',
            timestamp: new Date(Date.now() - 45 * 60000).toISOString(),
            reviewed: false
        }
    ];
}
