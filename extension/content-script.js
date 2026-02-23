/**
 * LectureScribe — Content Script
 * 
 * Injected into all pages. Detects <video> and <audio> elements,
 * monitors playback state, and notifies the service worker.
 */

(function () {
    'use strict';

    const DETECTED_ELEMENTS = new WeakSet();
    let hasVideoOnPage = false;

    /**
     * Safely send a message to the background script, ignoring "Extension context invalidated" errors
     */
    function safeSendMessage(message) {
        try {
            if (chrome.runtime && chrome.runtime.id) {
                chrome.runtime.sendMessage(message, () => {
                    if (chrome.runtime.lastError) {
                        // Context likely invalidated, ignore
                    }
                });
            }
        } catch (e) {
            // Context invalidated
        }
    }

    /**
     * Attach playback event listeners to a media element
     */
    function attachMediaListeners(element) {
        if (DETECTED_ELEMENTS.has(element)) return;
        DETECTED_ELEMENTS.add(element);

        // Notify that video exists on page
        safeSendMessage({ type: 'VIDEO_DETECTED' });
        hasVideoOnPage = true;

        element.addEventListener('play', () => {
            safeSendMessage({ type: 'VIDEO_PLAYING' });
        });

        element.addEventListener('pause', () => {
            safeSendMessage({ type: 'VIDEO_STOPPED' });
        });

        element.addEventListener('ended', () => {
            safeSendMessage({ type: 'VIDEO_STOPPED' });
        });

        // If the element is already playing, notify immediately
        if (!element.paused && !element.ended && element.readyState > 2) {
            safeSendMessage({ type: 'VIDEO_PLAYING' });
        }
    }

    /**
     * Scan the DOM for media elements
     */
    function scanForMedia() {
        const mediaElements = document.querySelectorAll('video, audio');
        mediaElements.forEach(attachMediaListeners);

        // Also check for iframes that might contain video (same-origin only)
        try {
            const iframes = document.querySelectorAll('iframe');
            iframes.forEach((iframe) => {
                try {
                    const iframeDoc = iframe.contentDocument || iframe.contentWindow?.document;
                    if (iframeDoc) {
                        const iframeMedia = iframeDoc.querySelectorAll('video, audio');
                        iframeMedia.forEach(attachMediaListeners);
                    }
                } catch (e) {
                    // Cross-origin iframe, skip
                }
            });
        } catch (e) {
            // Ignore iframe access errors
        }
    }

    /**
     * Watch for dynamically added media elements
     */
    const observer = new MutationObserver((mutations) => {
        for (const mutation of mutations) {
            for (const node of mutation.addedNodes) {
                if (node.nodeType !== Node.ELEMENT_NODE) continue;

                if (node.tagName === 'VIDEO' || node.tagName === 'AUDIO') {
                    attachMediaListeners(node);
                }

                // Check children of added nodes
                if (node.querySelectorAll) {
                    const media = node.querySelectorAll('video, audio');
                    media.forEach(attachMediaListeners);
                }
            }
        }
    });

    observer.observe(document.documentElement, {
        childList: true,
        subtree: true
    });

    // Initial scan
    scanForMedia();

    // Periodic re-scan for SPAs that create video elements dynamically
    setInterval(scanForMedia, 3000);
})();
