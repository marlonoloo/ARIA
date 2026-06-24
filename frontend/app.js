/**
 * ARIA Frontend - Voice-First Emergency Assistant
 * 
 * Flow:
 * 1. Patient holds mic button and speaks
 * 2. Audio is recorded and sent to API Gateway → Lambda #1
 * 3. Lambda #1: Transcribe → Translate → Lex → returns text response
 * 4. Frontend calls Polly to speak the response back to patient
 * 5. Loop continues until Lex closes the conversation (all slots filled + fulfillment done)
 */

// === CONFIGURE THESE ===
const API_ENDPOINT = 'https://5lujwlh8lf.execute-api.us-east-1.amazonaws.com/dev/emergency';  // e.g. https://xxxxxx.execute-api.region.amazonaws.com/dev/emergency

// AWS SDK config for Polly (called directly from browser)
// Cognito Identity Pool provides temporary credentials without patient login
const AWS_REGION = 'us-east-1';  // e.g. 'us-east-1'
const COGNITO_IDENTITY_POOL_ID = 'us-east-1:2e4d3f5c-0067-4ec5-8c44-cd5539967ff8';  // e.g. 'us-east-1:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx'

// Initialize AWS SDK for browser
function initAWS() {
    AWS.config.region = AWS_REGION;
    AWS.config.credentials = new AWS.CognitoIdentityCredentials({
        IdentityPoolId: COGNITO_IDENTITY_POOL_ID
    });
}
initAWS();

// === STATE ===
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let sessionId = 'session-' + Date.now();  // Unique per conversation
let detectedLanguage = null;  // Stored after first utterance, sent on every turn
let hasEmergencyDescription = false;  // Tracks if first utterance was captured
let emergencyDescription = '';  // The original emergency text

// === DOM ELEMENTS ===
const micBtn = document.getElementById('micBtn');
const status = document.getElementById('status');
const conversation = document.getElementById('conversation');
const textInput = document.getElementById('textInput');
const sendBtn = document.getElementById('sendBtn');

// === MIC BUTTON — HOLD TO RECORD ===

micBtn.addEventListener('mousedown', startRecording);
micBtn.addEventListener('mouseup', stopRecording);
micBtn.addEventListener('mouseleave', stopRecording);

// Touch support for mobile
micBtn.addEventListener('touchstart', (e) => { e.preventDefault(); startRecording(); });
micBtn.addEventListener('touchend', (e) => { e.preventDefault(); stopRecording(); });

async function startRecording() {
    if (isRecording) return;

    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
        audioChunks = [];

        mediaRecorder.ondataavailable = (event) => {
            audioChunks.push(event.data);
        };

        mediaRecorder.start();
        isRecording = true;
        micBtn.classList.add('recording');
        micBtn.classList.remove('bg-aria-emergency');
        micBtn.classList.add('bg-red-700');
        status.textContent = 'Listening... release when done';
        document.getElementById('micLabel').textContent = 'Release to send';
    } catch (err) {
        console.error('Mic access denied:', err);
        status.textContent = 'Microphone access denied. Please allow mic access.';
    }
}

function stopRecording() {
    if (!isRecording || !mediaRecorder) return;

    mediaRecorder.stop();
    isRecording = false;
    micBtn.classList.remove('recording');
    micBtn.classList.remove('bg-red-700');
    micBtn.classList.add('bg-aria-emergency');
    status.textContent = 'Processing your voice...';
    document.getElementById('micLabel').textContent = 'Processing...';

    mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
        
        // Stop all tracks to release mic
        mediaRecorder.stream.getTracks().forEach(track => track.stop());
        
        // Convert blob to base64
        const base64Audio = await blobToBase64(audioBlob);
        
        // Send to backend
        await sendAudio(base64Audio);
    };
}

// === SEND AUDIO TO BACKEND ===

async function sendAudio(base64Audio) {
    try {
        const response = await fetch(API_ENDPOINT, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                inputType: 'audio',
                audio: base64Audio,
                sessionId: sessionId,
                detectedLanguage: detectedLanguage,
                hasEmergencyDescription: hasEmergencyDescription,
                emergencyDescription: emergencyDescription
            })
        });

        const data = await response.json();
        handleResponse(data);
    } catch (err) {
        console.error('API error:', err);
        status.textContent = 'Connection error. Please try again.';
        micBtn.classList.remove('processing');
    }
}

// === SEND TEXT (fallback for testing) ===

sendBtn.addEventListener('click', sendText);
textInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendText();
});

async function sendText() {
    const text = textInput.value.trim();
    if (!text) return;

    textInput.value = '';
    micBtn.classList.add('processing');
    status.textContent = '⏳ Processing...';

    addMessage('patient', text);

    try {
        const response = await fetch(API_ENDPOINT, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                inputType: 'text',
                text: text,
                language: 'en',
                sessionId: sessionId
            })
        });

        const data = await response.json();
        handleResponse(data);
    } catch (err) {
        console.error('API error:', err);
        status.textContent = 'Connection error. Please try again.';
        micBtn.classList.remove('processing');
    }
}

// === HANDLE RESPONSE FROM BACKEND ===

function handleResponse(data) {
    const responseText = data.response;
    const dialogState = data.dialogState;
    const responseLanguage = data.detectedLanguage || 'en';
    const patientText = data.patientText;

    // Store detected language for future turns
    if (responseLanguage && responseLanguage !== 'en') {
        detectedLanguage = responseLanguage;
    }

    // Store emergency description after first turn
    if (data.hasEmergencyDescription) {
        hasEmergencyDescription = true;
        emergencyDescription = data.emergencyDescription;
    }

    // Show what the patient said (from Transcribe)
    if (patientText) {
        addMessage('patient', patientText);
    }

    // Show ARIA's response
    addMessage('aria', responseText);

    // Speak the response using Polly (pass language for correct voice)
    speakResponse(responseText, responseLanguage);

    // Update UI based on conversation state
    micBtn.classList.remove('processing');
    document.getElementById('micLabel').textContent = 'Hold to speak';

    if (dialogState === 'Close') {
        status.textContent = 'Help is on the way. Stay calm.';
        document.getElementById('statusBanner').className = 'bg-green-50 border border-green-200 rounded-xl p-4 mb-6 text-center';
        status.className = 'text-sm font-medium text-green-800';
        micBtn.style.display = 'none';
        document.getElementById('micLabel').style.display = 'none';
    } else {
        status.textContent = 'Hold the mic to answer';
    }
}

// === TEXT-TO-SPEECH (Amazon Polly) ===

// Map language codes to Polly voice IDs
const POLLY_VOICES = {
    'en': { voiceId: 'Joanna', engine: 'neural' },
    'fr': { voiceId: 'Lea', engine: 'neural' },
    'ar': { voiceId: 'Zeina', engine: 'standard' },
    'default': { voiceId: 'Joanna', engine: 'neural' }
};

async function speakResponse(text, languageCode) {
    try {
        const polly = new AWS.Polly();
        
        // Pick the right voice for the language
        const voice = POLLY_VOICES[languageCode] || POLLY_VOICES['default'];

        const params = {
            OutputFormat: 'mp3',
            Text: text,
            VoiceId: voice.voiceId,
            Engine: voice.engine
        };

        const data = await polly.synthesizeSpeech(params).promise();
        const audioBlob = new Blob([data.AudioStream], { type: 'audio/mp3' });
        const audioUrl = URL.createObjectURL(audioBlob);
        const audio = new Audio(audioUrl);
        await audio.play();
    } catch (err) {
        console.error('Polly error, falling back to browser speech:', err);
        // Fallback to browser speech synthesis
        if ('speechSynthesis' in window) {
            const utterance = new SpeechSynthesisUtterance(text);
            utterance.rate = 0.9;
            speechSynthesis.speak(utterance);
        }
    }
}

// === UTILITY FUNCTIONS ===

function blobToBase64(blob) {
    return new Promise((resolve) => {
        const reader = new FileReader();
        reader.onloadend = () => {
            // Remove the data:audio/webm;base64, prefix
            const base64 = reader.result.split(',')[1];
            resolve(base64);
        };
        reader.readAsDataURL(blob);
    });
}

function addMessage(sender, text) {
    conversation.style.display = 'flex';
    conversation.style.flexDirection = 'column';
    // Hide empty state after first message
    const emptyState = document.getElementById('emptyState');
    if (emptyState) emptyState.style.display = 'none';
    
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message-enter';
    
    if (sender === 'patient') {
        messageDiv.innerHTML = `
            <div class="flex justify-end mb-3">
                <div class="bg-blue-600 text-white rounded-2xl rounded-br-md px-4 py-3 max-w-[80%]">
                    <p class="text-sm">${text}</p>
                </div>
            </div>
        `;
    } else {
        messageDiv.innerHTML = `
            <div class="flex justify-start mb-3">
                <div class="bg-white border border-gray-200 rounded-2xl rounded-bl-md px-4 py-3 max-w-[80%] shadow-sm">
                    <p class="text-xs font-medium text-blue-600 mb-1">ARIA</p>
                    <p class="text-sm text-gray-900">${text}</p>
                </div>
            </div>
        `;
    }
    conversation.appendChild(messageDiv);
    conversation.scrollTop = conversation.scrollHeight;
}
