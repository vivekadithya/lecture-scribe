/**
 * LectureScribe — Offscreen Document
 * 
 * Captures tab audio using chrome.tabCapture stream ID,
 * processes it through AudioWorklet to extract 16kHz mono PCM,
 * and sends base64-encoded chunks to the service worker.
 */

let audioContext = null;
let mediaStream = null;
let workletNode = null;

// Listen for messages from the service worker
chrome.runtime.onMessage.addListener((message) => {
    if (message.target !== 'offscreen') return;

    switch (message.type) {
        case 'START_CAPTURE':
            startCapture(message.streamId);
            break;
        case 'STOP_CAPTURE':
            stopCapture();
            break;
    }
});

/**
 * Start capturing audio from the given tab stream ID
 */
async function startCapture(streamId) {
    try {
        // Get the media stream from the tab
        mediaStream = await navigator.mediaDevices.getUserMedia({
            audio: {
                mandatory: {
                    chromeMediaSource: 'tab',
                    chromeMediaSourceId: streamId
                }
            }
        });

        // Create audio context at 16kHz (Whisper's expected sample rate)
        audioContext = new AudioContext({ sampleRate: 16000 });

        // Load the AudioWorklet processor
        await audioContext.audioWorklet.addModule('audio-processor.js');

        // Create source from the media stream
        const source = audioContext.createMediaStreamSource(mediaStream);

        // Create the worklet node
        workletNode = new AudioWorkletNode(audioContext, 'pcm-extractor', {
            processorOptions: {
                bufferDurationSec: 2 // Send chunks every 2 seconds
            }
        });

        // Handle audio data from the worklet
        workletNode.port.onmessage = (event) => {
            const { audioData } = event.data;
            if (audioData && audioData.length > 0) {
                // Convert Float32Array to base64-encoded Int16 PCM
                const base64 = float32ToBase64PCM(audioData);
                chrome.runtime.sendMessage({
                    type: 'AUDIO_CHUNK',
                    data: base64
                });
            }
        };

        // Connect: source → worklet → destination (keeps audio audible)
        source.connect(workletNode);
        workletNode.connect(audioContext.destination);

        console.log('[LectureScribe Offscreen] Audio capture started');
    } catch (err) {
        console.error('[LectureScribe Offscreen] Failed to start capture:', err);
        chrome.runtime.sendMessage({
            type: 'CAPTURE_ERROR',
            error: err.message
        });
    }
}

/**
 * Stop audio capture and clean up resources
 */
function stopCapture() {
    if (workletNode) {
        workletNode.disconnect();
        workletNode = null;
    }

    if (mediaStream) {
        mediaStream.getTracks().forEach(track => track.stop());
        mediaStream = null;
    }

    if (audioContext) {
        audioContext.close();
        audioContext = null;
    }

    console.log('[LectureScribe Offscreen] Audio capture stopped');
}

/**
 * Convert Float32 audio data to base64-encoded Int16 PCM
 * Whisper expects 16-bit signed integer PCM
 */
function float32ToBase64PCM(float32Array) {
    const int16Array = new Int16Array(float32Array.length);

    for (let i = 0; i < float32Array.length; i++) {
        // Clamp to [-1, 1] range and convert to Int16
        const s = Math.max(-1, Math.min(1, float32Array[i]));
        int16Array[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }

    // Convert to base64
    const bytes = new Uint8Array(int16Array.buffer);
    let binary = '';
    for (let i = 0; i < bytes.length; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
}
