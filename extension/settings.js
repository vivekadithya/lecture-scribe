/**
 * LectureScribe — Settings Controller
 */

const engineSelect = document.getElementById('engine-select');
const modelSelect = document.getElementById('model-select');
const groqModelSelect = document.getElementById('groq-model-select');
const localModelField = document.getElementById('local-model-field');
const groqModelField = document.getElementById('groq-model-field');
const silenceSlider = document.getElementById('silence-slider');
const silenceValue = document.getElementById('silence-value');
const formatSelect = document.getElementById('format-select');
const outputDir = document.getElementById('output-dir');
const gdriveDir = document.getElementById('gdrive-dir');
const groqKey = document.getElementById('groq-key');
const testGroqBtn = document.getElementById('test-groq-btn');
const groqTestStatus = document.getElementById('groq-test-status');
const geminiKey = document.getElementById('gemini-key');
const geminiModel = document.getElementById('gemini-model');
const testGeminiBtn = document.getElementById('test-gemini-btn');
const geminiTestStatus = document.getElementById('gemini-test-status');
const notionKey = document.getElementById('notion-key');
const notionPageId = document.getElementById('notion-page-id');
const saveBtn = document.getElementById('save-btn');
const saveStatus = document.getElementById('save-status');

// Load settings
document.addEventListener('DOMContentLoaded', async () => {
    const { settings } = await chrome.storage.local.get('settings');
    if (settings) {
        engineSelect.value = settings.transcriptionEngine || 'local';
        modelSelect.value = settings.model || 'base';
        groqModelSelect.value = settings.groqModel || 'whisper-large-v3';
        silenceSlider.value = settings.silenceThreshold || 600;
        formatSelect.value = settings.outputFormat || 'timestamped';
        outputDir.value = settings.outputDir || '~/LectureScribe';
        gdriveDir.value = settings.gdriveDir || '';
        groqKey.value = settings.groqApiKey || '';
        geminiKey.value = settings.geminiApiKey || '';
        notionKey.value = settings.notionApiKey || '';
        notionPageId.value = settings.notionPageId || '';
        // Migrate from deprecated 1.5 or 2.0 models to 2.5
        if (settings.geminiModel === 'gemini-1.5-flash' || settings.geminiModel === 'gemini-1.5-pro' || settings.geminiModel === 'gemini-2.0-flash' || settings.geminiModel === 'gemini-2.0-flash-lite') {
            settings.geminiModel = 'gemini-2.5-flash-lite';
            // Save migrated setting immediately
            chrome.storage.local.set({ settings });
        }

        updateSliderLabel();
        updateEngineFields();
    }

    // Populate Gemini model dropdown
    const savedModel = settings?.geminiModel || 'gemini-2.5-flash-lite';
    await populateGeminiModels(geminiKey.value.trim(), savedModel);
});

// ─── UI Logic ──────────────────────────────────────────────────

function updateEngineFields() {
    if (engineSelect.value === 'groq') {
        localModelField.style.display = 'none';
        groqModelField.style.display = 'block';
    } else {
        localModelField.style.display = 'block';
        groqModelField.style.display = 'none';
    }
}

engineSelect.addEventListener('change', updateEngineFields);

// ─── Gemini Model Dropdown ────────────────────────────────────

const FALLBACK_MODELS = [
    { id: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash — Free (recommended)' },
    { id: 'gemini-2.5-flash-lite', label: 'Gemini 2.5 Flash Lite — Free (fastest)' },
    { id: 'gemini-2.5-pro', label: 'Gemini 2.5 Pro — Free tier limited' },
];

async function populateGeminiModels(apiKey, selectedModel) {
    let models = [];

    if (apiKey) {
        try {
            const res = await fetch(
                `https://generativelanguage.googleapis.com/v1beta/models?key=${apiKey}`
            );
            if (res.ok) {
                const data = await res.json();
                models = (data.models || [])
                    .filter(m => m.supportedGenerationMethods?.includes('generateContent'))
                    .map(m => ({
                        id: m.name.replace('models/', ''),
                        label: m.displayName || m.name.replace('models/', '')
                    }))
                    .sort((a, b) => a.id.localeCompare(b.id));
            }
        } catch (e) {
            // API call failed, use fallback
        }
    }

    if (models.length === 0) {
        models = FALLBACK_MODELS;
    }

    geminiModel.innerHTML = '';

    const sortedModels = models.map(m => {
        let label = m.label;
        let isRecommended = false;
        const idLower = m.id.toLowerCase();

        // Label models that have a free tier (practically all Flash/Pro/Lite in AI Studio)
        if (idLower.includes('flash') || idLower.includes('pro') || idLower.includes('lite')) {
            label += ' — ✨ Free';
        }

        // Recommend all stable Flash models
        if (idLower.includes('flash') && !idLower.includes('exp') && !idLower.includes('preview')) {
            isRecommended = true;
            label += ' (Recommended)';
        }

        if (idLower.includes('exp') || idLower.includes('preview')) {
            label += ' [Exp]';
        }

        return { ...m, label, isRecommended };
    }).sort((a, b) => {
        // Recommended first
        if (a.isRecommended && !b.isRecommended) return -1;
        if (!a.isRecommended && b.isRecommended) return 1;

        if (a.isRecommended && b.isRecommended) {
            const idA = a.id.toLowerCase();
            const idB = b.id.toLowerCase();

            // 1. Prioritize 2.5 Flash Lite (best free tier capacity)
            const aIs25Lite = idA.includes('2.5-flash-lite');
            const bIs25Lite = idB.includes('2.5-flash-lite');
            if (aIs25Lite && !bIs25Lite) return -1;
            if (!aIs25Lite && bIs25Lite) return 1;

            // 2. Then regular 2.5 Flash
            const aIs25Flash = idA.includes('2.5-flash');
            const bIs25Flash = idB.includes('2.5-flash');
            if (aIs25Flash && !bIs25Flash) return -1;
            if (!aIs25Flash && bIs25Flash) return 1;

            // 3. Then "latest" aliases
            const aIsLatest = idA.includes('latest');
            const bIsLatest = idB.includes('latest');
            if (aIsLatest && !bIsLatest) return -1;
            if (!aIsLatest && bIsLatest) return 1;
        }

        return a.id.localeCompare(b.id);
    });

    for (const m of sortedModels) {
        // Filter out legacy/internal models (typically models with just numbers or weird versions)
        if (m.id.match(/^gemini-\d+\.\d+/) && !m.id.includes('1.5') && !m.id.includes('2.0')) {
            // Likely restricted preview models like 2.5-flash, skip them unless they are the currently saved one
            if (m.id !== selectedModel) continue;
        }

        const opt = document.createElement('option');
        opt.value = m.id;
        opt.textContent = m.label;
        geminiModel.appendChild(opt);
    }

    // Restore saved selection
    if (selectedModel && [...geminiModel.options].some(o => o.value === selectedModel)) {
        geminiModel.value = selectedModel;
    }
}

// ─── Folder Picker ─────────────────────────────────────────────

const browseBtn = document.getElementById('browse-dir-btn');
browseBtn.addEventListener('click', async () => {
    browseBtn.disabled = true;
    browseBtn.textContent = '⏳...';
    try {
        const response = await chrome.runtime.sendMessage({ type: 'PICK_FOLDER' });
        if (response?.path) {
            outputDir.value = response.path;
        } else if (response?.error) {
            // User cancelled or error
        }
    } catch (e) {
        // Service worker not ready
    } finally {
        browseBtn.disabled = false;
        browseBtn.textContent = '📂 Browse';
    }
});

// Slider display
silenceSlider.addEventListener('input', updateSliderLabel);

function updateSliderLabel() {
    const seconds = parseInt(silenceSlider.value);
    const minutes = Math.floor(seconds / 60);
    silenceValue.textContent = `${minutes} min`;
}

// ─── Test Groq API Key ─────────────────────────────────────────

testGroqBtn.addEventListener('click', async () => {
    const apiKey = groqKey.value.trim();
    if (!apiKey) {
        groqTestStatus.textContent = '❌ Please enter an API key first';
        groqTestStatus.style.color = '#f87171';
        return;
    }

    testGroqBtn.disabled = true;
    testGroqBtn.textContent = '⏳ Testing...';
    groqTestStatus.textContent = '';

    try {
        const url = 'https://api.groq.com/openai/v1/models';

        const response = await fetch(url, {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${apiKey}`,
                'Content-Type': 'application/json'
            }
        });

        if (response.ok) {
            groqTestStatus.textContent = '✅ Connected to Groq!';
            groqTestStatus.style.color = '#4ade80';
        } else {
            const err = await response.json();
            const msg = err?.error?.message || `HTTP ${response.status}`;
            groqTestStatus.textContent = `❌ ${msg}`;
            groqTestStatus.style.color = '#f87171';
        }
    } catch (err) {
        groqTestStatus.textContent = `❌ Network error: ${err.message}`;
        groqTestStatus.style.color = '#f87171';
    } finally {
        testGroqBtn.disabled = false;
        testGroqBtn.textContent = '🔌 Test';
    }
});

// ─── Test Gemini API Key ───────────────────────────────────────

testGeminiBtn.addEventListener('click', async () => {
    const apiKey = geminiKey.value.trim();
    if (!apiKey) {
        geminiTestStatus.textContent = '❌ Please enter an API key first';
        geminiTestStatus.style.color = '#f87171';
        return;
    }

    testGeminiBtn.disabled = true;
    testGeminiBtn.textContent = '⏳ Testing...';
    geminiTestStatus.textContent = '';

    try {
        // Use the Gemini REST API directly to test (no native host needed)
        const model = geminiModel.value || 'gemini-2.0-flash';
        const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`;

        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                contents: [{ parts: [{ text: 'Say "LectureScribe connected!" in exactly those words.' }] }],
                generationConfig: { maxOutputTokens: 20 }
            })
        });

        if (response.ok) {
            const data = await response.json();
            const text = data?.candidates?.[0]?.content?.parts?.[0]?.text || 'Connected';
            geminiTestStatus.textContent = `✅ Connected! Model: ${model}`;
            geminiTestStatus.style.color = '#4ade80';
        } else {
            const err = await response.json();
            const msg = err?.error?.message || `HTTP ${response.status}`;
            geminiTestStatus.textContent = `❌ ${msg}`;
            geminiTestStatus.style.color = '#f87171';
        }
    } catch (err) {
        geminiTestStatus.textContent = `❌ Network error: ${err.message}`;
        geminiTestStatus.style.color = '#f87171';
    } finally {
        testGeminiBtn.disabled = false;
        testGeminiBtn.textContent = '🔌 Test';
    }
});

// ─── Save ──────────────────────────────────────────────────────

saveBtn.addEventListener('click', async () => {
    const settings = {
        transcriptionEngine: engineSelect.value,
        model: modelSelect.value,
        groqModel: groqModelSelect.value,
        silenceThreshold: parseInt(silenceSlider.value),
        outputFormat: formatSelect.value,
        outputDir: outputDir.value.trim() || '~/LectureScribe',
        gdriveDir: gdriveDir.value.trim(),
        groqApiKey: groqKey.value.trim(),
        geminiApiKey: geminiKey.value.trim(),
        geminiModel: geminiModel.value,
        notionApiKey: notionKey.value.trim(),
        notionPageId: notionPageId.value.trim()
    };

    await chrome.storage.local.set({ settings });

    // Notify native host of config change
    try {
        await chrome.runtime.sendMessage({
            type: 'UPDATE_SETTINGS',
            settings
        });
    } catch (e) {
        // Service worker might not be ready
    }

    // Show saved confirmation
    saveStatus.classList.add('visible');
    setTimeout(() => saveStatus.classList.remove('visible'), 2000);
});
