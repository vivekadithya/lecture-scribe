/**
 * LectureScribe — Service Worker (Background Script)
 * 
 * Central orchestrator for the extension. Manages:
 * - Session lifecycle (start/stop/pause)
 * - Offscreen document creation for audio capture
 * - Native messaging host communication
 * - Transcript state management
 */

const NATIVE_HOST = 'com.lecturescribe.host';
const OFFSCREEN_URL = 'offscreen.html';

/** @type {chrome.runtime.Port|null} */
let nativePort = null;

/** @type {Object} Current session state */
let session = {
  active: false,
  tabId: null,
  sessionId: null,
  startTime: null,
  transcript: [],
  wordCount: 0,
  silenceDuration: 0,
  outputFormat: 'timestamped',
  status: 'idle' // idle | listening | transcribing | auto-stopped | error
};

// ─── Message Routing ───────────────────────────────────────────

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  switch (message.type) {
    case 'VIDEO_DETECTED':
      handleVideoDetected(sender.tab);
      break;
    case 'VIDEO_PLAYING':
      handleVideoPlaying(sender.tab);
      break;
    case 'VIDEO_STOPPED':
      handleVideoStopped(sender.tab);
      break;
    case 'AUDIO_CHUNK':
      handleAudioChunk(message.data);
      break;
    case 'START_SESSION':
      startSession(message.tabId).then(r => sendResponse(r));
      return true; // async response
    case 'STOP_SESSION':
      stopSession().then(r => sendResponse(r));
      return true;
    case 'GET_STATUS':
      sendResponse({ ...session, transcript: session.transcript.slice(-50) });
      break;
    case 'GET_FULL_TRANSCRIPT':
      sendResponse({ transcript: session.transcript });
      break;
    case 'UPDATE_SETTINGS':
      syncSettingsToNativeHost(message.settings);
      break;
    case 'GENERATE_STUDY_MATERIALS':
      handleGenerateRequest(message).then(r => sendResponse(r));
      return true;
    case 'EXPORT_TO_NOTION':
      handleNotionExportRequest(message).then(r => sendResponse(r));
      return true;
    case 'PICK_FOLDER':
      handlePickFolder().then(r => sendResponse(r));
      return true;
    default:
      break;
  }
});

// ─── Video Detection Handlers ──────────────────────────────────

function handleVideoDetected(tab) {
  if (!tab) return;
  chrome.action.setBadgeText({ text: '▶', tabId: tab.id });
  chrome.action.setBadgeBackgroundColor({ color: '#4CAF50', tabId: tab.id });
}

function handleVideoPlaying(tab) {
  if (!tab) return;
  chrome.action.setBadgeText({ text: '▶', tabId: tab.id });
  chrome.action.setBadgeBackgroundColor({ color: '#4CAF50', tabId: tab.id });
}

function handleVideoStopped(tab) {
  if (!tab) return;
  chrome.action.setBadgeText({ text: '', tabId: tab.id });
}

// ─── Session Management ────────────────────────────────────────

async function startSession(tabId) {
  if (session.active) {
    return { success: false, error: 'Session already active' };
  }

  try {
    // 1. Connect to native host
    if (!connectNativeHost()) {
      return { success: false, error: 'Failed to connect to LectureScribe companion app. Is it installed?' };
    }

    // 2. Create offscreen document for audio capture
    await ensureOffscreenDocument();

    // 3. Get tab media stream ID
    const streamId = await chrome.tabCapture.getMediaStreamId({ targetTabId: tabId });

    // 4. Initialize session state
    const { settings } = await chrome.storage.local.get('settings');
    const outputFormat = settings?.outputFormat || 'timestamped';

    session = {
      active: true,
      tabId,
      sessionId: generateSessionId(),
      startTime: Date.now(),
      transcript: [],
      wordCount: 0,
      silenceDuration: 0,
      outputFormat,
      status: 'listening'
    };

    // 5. Small delay to let native host Python interpreter start
    await new Promise(resolve => setTimeout(resolve, 500));

    // 6. Check if native port is still alive after delay
    if (!nativePort) {
      session.active = false;
      session.status = 'error';
      updateStoredSession();
      return { success: false, error: 'Native host disconnected during startup. Check installation.' };
    }

    // 7. Sync current settings to native host BEFORE starting session
    if (settings) {
      syncSettingsToNativeHost(settings);
    }

    // 8. Tell native host to start a new session
    sendNativeMessage({
      type: 'START_SESSION',
      sessionId: session.sessionId
    });

    // 9. Tell offscreen document to start capturing audio
    chrome.runtime.sendMessage({
      type: 'START_CAPTURE',
      target: 'offscreen',
      streamId,
      tabId
    });

    // 10. Update badge
    chrome.action.setBadgeText({ text: '🔴', tabId });
    chrome.action.setBadgeBackgroundColor({ color: '#F44336', tabId });

    updateStoredSession();
    return { success: true, sessionId: session.sessionId };
  } catch (err) {
    session.active = false;
    session.status = 'error';
    console.error('[LectureScribe] Start session failed:', err);
    updateStoredSession();
    return { success: false, error: err.message };
  }
}

async function stopSession() {
  if (!session.active) {
    return { success: false, error: 'No active session' };
  }

  try {
    // 1. Stop audio capture
    chrome.runtime.sendMessage({
      type: 'STOP_CAPTURE',
      target: 'offscreen'
    });

    // 2. Tell native host to finalize
    sendNativeMessage({
      type: 'STOP_SESSION',
      sessionId: session.sessionId
    });

    // 3. Update state
    session.active = false;
    session.status = 'idle';

    // 4. Clear badge
    if (session.tabId) {
      chrome.action.setBadgeText({ text: '', tabId: session.tabId });
    }

    // 5. Close offscreen document
    await closeOffscreenDocument();

    const result = {
      success: true,
      sessionId: session.sessionId,
      duration: Date.now() - session.startTime,
      wordCount: session.wordCount
    };

    updateStoredSession();
    return result;
  } catch (err) {
    console.error('[LectureScribe] Stop session failed:', err);
    return { success: false, error: err.message };
  }
}

// ─── Audio Chunk Handling ──────────────────────────────────────

function handleAudioChunk(base64Audio) {
  if (!session.active || !nativePort) return;

  sendNativeMessage({
    type: 'AUDIO_CHUNK',
    sessionId: session.sessionId,
    data: base64Audio,
    timestamp: Date.now()
  });

  session.status = 'transcribing';
}

// ─── Native Messaging ──────────────────────────────────────────

function connectNativeHost() {
  try {
    nativePort = chrome.runtime.connectNative(NATIVE_HOST);

    nativePort.onMessage.addListener((message) => {
      handleNativeMessage(message);
    });

    nativePort.onDisconnect.addListener(() => {
      const error = chrome.runtime.lastError;
      const errorMsg = error?.message || 'Unknown error';
      console.error('[LectureScribe] Native host disconnected:', errorMsg);
      nativePort = null;

      if (session.active) {
        session.status = 'error';
        session.active = false;
        // Store the error so popup can display it
        session.lastError = `Native host disconnected: ${errorMsg}`;
        updateStoredSession();
      }
    });

    return true;
  } catch (err) {
    console.error('[LectureScribe] Failed to connect native host:', err);
    return false;
  }
}

function sendNativeMessage(message) {
  if (!nativePort) {
    console.error('[LectureScribe] No native port, cannot send message');
    return;
  }
  try {
    nativePort.postMessage(message);
  } catch (err) {
    console.error('[LectureScribe] Failed to send native message:', err);
  }
}

function handleNativeMessage(message) {
  switch (message.type) {
    case 'TRANSCRIPT_CHUNK':
      handleTranscriptChunk(message);
      break;
    case 'SILENCE_ALERT':
      handleSilenceAlert(message);
      break;
    case 'SESSION_COMPLETE':
      handleSessionComplete(message);
      break;
    case 'GENERATION_COMPLETE':
    case 'GENERATION_PROGRESS':
    case 'NOTION_EXPORT_COMPLETE':
      // Forward to all extension pages (generate page listens for these)
      chrome.runtime.sendMessage(message).catch(() => { });
      break;
    case 'ERROR':
      console.error('[LectureScribe] Native host error:', message.error);
      // Forward errors to generate page too
      chrome.runtime.sendMessage(message).catch(() => { });
      session.status = 'error';
      updateStoredSession();
      break;
    case 'STATUS':
      // Acknowledgement from native host
      break;
    default:
      console.warn('[LectureScribe] Unknown native message type:', message.type);
  }
}

function handleTranscriptChunk(message) {
  if (!message.segments || !Array.isArray(message.segments)) return;

  for (const segment of message.segments) {
    session.transcript.push({
      timestamp: segment.timestamp,
      text: segment.text
    });
    session.wordCount += segment.text.split(/\s+/).filter(Boolean).length;
  }

  session.silenceDuration = 0;
  session.status = 'transcribing';
  updateStoredSession();
}

function handleSilenceAlert(message) {
  session.silenceDuration = message.silenceDuration || 0;

  if (message.autoStop) {
    console.log('[LectureScribe] Auto-stopping due to extended silence');
    session.status = 'auto-stopped';
    stopSession();
  }

  updateStoredSession();
}

function handleSessionComplete(message) {
  session.active = false;
  session.status = 'idle';

  if (message.transcriptPath) {
    chrome.storage.local.set({
      lastTranscriptPath: message.transcriptPath
    });
  }

  updateStoredSession();
}

// ─── Offscreen Document Management ─────────────────────────────

async function ensureOffscreenDocument() {
  const existingContexts = await chrome.runtime.getContexts({
    contextTypes: ['OFFSCREEN_DOCUMENT'],
    documentUrls: [chrome.runtime.getURL(OFFSCREEN_URL)]
  });

  if (existingContexts.length > 0) return;

  await chrome.offscreen.createDocument({
    url: OFFSCREEN_URL,
    reasons: [chrome.offscreen.Reason.USER_MEDIA],
    justification: 'Capture tab audio for transcription'
  });
}

async function closeOffscreenDocument() {
  const existingContexts = await chrome.runtime.getContexts({
    contextTypes: ['OFFSCREEN_DOCUMENT'],
    documentUrls: [chrome.runtime.getURL(OFFSCREEN_URL)]
  });

  if (existingContexts.length > 0) {
    await chrome.offscreen.closeDocument();
  }
}

// ─── Utilities ─────────────────────────────────────────────────

function generateSessionId() {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}_${pad(now.getHours())}-${pad(now.getMinutes())}-${pad(now.getSeconds())}`;
}

function updateStoredSession() {
  chrome.storage.local.set({
    session: {
      active: session.active,
      tabId: session.tabId,
      sessionId: session.sessionId,
      startTime: session.startTime,
      wordCount: session.wordCount,
      silenceDuration: session.silenceDuration,
      outputFormat: session.outputFormat,
      status: session.status,
      transcriptLength: session.transcript.length
    }
  });
}

/**
 * Sync extension settings to the native host via CONFIGURE message.
 * Called when user saves settings and before each session start.
 */
function syncSettingsToNativeHost(settings) {
  if (!nativePort) return;
  sendNativeMessage({
    type: 'CONFIGURE',
    settings: {
      transcriptionEngine: settings.transcriptionEngine || 'local',
      model: settings.model || 'base',
      groqModel: settings.groqModel || 'whisper-large-v3',
      silenceThreshold: settings.silenceThreshold || 600,
      outputFormat: settings.outputFormat || 'timestamped',
      outputDir: settings.outputDir || '~/LectureScribe',
      gdriveDir: settings.gdriveDir || '',
      groqApiKey: settings.groqApiKey || '',
      geminiApiKey: settings.geminiApiKey || '',
      geminiModel: settings.geminiModel || 'gemini-2.5-flash',
      notionApiKey: settings.notionApiKey || '',
      notionPageId: settings.notionPageId || '',
      defaultFeatures: settings.defaultFeatures || ['summary', 'flashcards', 'quiz'],
      customPrompts: settings.customPrompts || {}
    }
  });
}

// ─── AI Generation ─────────────────────────────────────────────

async function handleGenerateRequest(message) {
  try {
    // Ensure native host is connected
    if (!nativePort) {
      if (!connectNativeHost()) {
        return { error: 'Failed to connect to companion app. Is it installed?' };
      }
      await new Promise(resolve => setTimeout(resolve, 500));
    }

    // Read transcript from session storage if not provided
    let transcript = '';
    if (session.transcript.length > 0) {
      transcript = session.transcript
        .map(line => `[${line.timestamp}] ${line.text}`)
        .join('\n');
    }

    // Get API key from settings
    const { settings } = await chrome.storage.local.get('settings');

    sendNativeMessage({
      type: 'GENERATE',
      sessionId: message.sessionId || session.sessionId,
      features: message.features || ['summary', 'flashcards', 'quiz'],
      customPrompts: message.customPrompts || {},
      transcript,
      geminiApiKey: settings?.geminiApiKey || '',
      geminiModel: settings?.geminiModel || 'gemini-2.5-flash'
    });

    return { success: true };
  } catch (err) {
    console.error('[LectureScribe] Generate request failed:', err);
    return { error: err.message };
  }
}

async function handleNotionExportRequest(message) {
  try {
    if (!nativePort) {
      return { error: 'Native host not connected' };
    }

    const { settings } = await chrome.storage.local.get('settings');

    sendNativeMessage({
      type: 'NOTION_EXPORT',
      sessionId: message.sessionId,
      results: message.results,
      notionApiKey: settings?.notionApiKey || '',
      notionPageId: settings?.notionPageId || ''
    });

    return { success: true };
  } catch (err) {
    console.error('[LectureScribe] Notion export request failed:', err);
    return { error: err.message };
  }
}

async function handlePickFolder() {
  try {
    if (!nativePort) {
      connectNativeHost();
      await new Promise(r => setTimeout(r, 500));
    }
    if (!nativePort) {
      return { error: 'Native host not connected' };
    }

    return new Promise((resolve) => {
      const listener = (message) => {
        if (message.type === 'FOLDER_PICKED') {
          nativePort.onMessage.removeListener(listener);
          resolve({ path: message.path });
        } else if (message.type === 'FOLDER_CANCELLED') {
          nativePort.onMessage.removeListener(listener);
          resolve({ error: 'cancelled' });
        }
      };
      nativePort.onMessage.addListener(listener);
      sendNativeMessage({ type: 'PICK_FOLDER' });

      // Timeout after 60 seconds (user may take time in dialog)
      setTimeout(() => {
        nativePort.onMessage.removeListener(listener);
        resolve({ error: 'timeout' });
      }, 60000);
    });
  } catch (err) {
    return { error: err.message };
  }
}

// ─── Extension Install / Update ────────────────────────────────

chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === 'install') {
    chrome.storage.local.set({
      settings: {
        model: 'base',
        silenceThreshold: 600,
        outputFormat: 'timestamped',
        outputDir: '~/LectureScribe',
        groqApiKey: '',
        geminiApiKey: '',
        notionApiKey: '',
        notionPageId: '',
        defaultFeatures: ['summary', 'flashcards', 'quiz'],
        customPrompts: {}
      },
      session: {
        active: false,
        status: 'idle'
      }
    });
  }
});
