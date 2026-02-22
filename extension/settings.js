/**
 * LectureScribe — Settings Controller
 */

const modelSelect = document.getElementById('model-select');
const silenceSlider = document.getElementById('silence-slider');
const silenceValue = document.getElementById('silence-value');
const formatSelect = document.getElementById('format-select');
const outputDir = document.getElementById('output-dir');
const gdriveDir = document.getElementById('gdrive-dir');
const groqKey = document.getElementById('groq-key');
const saveBtn = document.getElementById('save-btn');
const saveStatus = document.getElementById('save-status');

// Load settings
document.addEventListener('DOMContentLoaded', async () => {
    const { settings } = await chrome.storage.local.get('settings');
    if (settings) {
        modelSelect.value = settings.model || 'base';
        silenceSlider.value = settings.silenceThreshold || 600;
        formatSelect.value = settings.outputFormat || 'timestamped';
        outputDir.value = settings.outputDir || '~/LectureScribe';
        gdriveDir.value = settings.gdriveDir || '';
        groqKey.value = settings.groqApiKey || '';
        updateSliderLabel();
    }
});

// Slider display
silenceSlider.addEventListener('input', updateSliderLabel);

function updateSliderLabel() {
    const seconds = parseInt(silenceSlider.value);
    const minutes = Math.floor(seconds / 60);
    silenceValue.textContent = `${minutes} min`;
}

// Save
saveBtn.addEventListener('click', async () => {
    const settings = {
        model: modelSelect.value,
        silenceThreshold: parseInt(silenceSlider.value),
        outputFormat: formatSelect.value,
        outputDir: outputDir.value.trim() || '~/LectureScribe',
        gdriveDir: gdriveDir.value.trim(),
        groqApiKey: groqKey.value.trim()
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
