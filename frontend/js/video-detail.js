/**
 * Video Detail View — Notes, Flowchart, Embedded Player
 */

let currentVideoData = null;
let youtubePlayer = null;


async function renderVideoDetail(videoId) {
    const main = document.getElementById('main-content');

    // Show loading skeleton
    main.innerHTML = `
        <div class="fade-in">
            <button class="detail-back" onclick="navigateTo('/')">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="15 18 9 12 15 6"></polyline>
                </svg>
                Back to Library
            </button>
            <div style="margin-top: 24px;">
                <div class="skeleton" style="height: 32px; width: 70%; margin-bottom: 12px;"></div>
                <div class="skeleton" style="height: 16px; width: 40%; margin-bottom: 32px;"></div>
                <div class="skeleton" style="height: 300px; border-radius: 16px; margin-bottom: 24px;"></div>
                <div class="skeleton" style="height: 200px; border-radius: 16px;"></div>
            </div>
        </div>
    `;

    try {
        const video = await api.getVideo(videoId);
        currentVideoData = video;
        renderDetailContent(video);
    } catch (error) {
        console.error('Failed to load video:', error);
        showToast('error', 'Failed to load video', error.message);
        main.innerHTML = `
            <div class="empty-state">
                <span class="empty-state-icon">😞</span>
                <h2 class="empty-state-title">Video not found</h2>
                <p class="empty-state-text">${escapeHtml(error.message)}</p>
                <button class="btn btn-primary" onclick="navigateTo('/')">Back to Library</button>
            </div>
        `;
    }
}


function renderDetailContent(video) {
    const main = document.getElementById('main-content');
    const notes = video.notes;
    const hasNotes = notes && notes.sections && notes.sections.length > 0;
    const hasFlowchart = video.flowchart && video.flowchart.trim();
    const hasTakeaways = notes && notes.key_takeaways && notes.key_takeaways.length > 0;
    const chatHistory = video.chat_history || [];

    main.innerHTML = `
        <div class="fade-in">
            <!-- Header -->
            <div class="detail-header">
                <button class="detail-back" onclick="navigateTo('/')">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="15 18 9 12 15 6"></polyline>
                    </svg>
                    Back to Library
                </button>
                <h1 class="detail-title">${escapeHtml(video.title || 'Untitled Video')}</h1>
                <div class="detail-meta">
                    <span class="detail-meta-item">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
                        ${escapeHtml(video.channel || 'Unknown Channel')}
                    </span>
                    ${video.duration ? `
                    <span class="detail-meta-item">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
                        ${escapeHtml(video.duration)}
                    </span>` : ''}
                    ${renderStatusBadge(video.status)}
                </div>
                ${(video.tags && video.tags.length > 0) ? `
                <div class="detail-tags">
                    ${video.tags.map(t => renderTag(t)).join('')}
                </div>` : ''}
                <div class="detail-actions">
                    <button class="btn btn-secondary btn-sm" onclick="exportNotes('${video.id}')">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                            <polyline points="7 10 12 15 17 10"></polyline>
                            <line x1="12" y1="15" x2="12" y2="3"></line>
                        </svg>
                        <span>Export Markdown</span>
                    </button>
                    <button class="btn btn-danger btn-sm" onclick="deleteVideoConfirm('${video.id}')">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="3 6 5 6 21 6"></polyline>
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                        </svg>
                        <span>Delete</span>
                    </button>
                </div>
            </div>

            <!-- Layout Grid -->
            <div class="detail-layout">
                <!-- Player -->
                <div class="player-section">
                    <div class="player-wrapper">
                        <iframe
                            id="youtube-player"
                            src="https://www.youtube.com/embed/${video.video_id}?enablejsapi=1&rel=0"
                            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                            allowfullscreen>
                        </iframe>
                    </div>
                </div>

                <!-- Key Takeaways (if available) -->
                ${hasTakeaways ? `
                <div class="takeaways-section">
                    <div class="section-title">
                        <span class="section-title-icon">💡</span>
                        Key Takeaways
                    </div>
                    <ul class="takeaways-list">
                        ${notes.key_takeaways.map(t => `<li>${escapeHtml(t)}</li>`).join('')}
                    </ul>
                </div>` : ''}

                <!-- Notes -->
                ${hasNotes ? `
                <div class="notes-section detail-layout-full">
                    <div class="section-header">
                        <div class="section-title">
                            <span class="section-title-icon">📝</span>
                            Lecture Notes
                        </div>
                        <span style="color: var(--text-tertiary); font-size: 0.82rem;">${notes.sections.length} sections</span>
                    </div>
                    ${notes.summary ? `
                    <div class="notes-summary">
                        <div class="notes-summary-label">Summary</div>
                        <div class="notes-summary-text">${escapeHtml(notes.summary)}</div>
                    </div>` : ''}
                    <div id="notes-accordion">
                        ${notes.sections.map((section, i) => renderNoteAccordion(section, i, video.video_id)).join('')}
                    </div>
                </div>` : (video.status === 'failed' ? `
                <div class="notes-section detail-layout-full" style="padding: var(--space-xl);">
                    <div class="empty-state" style="padding: var(--space-lg);">
                        <span class="empty-state-icon">⚠️</span>
                        <h2 class="empty-state-title">Processing Failed</h2>
                        <p class="empty-state-text">${escapeHtml(video.error_message || 'An unknown error occurred.')}</p>
                    </div>
                </div>` : '')}

                <!-- Chat with Notes Section -->
                ${hasNotes ? `
                <div class="chat-section detail-layout-full" id="chat-section">
                    <div class="section-header chat-header">
                        <div class="chat-header-title-group">
                            <div class="section-title">
                                <span class="section-title-icon">💬</span>
                                Chat with Notes
                            </div>
                            <span class="chat-badge" id="chat-msg-count">${chatHistory.length} saved</span>
                        </div>
                        <div class="chat-header-actions">
                            <button class="btn btn-secondary btn-sm" id="btn-clear-chat" onclick="clearChatConfirm('${video.id}')" ${chatHistory.length === 0 ? 'style="display:none;"' : ''}>
                                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <polyline points="3 6 5 6 21 6"></polyline>
                                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                                </svg>
                                <span>Clear Chat</span>
                            </button>
                        </div>
                    </div>

                    <!-- Suggested prompt chips -->
                    <div class="chat-suggestions" id="chat-suggestions">
                        <span class="suggestions-label">Try asking:</span>
                        <button class="suggestion-chip" onclick="handleQuickPrompt('${video.id}', 'Summarize the main takeaways of this lecture in simple terms.')">
                            💡 Summarize in simple terms
                        </button>
                        <button class="suggestion-chip" onclick="handleQuickPrompt('${video.id}', 'Give me a 3-question practice quiz based on this lecture with answers.')">
                            ❓ Quiz me on this lecture
                        </button>
                        <button class="suggestion-chip" onclick="handleQuickPrompt('${video.id}', 'Explain the key terms and concepts with real-world examples.')">
                            🔍 Explain key terms with examples
                        </button>
                        <button class="suggestion-chip" onclick="handleQuickPrompt('${video.id}', 'What are the most practical takeaways I should remember?')">
                            ⚡ Practical applications
                        </button>
                    </div>

                    <!-- Chat messages scroll box -->
                    <div class="chat-messages" id="chat-messages-box">
                        ${renderChatMessagesList(chatHistory)}
                    </div>

                    <!-- Typing indicator -->
                    <div class="chat-typing-indicator hidden" id="chat-typing-indicator">
                        <div class="typing-dots">
                            <div class="dot"></div>
                            <div class="dot"></div>
                            <div class="dot"></div>
                        </div>
                        <span class="typing-text">AI Tutor is reviewing your lecture notes...</span>
                    </div>

                    <!-- Chat input bar -->
                    <form class="chat-input-form" id="chat-input-form" onsubmit="handleChatSubmit(event, '${video.id}')">
                        <div class="chat-input-wrapper">
                            <textarea
                                id="chat-user-input"
                                class="chat-input-field"
                                placeholder="Ask a question about this lecture... (Shift+Enter for new line)"
                                rows="1"
                                onkeydown="handleChatInputKeydown(event, '${video.id}')"
                                oninput="autoExpandChatInput(this)"
                            ></textarea>
                            <button type="submit" class="btn btn-primary chat-send-btn" id="btn-chat-send">
                                <span>Send</span>
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                                    <line x1="22" y1="2" x2="11" y2="13"></line>
                                    <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
                                </svg>
                            </button>
                        </div>
                    </form>
                </div>` : ''}

                <!-- Flowchart -->
                ${hasFlowchart ? `
                <div class="flowchart-section detail-layout-full">
                    <div class="section-header">
                        <div class="section-title">
                            <span class="section-title-icon">🔀</span>
                            Concept Map
                        </div>
                    </div>
                    <div class="flowchart-container" id="flowchart-container">
                        <pre class="mermaid">${escapeHtml(video.flowchart)}</pre>
                    </div>
                </div>` : ''}
            </div>
        </div>
    `;

    // Initialize Mermaid for flowcharts
    if (hasFlowchart) {
        initMermaid();
    }

    // Scroll chat box to bottom on initial render if messages exist
    scrollChatToBottom();
}


function renderNoteAccordion(section, index, videoId) {
    const isFirst = index === 0;
    return `
        <div class="note-accordion ${isFirst ? 'open' : ''}" data-index="${index}">
            <div class="note-accordion-header" onclick="toggleAccordion(this)">
                <svg class="note-accordion-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="9 18 15 12 9 6"></polyline>
                </svg>
                <span class="note-accordion-heading">${escapeHtml(section.heading)}</span>
                ${section.timestamp ? `
                <span class="note-accordion-timestamp" onclick="event.stopPropagation(); seekTo('${section.timestamp}', '${videoId}')"
                      title="Jump to ${section.timestamp}">
                    ${escapeHtml(section.timestamp)}
                </span>` : ''}
            </div>
            <div class="note-accordion-body">
                ${section.subpoints && section.subpoints.length > 0 ? `
                <ul class="note-subpoints">
                    ${section.subpoints.map(p => `<li>${escapeHtml(p)}</li>`).join('')}
                </ul>` : ''}
                ${section.key_terms && section.key_terms.length > 0 ? `
                <div class="note-key-terms">
                    ${section.key_terms.map(t => `<span class="key-term">${escapeHtml(t)}</span>`).join('')}
                </div>` : ''}
            </div>
        </div>
    `;
}


function toggleAccordion(header) {
    const accordion = header.parentElement;
    accordion.classList.toggle('open');
}


function seekTo(timestamp, videoId) {
    const seconds = parseTimestampToSeconds(timestamp);
    const iframe = document.getElementById('youtube-player');
    if (iframe) {
        // Update the iframe src with the start time
        iframe.src = `https://www.youtube.com/embed/${videoId}?enablejsapi=1&rel=0&start=${seconds}&autoplay=1`;
    }
    showToast('info', `Jumping to ${timestamp}`);
}


function initMermaid() {
    try {
        mermaid.initialize({
            startOnLoad: true,
            theme: 'dark',
            themeVariables: {
                primaryColor: '#7c3aed',
                primaryTextColor: '#f0eeff',
                primaryBorderColor: '#6366f1',
                lineColor: '#6366f1',
                secondaryColor: '#1c1c40',
                tertiaryColor: '#161630',
                fontFamily: 'Inter, sans-serif',
                fontSize: '13px',
            },
            flowchart: {
                useMaxWidth: true,
                htmlLabels: true,
                curve: 'basis',
            },
        });
        mermaid.run();
    } catch (e) {
        console.warn('Mermaid rendering failed:', e);
    }
}


async function exportNotes(videoId) {
    try {
        const markdown = await api.exportMarkdown(videoId);
        const video = currentVideoData;
        const filename = `${(video?.video_id || 'notes')}_lecture_notes.md`;
        downloadFile(markdown, filename);
        showToast('success', 'Notes exported!', `Saved as ${filename}`);
    } catch (error) {
        showToast('error', 'Export failed', error.message);
    }
}


async function deleteVideoConfirm(videoId) {
    if (!confirm('Are you sure you want to delete this video and its notes? This cannot be undone.')) {
        return;
    }

    try {
        await api.deleteVideo(videoId);
        showToast('success', 'Video deleted');
        navigateTo('/');
    } catch (error) {
        showToast('error', 'Delete failed', error.message);
    }
}


// ── Chat Interactive Functions ──────────────────────────────────────────────


function formatMarkdown(text) {
    if (typeof marked !== 'undefined' && typeof marked.parse === 'function') {
        try {
            return marked.parse(text);
        } catch (e) {
            console.error('Marked parsing error:', e);
        }
    }
    return escapeHtml(text).replace(/\n/g, '<br>');
}


function formatChatTimestamp(isoString) {
    if (!isoString) return '';
    try {
        const date = new Date(isoString);
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch {
        return '';
    }
}


function renderChatMessage(msg) {
    const isUser = msg.role === 'user';
    const timeStr = formatChatTimestamp(msg.created_at);

    if (isUser) {
        return `
            <div class="chat-message chat-message-user">
                <div class="chat-bubble chat-bubble-user">
                    <div class="chat-message-content">${escapeHtml(msg.content)}</div>
                    ${timeStr ? `<span class="chat-time">${timeStr}</span>` : ''}
                </div>
            </div>
        `;
    } else {
        const renderedHtml = formatMarkdown(msg.content);
        return `
            <div class="chat-message chat-message-assistant">
                <div class="chat-avatar" title="AI Tutor">✨</div>
                <div class="chat-bubble chat-bubble-assistant">
                    <div class="chat-message-content markdown-body">${renderedHtml}</div>
                    <div class="chat-assistant-footer">
                        ${timeStr ? `<span class="chat-time">${timeStr}</span>` : ''}
                        <button class="chat-copy-btn" onclick="copyChatResponse(this, ${JSON.stringify(msg.content).replace(/"/g, '&quot;')})" title="Copy answer">
                            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                            </svg>
                            <span>Copy</span>
                        </button>
                    </div>
                </div>
            </div>
        `;
    }
}


function renderChatMessagesList(chatHistory) {
    if (!chatHistory || chatHistory.length === 0) {
        return `
            <div class="chat-empty-state" id="chat-empty-state">
                <div class="chat-empty-icon">💡</div>
                <h3 class="chat-empty-title">Ask your lecture notes anything</h3>
                <p class="chat-empty-subtitle">Have questions on this topic? Ask below to get instant explanations, summaries, or test quizzes based on your lecture context.</p>
            </div>
        `;
    }
    return chatHistory.map(msg => renderChatMessage(msg)).join('');
}


function scrollChatToBottom() {
    const box = document.getElementById('chat-messages-box');
    if (box) {
        setTimeout(() => {
            box.scrollTop = box.scrollHeight;
        }, 50);
    }
}


function autoExpandChatInput(textarea) {
    textarea.style.height = 'auto';
    const newHeight = Math.min(textarea.scrollHeight, 160);
    textarea.style.height = `${newHeight}px`;
}


function handleChatInputKeydown(event, videoId) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        handleChatSubmit(event, videoId);
    }
}


function handleQuickPrompt(videoId, promptText) {
    const input = document.getElementById('chat-user-input');
    if (input) {
        input.value = promptText;
        autoExpandChatInput(input);
        input.focus();
        handleChatSubmit(null, videoId);
    }
}


async function handleChatSubmit(event, videoId) {
    if (event && event.preventDefault) {
        event.preventDefault();
    }

    const input = document.getElementById('chat-user-input');
    const sendBtn = document.getElementById('btn-chat-send');
    const messagesBox = document.getElementById('chat-messages-box');
    const emptyState = document.getElementById('chat-empty-state');
    const typingIndicator = document.getElementById('chat-typing-indicator');
    const clearBtn = document.getElementById('btn-clear-chat');
    const countBadge = document.getElementById('chat-msg-count');

    if (!input) return;
    const message = input.value.trim();
    if (!message) return;

    // Reset input
    input.value = '';
    input.style.height = 'auto';
    input.disabled = true;
    if (sendBtn) sendBtn.disabled = true;

    // Remove empty state if visible
    if (emptyState) {
        emptyState.remove();
    }

    // Optimistically render user message
    const tempUserMsg = {
        role: 'user',
        content: message,
        created_at: new Date().toISOString(),
    };
    messagesBox.insertAdjacentHTML('beforeend', renderChatMessage(tempUserMsg));
    scrollChatToBottom();

    // Show typing indicator
    if (typingIndicator) {
        typingIndicator.classList.remove('hidden');
        scrollChatToBottom();
    }

    try {
        const res = await api.sendChatMessage(videoId, message);

        // Hide typing indicator
        if (typingIndicator) {
            typingIndicator.classList.add('hidden');
        }

        // Render assistant response
        const assistantMsg = {
            role: 'assistant',
            content: res.reply,
            created_at: new Date().toISOString(),
        };
        messagesBox.insertAdjacentHTML('beforeend', renderChatMessage(assistantMsg));
        scrollChatToBottom();

        // Update local video data
        if (currentVideoData) {
            currentVideoData.chat_history = res.chat_history || [];
        }

        // Show clear button and update count badge
        if (clearBtn) clearBtn.style.display = 'inline-flex';
        if (countBadge && res.chat_history) {
            countBadge.textContent = `${res.chat_history.length} saved`;
        }

    } catch (error) {
        console.error('Chat error:', error);
        if (typingIndicator) {
            typingIndicator.classList.add('hidden');
        }
        showToast('error', 'Failed to get answer', error.message);
        messagesBox.insertAdjacentHTML('beforeend', `
            <div class="chat-error-notice">
                <span>⚠️ ${escapeHtml(error.message || 'Error communicating with AI assistant.')}</span>
            </div>
        `);
        scrollChatToBottom();
    } finally {
        input.disabled = false;
        if (sendBtn) sendBtn.disabled = false;
        input.focus();
    }
}


async function clearChatConfirm(videoId) {
    if (!confirm('Are you sure you want to clear the chat history for these notes?')) {
        return;
    }

    try {
        await api.clearChatHistory(videoId);
        showToast('success', 'Chat history cleared');

        if (currentVideoData) {
            currentVideoData.chat_history = [];
        }

        const messagesBox = document.getElementById('chat-messages-box');
        if (messagesBox) {
            messagesBox.innerHTML = renderChatMessagesList([]);
        }

        const clearBtn = document.getElementById('btn-clear-chat');
        if (clearBtn) clearBtn.style.display = 'none';

        const countBadge = document.getElementById('chat-msg-count');
        if (countBadge) countBadge.textContent = '0 saved';

    } catch (error) {
        showToast('error', 'Failed to clear chat', error.message);
    }
}


function copyChatResponse(btn, text) {
    navigator.clipboard.writeText(text).then(() => {
        const originalHtml = btn.innerHTML;
        btn.innerHTML = `
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
            <span>Copied!</span>
        `;
        btn.classList.add('copied');
        setTimeout(() => {
            btn.innerHTML = originalHtml;
            btn.classList.remove('copied');
        }, 2000);
    }).catch(err => {
        console.error('Copy failed:', err);
    });
}

