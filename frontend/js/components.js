/**
 * Reusable UI Components — Toast, Skeleton, Status Badges, etc.
 */

// ── Toast Notification System ─────────────────────────────────────────────

function showToast(type, title, message = '', duration = 5000) {
    const container = document.getElementById('toast-container');
    const icons = {
        success: '✅',
        error: '❌',
        info: 'ℹ️',
        warning: '⚠️',
    };

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <span class="toast-icon">${icons[type] || 'ℹ️'}</span>
        <div class="toast-content">
            <div class="toast-title">${escapeHtml(title)}</div>
            ${message ? `<div class="toast-message">${escapeHtml(message)}</div>` : ''}
        </div>
        <button class="toast-close" onclick="this.parentElement.remove()">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
        </button>
    `;

    container.appendChild(toast);

    // Auto-remove
    setTimeout(() => {
        toast.classList.add('toast-leaving');
        setTimeout(() => toast.remove(), 300);
    }, duration);
}


// ── Skeleton Loaders ──────────────────────────────────────────────────────

function renderSkeletonCards(count = 6) {
    let html = '';
    for (let i = 0; i < count; i++) {
        html += `
            <div class="skeleton-card">
                <div class="skeleton skeleton-thumbnail"></div>
                <div class="skeleton skeleton-text" style="width: ${70 + Math.random() * 25}%"></div>
                <div class="skeleton skeleton-text skeleton-text-short"></div>
                <div class="skeleton skeleton-text-xs"></div>
            </div>
        `;
    }
    return html;
}


// ── Status Badge ──────────────────────────────────────────────────────────

function renderStatusBadge(status) {
    const labels = {
        pending: 'Pending',
        fetching_metadata: 'Fetching…',
        fetching_transcript: 'Transcript…',
        transcribing_audio: 'Transcribing…',
        generating_notes: 'Generating…',
        generating_flowchart: 'Flowchart…',
        done: 'Ready',
        failed: 'Failed',
    };
    const label = labels[status] || status;
    return `<span class="status-badge status-badge-${status}">${label}</span>`;
}


// ── Tag Chip ──────────────────────────────────────────────────────────────

function renderTag(tag, isActive = false, small = false) {
    const classes = ['tag'];
    if (isActive) classes.push('active');
    if (small) classes.push('tag-small');
    return `<span class="${classes.join(' ')}" data-tag="${escapeHtml(tag)}">${escapeHtml(tag)}</span>`;
}


// ── Video Card ────────────────────────────────────────────────────────────

function renderVideoCard(video) {
    const thumbnail = video.thumbnail_url || `https://img.youtube.com/vi/${video.video_id}/mqdefault.jpg`;
    const title = video.title || 'Processing...';
    const channel = video.channel || '';
    const date = video.created_at ? formatDate(video.created_at) : '';
    const tags = (video.tags || []).slice(0, 3);

    return `
        <div class="video-card" onclick="navigateTo('/video/${video.id}')" data-video-id="${video.id}">
            <div class="video-card-thumbnail">
                <img src="${escapeHtml(thumbnail)}" alt="${escapeHtml(title)}" loading="lazy"
                     onerror="this.src='https://img.youtube.com/vi/${video.video_id}/mqdefault.jpg'">
                ${video.duration ? `<span class="video-card-duration">${escapeHtml(video.duration)}</span>` : ''}
            </div>
            <div class="video-card-body">
                <h3 class="video-card-title">${escapeHtml(title)}</h3>
                <p class="video-card-channel">${escapeHtml(channel)}</p>
            </div>
            <div class="video-card-footer">
                <div class="video-card-tags">
                    ${tags.map(t => renderTag(t, false, true)).join('')}
                </div>
                <span class="video-card-date">${date}</span>
            </div>
        </div>
    `;
}


// ── Utility Functions ─────────────────────────────────────────────────────

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function formatDate(dateStr) {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function parseTimestampToSeconds(timestamp) {
    if (!timestamp) return 0;
    const parts = timestamp.split(':').map(Number);
    if (parts.length === 3) {
        return parts[0] * 3600 + parts[1] * 60 + parts[2];
    } else if (parts.length === 2) {
        return parts[0] * 60 + parts[1];
    }
    return 0;
}

function downloadFile(content, filename) {
    const blob = new Blob([content], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}
