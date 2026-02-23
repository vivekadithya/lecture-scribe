/**
 * LectureScribe — Popup Controller
 * 
 * Manages the popup UI lifecycle: status polling, session controls,
 * live transcript updates, and settings navigation.
 */

// DOM elements
const statusBar = document.getElementById('status-bar');
const statusText = document.getElementById('status-text');
const sessionInfo = document.getElementById('session-info');
const durationEl = document.getElementById('duration');
const wordCountEl = document.getElementById('word-count');
const silenceCounterEl = document.getElementById('silence-counter');
const startBtn = document.getElementById('start-btn');
const stopBtn = document.getElementById('stop-btn');
const transcriptContainer = document.getElementById('transcript-container');
const transcriptBody = document.getElementById('transcript-body');
const copyBtn = document.getElementById('copy-btn');
const settingsBtn = document.getElementById('settings-btn');
const setupBanner = document.getElementById('setup-banner');
const noVideoMsg = document.getElementById('no-video-msg');
const generateSection = document.getElementById('generate-section');
const generateBtn = document.getElementById('generate-btn');

let pollInterval = null;
let durationInterval = null;
let sessionStartTime = null;
let currentOutputFormat = 'timestamped';

// ─── Initialization ────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
    await refreshState();

    // Start polling for updates
    pollInterval = setInterval(refreshState, 1000);
});

// ─── Event Listeners ───────────────────────────────────────────

startBtn.addEventListener('click', async () => {
    startBtn.disabled = true;
    startBtn.textContent = 'Starting...';

    try {
        // Get the active tab
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if (!tab) {
            showError('No active tab found');
            return;
        }

        const response = await chrome.runtime.sendMessage({
            type: 'START_SESSION',
            tabId: tab.id
        });

        if (response.success) {
            sessionStartTime = Date.now();
            startDurationTimer();
            await refreshState();
        } else {
            showError(response.error || 'Failed to start session');
        }
    } catch (err) {
        showError(err.message);
    } finally {
        startBtn.disabled = false;
        startBtn.innerHTML = '<span class="btn-icon">🎙️</span> Start Transcribing';
    }
});

stopBtn.addEventListener('click', async () => {
    stopBtn.disabled = true;
    stopBtn.textContent = 'Stopping...';

    try {
        const response = await chrome.runtime.sendMessage({ type: 'STOP_SESSION' });
        if (response.success) {
            stopDurationTimer();
            await refreshState();
        } else {
            showError(response.error || 'Failed to stop session');
        }
    } catch (err) {
        showError(err.message);
    } finally {
        stopBtn.disabled = false;
        stopBtn.innerHTML = '<span class="btn-icon">⏹️</span> Stop';
    }
});

copyBtn.addEventListener('click', async () => {
    try {
        const response = await chrome.runtime.sendMessage({ type: 'GET_FULL_TRANSCRIPT' });
        if (response.transcript && response.transcript.length > 0) {
            let text;
            if (currentOutputFormat === 'raw') {
                text = response.transcript.map(line => line.text).join(' ');
            } else {
                text = response.transcript
                    .map(line => `[${line.timestamp}] ${line.text}`)
                    .join('\n');
            }
            await navigator.clipboard.writeText(text);
            copyBtn.textContent = '✅ Copied!';
            setTimeout(() => { copyBtn.textContent = '📋 Copy'; }, 1500);
        }
    } catch (err) {
        console.error('Copy failed:', err);
    }
});

settingsBtn.addEventListener('click', () => {
    chrome.runtime.openOptionsPage();
});

generateBtn.addEventListener('click', () => {
    // Open generate page in a new tab with current session ID
    chrome.runtime.sendMessage({ type: 'GET_STATUS' }, (state) => {
        const sessionId = state?.sessionId || '';
        chrome.tabs.create({
            url: chrome.runtime.getURL(`generate.html?session=${sessionId}`)
        });
    });
});

// ─── State Management ──────────────────────────────────────────

async function refreshState() {
    try {
        const response = await chrome.runtime.sendMessage({ type: 'GET_STATUS' });
        updateUI(response);
    } catch (err) {
        // Service worker might not be ready yet
        console.warn('Failed to get status:', err);
    }
}

function updateUI(state) {
    if (!state) return;

    // Update status bar
    const statusMap = {
        'idle': 'Idle',
        'listening': 'Listening...',
        'transcribing': 'Transcribing',
        'auto-stopped': 'Auto-stopped (silence)',
        'error': 'Error'
    };

    statusText.textContent = statusMap[state.status] || state.status;
    statusBar.className = `status-bar status-${state.status}`;

    // Show/hide elements based on session state
    const isActive = state.active;

    startBtn.classList.toggle('hidden', isActive);
    stopBtn.classList.toggle('hidden', !isActive);
    sessionInfo.classList.toggle('hidden', !isActive && state.status !== 'auto-stopped');
    transcriptContainer.classList.toggle('hidden', !state.transcript || state.transcript.length === 0);
    noVideoMsg.classList.add('hidden');

    // Show generate button when session has transcript and is not active
    const hasTranscript = state.transcript && state.transcript.length > 0;
    generateSection.classList.toggle('hidden', isActive || !hasTranscript);

    // Update session info
    if (isActive || state.status === 'auto-stopped') {
        wordCountEl.textContent = state.wordCount || 0;

        // Silence counter
        const silenceSec = Math.floor((state.silenceDuration || 0) / 1000);
        const silenceMin = Math.floor(silenceSec / 60);
        const silenceRemSec = silenceSec % 60;
        silenceCounterEl.textContent = `${silenceMin}:${String(silenceRemSec).padStart(2, '0')}`;

        // Duration
        if (isActive && state.startTime) {
            sessionStartTime = state.startTime;
            startDurationTimer();
        }
    }

    // Track format for rendering
    if (state.outputFormat) {
        currentOutputFormat = state.outputFormat;
    }

    // Update transcript
    if (state.transcript && state.transcript.length > 0) {
        renderTranscript(state.transcript, currentOutputFormat);
    }
}

function renderTranscript(lines, format) {
    let html;
    if (format === 'raw') {
        // Raw text: flowing paragraphs, no timestamps
        const text = lines.map(line => escapeHTML(line.text)).join(' ');
        html = `<div class="transcript-line"><span class="transcript-text">${text}</span></div>`;
    } else {
        // Timestamped: each segment on its own line with [HH:MM:SS] prefix
        html = lines.map(line => `
        <div class="transcript-line">
          <span class="transcript-timestamp">${escapeHTML(line.timestamp)}</span>
          <span class="transcript-text">${escapeHTML(line.text)}</span>
        </div>
      `).join('');
    }

    transcriptBody.innerHTML = html;

    // Auto-scroll to bottom
    transcriptBody.scrollTop = transcriptBody.scrollHeight;
}

// ─── Duration Timer ────────────────────────────────────────────

function startDurationTimer() {
    if (durationInterval) return;

    durationInterval = setInterval(() => {
        if (!sessionStartTime) return;
        const elapsed = Date.now() - sessionStartTime;
        durationEl.textContent = formatDuration(elapsed);
    }, 1000);
}

function stopDurationTimer() {
    if (durationInterval) {
        clearInterval(durationInterval);
        durationInterval = null;
    }
}

// ─── Utilities ─────────────────────────────────────────────────

function formatDuration(ms) {
    const totalSec = Math.floor(ms / 1000);
    const h = Math.floor(totalSec / 3600);
    const m = Math.floor((totalSec % 3600) / 60);
    const s = totalSec % 60;
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function escapeHTML(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function showError(message) {
    statusText.textContent = `Error: ${message}`;
    statusBar.className = 'status-bar status-error';
}

// ─── Cleanup ───────────────────────────────────────────────────

window.addEventListener('unload', () => {
    if (pollInterval) clearInterval(pollInterval);
    if (durationInterval) clearInterval(durationInterval);
});
