/**
 * API Client — Backend communication layer
 */
const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    ? 'http://localhost:8000/api'
    : 'https://lecturenotes-api.onrender.com/api';

const api = {
    /**
     * Make a fetch request with error handling.
     */
    async request(endpoint, options = {}) {
        const url = `${API_BASE}${endpoint}`;
        const config = {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers,
            },
            ...options,
        };

        try {
            const response = await fetch(url, config);

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                const message = errorData.detail || `Request failed with status ${response.status}`;
                throw new Error(message);
            }

            // Handle different content types
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('text/markdown')) {
                return await response.text();
            }
            return await response.json();
        } catch (error) {
            if (error.name === 'TypeError' && error.message.includes('fetch')) {
                throw new Error('Cannot connect to the server. Please make sure the backend is running.');
            }
            throw error;
        }
    },

    /**
     * Submit a new YouTube video URL for processing.
     */
    async createVideo(url) {
        return this.request('/videos', {
            method: 'POST',
            body: JSON.stringify({ url }),
        });
    },

    /**
     * List all videos with optional search and tag filter.
     */
    async listVideos(query = null, tag = null) {
        const params = new URLSearchParams();
        if (query) params.set('q', query);
        if (tag) params.set('tag', tag);
        const qs = params.toString();
        return this.request(`/videos${qs ? '?' + qs : ''}`);
    },

    /**
     * Get full video details by MongoDB ID.
     */
    async getVideo(id) {
        return this.request(`/videos/${id}`);
    },

    /**
     * Delete a video by MongoDB ID.
     */
    async deleteVideo(id) {
        return this.request(`/videos/${id}`, { method: 'DELETE' });
    },

    /**
     * Export video notes as Markdown.
     */
    async exportMarkdown(id) {
        return this.request(`/videos/${id}/export/markdown`);
    },

    /**
     * Get all available tags.
     */
    async getTags() {
        return this.request('/tags');
    },

    /**
     * Send a chat question to the AI tutor about the video notes.
     */
    async sendChatMessage(videoId, message) {
        return this.request(`/videos/${videoId}/chat`, {
            method: 'POST',
            body: JSON.stringify({ message }),
        });
    },

    /**
     * Get saved chat history for a video.
     */
    async getChatHistory(videoId) {
        return this.request(`/videos/${videoId}/chat`);
    },

    /**
     * Clear all chat history for a video.
     */
    async clearChatHistory(videoId) {
        return this.request(`/videos/${videoId}/chat`, {
            method: 'DELETE',
        });
    },

    /**
     * Health check.
     */
    async healthCheck() {
        return this.request('/health');
    },
};

