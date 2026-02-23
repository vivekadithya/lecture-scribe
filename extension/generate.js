/**
 * LectureScribe — Study Materials Generation Controller
 *
 * Handles feature selection, AI generation via native host,
 * results display (summary, flashcards, quiz), and Notion export.
 */

// ─── State ─────────────────────────────────────────────────────

let sessionId = null;
let generationResults = null;
let currentFlashcardIndex = 0;
let flashcards = [];
let quizAnswers = {};

// ─── DOM Elements ──────────────────────────────────────────────

const generateBtn = document.getElementById('generate-btn');
const featureSelection = document.getElementById('feature-selection');
const progressSection = document.getElementById('progress-section');
const progressText = document.getElementById('progress-text');
const progressFill = document.getElementById('progress-fill');
const resultsSection = document.getElementById('results-section');
const errorSection = document.getElementById('error-section');
const errorMessage = document.getElementById('error-message');
const retryBtn = document.getElementById('retry-btn');
const copyResultsBtn = document.getElementById('copy-results-btn');
const exportNotionBtn = document.getElementById('export-notion-btn');
const exportStatus = document.getElementById('export-status');

// ─── Initialization ────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
    // Get session ID from URL params
    const params = new URLSearchParams(window.location.search);
    sessionId = params.get('session');

    if (sessionId) {
        document.getElementById('session-label').textContent = `Session: ${sessionId}`;
    }

    // Load saved custom prompts
    const { settings } = await chrome.storage.local.get('settings');
    if (settings?.customPrompts) {
        if (settings.customPrompts.summary) {
            document.getElementById('prompt-summary').value = settings.customPrompts.summary;
        }
        if (settings.customPrompts.flashcards) {
            document.getElementById('prompt-flashcards').value = settings.customPrompts.flashcards;
        }
        if (settings.customPrompts.quiz) {
            document.getElementById('prompt-quiz').value = settings.customPrompts.quiz;
        }
    }

    // Load default feature selection
    if (settings?.defaultFeatures) {
        document.getElementById('feat-summary').checked = settings.defaultFeatures.includes('summary');
        document.getElementById('feat-flashcards').checked = settings.defaultFeatures.includes('flashcards');
        document.getElementById('feat-quiz').checked = settings.defaultFeatures.includes('quiz');
    }
});

// ─── Event Listeners ───────────────────────────────────────────

generateBtn.addEventListener('click', startGeneration);
retryBtn.addEventListener('click', () => {
    errorSection.classList.add('hidden');
    featureSelection.classList.remove('hidden');
});

// Tab switching
document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById(`tab-${tab.dataset.tab}`).classList.add('active');
    });
});

// Flashcard navigation
document.getElementById('flashcard-flip').addEventListener('click', flipFlashcard);
document.getElementById('flashcard-prev').addEventListener('click', () => navigateFlashcard(-1));
document.getElementById('flashcard-next').addEventListener('click', () => navigateFlashcard(1));

// Export
copyResultsBtn.addEventListener('click', copyResults);
exportNotionBtn.addEventListener('click', exportToNotion);

// ─── Generation ────────────────────────────────────────────────

async function startGeneration() {
    const features = getSelectedFeatures();
    if (features.length === 0) {
        alert('Please select at least one feature to generate.');
        return;
    }

    const customPrompts = getCustomPrompts();

    // Show progress
    featureSelection.classList.add('hidden');
    progressSection.classList.remove('hidden');
    errorSection.classList.add('hidden');
    progressFill.style.width = '10%';
    progressText.textContent = 'Connecting to AI engine...';

    try {
        // Start generation via service worker → native host
        const response = await chrome.runtime.sendMessage({
            type: 'GENERATE_STUDY_MATERIALS',
            sessionId,
            features,
            customPrompts
        });

        if (response?.error) {
            showError(response.error);
            return;
        }

        // Poll for results (native host will send GENERATION_COMPLETE)
        progressFill.style.width = '30%';
        progressText.textContent = `Generating ${features.join(', ')} with Gemini AI...`;

        // Wait for generation to complete
        await waitForGeneration();

    } catch (err) {
        showError(err.message || 'Generation failed. Check your Gemini API key in Settings.');
    }
}

function getSelectedFeatures() {
    const features = [];
    if (document.getElementById('feat-summary').checked) features.push('summary');
    if (document.getElementById('feat-flashcards').checked) features.push('flashcards');
    if (document.getElementById('feat-quiz').checked) features.push('quiz');
    return features;
}

function getCustomPrompts() {
    const prompts = {};
    const summary = document.getElementById('prompt-summary').value.trim();
    const flashcards = document.getElementById('prompt-flashcards').value.trim();
    const quiz = document.getElementById('prompt-quiz').value.trim();
    if (summary) prompts.summary = summary;
    if (flashcards) prompts.flashcards = flashcards;
    if (quiz) prompts.quiz = quiz;
    return prompts;
}

async function waitForGeneration() {
    let progress = 30;

    return new Promise((resolve, reject) => {
        const progressInterval = setInterval(() => {
            if (progress < 85) {
                progress += Math.random() * 5;
                progressFill.style.width = `${progress}%`;
            }
        }, 500);

        // Listen for generation result
        const listener = (message) => {
            if (message.type === 'GENERATION_COMPLETE') {
                clearInterval(progressInterval);
                progressFill.style.width = '100%';
                progressText.textContent = 'Done!';

                generationResults = message.results;

                setTimeout(() => {
                    progressSection.classList.add('hidden');

                    // Check if all requested features failed with an error
                    const hasValidResults = Object.values(message.results).some(res => !res.error);

                    if (!hasValidResults) {
                        const firstError = Object.values(message.results).find(res => res.error)?.error || 'Generation failed.';
                        showError('API Error: ' + firstError);
                    } else {
                        displayResults(message.results);
                        resultsSection.classList.remove('hidden');

                        // If some failed but not all, maybe show a toast warning? 
                        // For now just showing valid ones is fine.
                    }
                }, 500);

                chrome.runtime.onMessage.removeListener(listener);
                resolve();
            } else if (message.type === 'ERROR' && message.messageType === 'GENERATE') {
                clearInterval(progressInterval);
                chrome.runtime.onMessage.removeListener(listener);
                showError(message.error);
                reject(new Error(message.error));
            } else if (message.type === 'GENERATION_PROGRESS') {
                progressText.textContent = `Generating ${message.status}...`;
            }
        };

        chrome.runtime.onMessage.addListener(listener);

        // Timeout after 120 seconds
        const timeoutId = setTimeout(() => {
            clearInterval(progressInterval);
            chrome.runtime.onMessage.removeListener(listener);
            showError('Generation timed out. The transcript may be too long or the API is overloaded.');
            reject(new Error('Timeout'));
        }, 120000);

        // Update listener to clear timeout
        const originalResolve = resolve;
        const originalReject = reject;

        const cleanupAndFinish = (fn, ...args) => {
            clearTimeout(timeoutId);
            fn(...args);
        };

        // We override the local references to ensure they clear the timeout
        resolve = (val) => cleanupAndFinish(originalResolve, val);
        reject = (err) => cleanupAndFinish(originalReject, err);
    });
}

// ─── Display Results ───────────────────────────────────────────

function displayResults(results) {
    // Show/hide tabs based on what was generated
    document.querySelectorAll('.tab').forEach(tab => {
        const feature = tab.dataset.tab;
        if (results[feature] && !results[feature].error) {
            tab.classList.remove('hidden');
        } else {
            tab.classList.add('hidden');
        }
    });

    // Activate first available tab
    const firstTab = document.querySelector('.tab:not(.hidden)');
    if (firstTab) {
        firstTab.click();
    }

    // Render each feature
    if (results.summary && !results.summary.error) {
        renderSummary(results.summary);
    }
    if (results.flashcards && !results.flashcards.error) {
        renderFlashcards(results.flashcards);
    }
    if (results.quiz && !results.quiz.error) {
        renderQuiz(results.quiz);
    }
}

// ─── Summary Rendering ────────────────────────────────────────

function renderSummary(data) {
    const container = document.getElementById('summary-content');
    let html = '';

    if (data.action_items?.length) {
        html += '<h3>📋 Action Items</h3><ul>';
        for (const item of data.action_items) {
            html += `<li>${escapeHTML(item)}</li>`;
        }
        html += '</ul>';
    }

    if (data.key_points?.length) {
        html += '<h3>🎯 Key Points</h3><ul>';
        for (const point of data.key_points) {
            html += `<li>${escapeHTML(point)}</li>`;
        }
        html += '</ul>';
    }

    if (data.topics?.length) {
        html += '<h3>📚 Topics</h3>';
        for (const topic of data.topics) {
            html += `<div class="topic-card">
                <h4>${escapeHTML(topic.topic || 'Untitled')}</h4>
                <p>${escapeHTML(topic.summary || '')}</p>`;
            if (topic.key_terms?.length) {
                html += '<div class="key-terms">';
                for (const term of topic.key_terms) {
                    html += `<span class="key-term">${escapeHTML(term)}</span>`;
                }
                html += '</div>';
            }
            html += '</div>';
        }
    }

    container.innerHTML = html;
}

// ─── Flashcard Rendering ──────────────────────────────────────

function renderFlashcards(data) {
    flashcards = data.flashcards || [];
    currentFlashcardIndex = 0;
    showFlashcard(0);
}

function showFlashcard(index) {
    if (index < 0 || index >= flashcards.length) return;
    currentFlashcardIndex = index;

    const card = flashcards[index];
    document.getElementById('flashcard-question').textContent = card.question;
    document.getElementById('flashcard-answer').textContent = card.answer;
    document.getElementById('flashcard-counter').textContent = `${index + 1} / ${flashcards.length}`;

    // Show front (question) by default
    document.getElementById('flashcard-front').classList.remove('hidden');
    document.getElementById('flashcard-back').classList.add('hidden');

    // Update prev/next button states
    document.getElementById('flashcard-prev').disabled = index === 0;
    document.getElementById('flashcard-next').disabled = index === flashcards.length - 1;
}

function flipFlashcard() {
    const front = document.getElementById('flashcard-front');
    const back = document.getElementById('flashcard-back');
    front.classList.toggle('hidden');
    back.classList.toggle('hidden');
}

function navigateFlashcard(direction) {
    const newIndex = currentFlashcardIndex + direction;
    if (newIndex >= 0 && newIndex < flashcards.length) {
        showFlashcard(newIndex);
    }
}

// ─── Quiz Rendering ───────────────────────────────────────────

function renderQuiz(data) {
    const container = document.getElementById('quiz-content');
    let html = '';
    let questionNum = 0;

    // Multiple Choice
    const mcqs = data.multiple_choice || [];
    if (mcqs.length) {
        html += '<p class="quiz-section-title">Multiple Choice</p>';
        for (const q of mcqs) {
            questionNum++;
            html += `<div class="quiz-question" data-type="mcq" data-num="${questionNum}" data-correct="${escapeAttr(q.correct_answer)}">
                <p class="quiz-question-text">${questionNum}. ${escapeHTML(q.question)}</p>
                <div class="quiz-options">`;
            for (const opt of (q.options || [])) {
                const letter = opt.charAt(0);
                html += `<div class="quiz-option" data-value="${escapeAttr(letter)}">
                    ${escapeHTML(opt)}
                </div>`;
            }
            html += `</div>
                <div class="quiz-explanation" id="explanation-${questionNum}">${escapeHTML(q.explanation || '')}</div>
            </div>`;
        }
    }

    // Short Answer
    const short = data.short_answer || [];
    if (short.length) {
        html += '<p class="quiz-section-title">Short Answer</p>';
        for (const q of short) {
            questionNum++;
            html += `<div class="quiz-question" data-type="short" data-num="${questionNum}">
                <p class="quiz-question-text">${questionNum}. ${escapeHTML(q.question)}</p>
                <textarea class="quiz-short-answer" placeholder="Type your answer..." rows="2"
                    style="width:100%;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:8px;padding:10px;font-size:13px;resize:vertical;margin-top:8px;"></textarea>
                <div class="quiz-explanation" id="explanation-${questionNum}"><strong>Sample answer:</strong> ${escapeHTML(q.sample_answer || '')}</div>
            </div>`;
        }
    }

    // True/False
    const tf = data.true_false || [];
    if (tf.length) {
        html += '<p class="quiz-section-title">True or False</p>';
        for (const q of tf) {
            questionNum++;
            const correctStr = q.answer ? 'True' : 'False';
            html += `<div class="quiz-question" data-type="tf" data-num="${questionNum}" data-correct="${correctStr}">
                <p class="quiz-question-text">${questionNum}. ${escapeHTML(q.statement)}</p>
                <div class="quiz-options">
                    <div class="quiz-option" data-value="True">True</div>
                    <div class="quiz-option" data-value="False">False</div>
                </div>
                <div class="quiz-explanation" id="explanation-${questionNum}">${escapeHTML(q.explanation || '')}</div>
            </div>`;
        }
    }

    html += `<div class="quiz-submit-row">
        <button class="btn btn-primary" data-action="submit-quiz">✅ Check Answers</button>
    </div>`;

    container.innerHTML = html;

    // Add event delegation for quiz interactivity (CSP-safe)
    container.addEventListener('click', (e) => {
        const option = e.target.closest('.quiz-option');
        if (option) {
            selectOption(option);
            return;
        }
        const submitBtn = e.target.closest('[data-action="submit-quiz"]');
        if (submitBtn) {
            submitQuiz();
        }
    });
}

function selectOption(el) {
    // Deselect siblings
    el.parentElement.querySelectorAll('.quiz-option').forEach(o => o.classList.remove('selected'));
    el.classList.add('selected');

    const questionEl = el.closest('.quiz-question');
    const num = questionEl.dataset.num;
    quizAnswers[num] = el.dataset.value;
}

function submitQuiz() {
    let total = 0;
    let correct = 0;

    document.querySelectorAll('.quiz-question').forEach(q => {
        const type = q.dataset.type;
        const num = q.dataset.num;

        if (type === 'mcq' || type === 'tf') {
            total++;
            const correctAnswer = q.dataset.correct;
            const userAnswer = quizAnswers[num];

            q.querySelectorAll('.quiz-option').forEach(opt => {
                if (opt.dataset.value.startsWith(correctAnswer)) {
                    opt.classList.add('correct');
                } else if (opt.classList.contains('selected') && !opt.dataset.value.startsWith(correctAnswer)) {
                    opt.classList.add('incorrect');
                }
            });

            if (userAnswer && userAnswer.startsWith(correctAnswer)) {
                correct++;
            }
        }

        // Show explanations
        const explanation = document.getElementById(`explanation-${num}`);
        if (explanation) {
            explanation.classList.add('visible');
        }
    });

    // Show score
    const scoreSection = document.getElementById('quiz-score');
    scoreSection.classList.remove('hidden');
    document.getElementById('score-text').textContent = `${correct} / ${total}`;
}

// ─── Export Functions ──────────────────────────────────────────

async function copyResults() {
    if (!generationResults) return;

    let text = '';

    if (generationResults.summary) {
        text += '# SUMMARY\n\n';
        if (generationResults.summary.key_points) {
            text += '## Key Points\n';
            generationResults.summary.key_points.forEach(p => text += `- ${p}\n`);
        }
        if (generationResults.summary.action_items) {
            text += '\n## Action Items\n';
            generationResults.summary.action_items.forEach(a => text += `- [ ] ${a}\n`);
        }
        text += '\n';
    }

    if (generationResults.flashcards?.flashcards) {
        text += '# FLASHCARDS\n\n';
        generationResults.flashcards.flashcards.forEach((c, i) => {
            text += `Q${i + 1}: ${c.question}\nA: ${c.answer}\n\n`;
        });
    }

    await navigator.clipboard.writeText(text);
    copyResultsBtn.textContent = '✅ Copied!';
    setTimeout(() => { copyResultsBtn.textContent = '📋 Copy'; }, 2000);
}

async function exportToNotion() {
    if (!generationResults) return;

    exportNotionBtn.disabled = true;
    exportStatus.textContent = 'Exporting to Notion...';

    try {
        const response = await chrome.runtime.sendMessage({
            type: 'EXPORT_TO_NOTION',
            sessionId,
            results: generationResults
        });

        if (response?.error) {
            exportStatus.textContent = `❌ ${response.error}`;
        } else {
            exportStatus.textContent = '✅ Exported to Notion!';
        }
    } catch (err) {
        exportStatus.textContent = `❌ ${err.message}`;
    } finally {
        exportNotionBtn.disabled = false;
    }
}

// ─── Error Handling ───────────────────────────────────────────

function showError(message) {
    progressSection.classList.add('hidden');
    featureSelection.classList.add('hidden');
    resultsSection.classList.add('hidden');
    errorSection.classList.remove('hidden');
    errorMessage.textContent = message;
}

// ─── Utilities ────────────────────────────────────────────────

function escapeHTML(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function escapeAttr(str) {
    if (!str) return '';
    return str.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
