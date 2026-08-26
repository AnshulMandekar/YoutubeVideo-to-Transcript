/**
 * App Controller — Router, Modal Management, Initialization
 */

// ── Hash-based Router ─────────────────────────────────────────────────────

function navigateTo(path) {
    window.location.hash = path;
}

function getCurrentRoute() {
    const hash = window.location.hash.slice(1) || '/';
    return hash;
}

async function handleRoute() {
    const route = getCurrentRoute();

    if (route.startsWith('/video/')) {
        const videoId = route.replace('/video/', '');
        await renderVideoDetail(videoId);
    } else {
        await renderDashboard();
    }
}

window.addEventListener('hashchange', handleRoute);


// ── Modal Management ──────────────────────────────────────────────────────

function openAddModal() {
    const overlay = document.getElementById('modal-overlay');
    const inputSection = document.getElementById('modal-input');
    const processingSection = document.getElementById('modal-processing');
    const errorDiv = document.getElementById('modal-error');
    const urlInput = document.getElementById('input-youtube-url');

    // Reset to input state
    inputSection.classList.remove('hidden');
    processingSection.classList.add('hidden');
    errorDiv.textContent = '';
    urlInput.value = '';

    // Reset processing steps
    document.querySelectorAll('.step').forEach(s => {
        s.classList.remove('active', 'done');
    });

    overlay.classList.add('active');

    // Focus input
    setTimeout(() => urlInput.focus(), 300);
}

function closeAddModal() {
    const overlay = document.getElementById('modal-overlay');
    overlay.classList.remove('active');
}

// Close modal on Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeAddModal();
    }
});

// Submit on Enter key in URL input
document.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && document.activeElement?.id === 'input-youtube-url') {
        submitVideo();
    }
});


// ── Video Submission ──────────────────────────────────────────────────────

async function submitVideo() {
    const urlInput = document.getElementById('input-youtube-url');
    const errorDiv = document.getElementById('modal-error');
    const submitBtn = document.getElementById('btn-submit-url');
    const inputSection = document.getElementById('modal-input');
    const processingSection = document.getElementById('modal-processing');

    const url = urlInput.value.trim();

    // Validate
    if (!url) {
        errorDiv.textContent = 'Please enter a YouTube URL.';
        urlInput.focus();
        return;
    }

    // Basic URL validation
    const isYouTube = /^(https?:\/\/)?(www\.)?(youtube\.com|youtu\.be|m\.youtube\.com)\/.+/i.test(url) ||
                      /^[a-zA-Z0-9_-]{11}$/.test(url);

    if (!isYouTube) {
        errorDiv.textContent = 'This doesn\'t look like a valid YouTube URL.';
        urlInput.focus();
        return;
    }

    // Switch to processing state
    errorDiv.textContent = '';
    inputSection.classList.add('hidden');
    processingSection.classList.remove('hidden');

    // Animate processing steps
    const steps = ['step-metadata', 'step-transcript', 'step-notes', 'step-flowchart'];
    let currentStep = 0;

    function activateStep(index) {
        steps.forEach((stepId, i) => {
            const el = document.getElementById(stepId);
            if (i < index) {
                el.classList.remove('active');
                el.classList.add('done');
            } else if (i === index) {
                el.classList.add('active');
                el.classList.remove('done');
            } else {
                el.classList.remove('active', 'done');
            }
        });
    }

    // Start step animation
    activateStep(0);
    const stepInterval = setInterval(() => {
        currentStep++;
        if (currentStep < steps.length) {
            activateStep(currentStep);
        }
    }, 5000); // Advance step every 5 seconds visually

    try {
        const video = await api.createVideo(url);

        clearInterval(stepInterval);

        // Mark all steps done
        steps.forEach(stepId => {
            const el = document.getElementById(stepId);
            el.classList.remove('active');
            el.classList.add('done');
        });

        // Short delay to show completion
        await new Promise(r => setTimeout(r, 800));

        closeAddModal();

        if (video.status === 'done') {
            showToast('success', 'Notes generated!', `"${video.title}" is ready to view.`);
            navigateTo(`/video/${video.id}`);
        } else {
            showToast('info', 'Video added', `Status: ${video.status}`);
            // Refresh dashboard
            if (getCurrentRoute() === '/' || getCurrentRoute() === '') {
                await renderDashboard();
            }
        }
    } catch (error) {
        clearInterval(stepInterval);
        console.error('Submit failed:', error);

        // Switch back to input state with error
        processingSection.classList.add('hidden');
        inputSection.classList.remove('hidden');
        errorDiv.textContent = error.message;

        // Reset steps
        document.querySelectorAll('.step').forEach(s => {
            s.classList.remove('active', 'done');
        });

        showToast('error', 'Processing failed', error.message);
    }
}


// ── App Initialization ────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    // Initialize mermaid globally
    if (typeof mermaid !== 'undefined') {
        mermaid.initialize({
            startOnLoad: false,
            theme: 'dark',
        });
    }

    // Route to current page
    handleRoute();
});
