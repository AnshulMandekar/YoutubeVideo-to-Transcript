/**
 * Dashboard View — Grid of videos, search, tag filtering
 */

let dashboardState = {
    videos: [],
    tags: [],
    searchQuery: '',
    activeTag: null,
    loading: false,
};

let searchDebounceTimer = null;


async function renderDashboard() {
    const main = document.getElementById('main-content');

    main.innerHTML = `
        <div class="fade-in">
            <div class="dashboard-header">
                <h1 class="dashboard-title">Your Lecture Library</h1>
                <p class="dashboard-subtitle">AI-powered notes from YouTube lectures</p>
            </div>

            <div class="dashboard-controls">
                <div class="search-input-wrapper input-group">
                    <div class="input-icon">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <circle cx="11" cy="11" r="8"></circle>
                            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
                        </svg>
                    </div>
                    <input type="text" id="search-input" class="input-field" placeholder="Search videos, topics, or keywords..."
                           value="${escapeHtml(dashboardState.searchQuery)}"
                           oninput="onSearchInput(this.value)">
                </div>
                <div class="tag-filters" id="tag-filters">
                    <!-- Tags injected here -->
                </div>
            </div>

            <div class="video-grid" id="video-grid">
                ${renderSkeletonCards(6)}
            </div>
        </div>
    `;

    await loadDashboardData();
}


async function loadDashboardData() {
    dashboardState.loading = true;

    try {
        // Fetch videos and tags in parallel
        const [videosRes, tagsRes] = await Promise.all([
            api.listVideos(dashboardState.searchQuery || null, dashboardState.activeTag || null),
            api.getTags(),
        ]);

        dashboardState.videos = videosRes.videos || [];
        dashboardState.tags = tagsRes.tags || [];

        renderVideoGrid();
        renderTagFilters();
    } catch (error) {
        console.error('Failed to load dashboard:', error);
        showToast('error', 'Failed to load videos', error.message);

        const grid = document.getElementById('video-grid');
        if (grid) {
            grid.innerHTML = renderEmptyState();
        }
    } finally {
        dashboardState.loading = false;
    }
}


function renderVideoGrid() {
    const grid = document.getElementById('video-grid');
    if (!grid) return;

    if (dashboardState.videos.length === 0) {
        grid.innerHTML = renderEmptyState();
        return;
    }

    grid.innerHTML = dashboardState.videos.map(v => renderVideoCard(v)).join('');
}


function renderTagFilters() {
    const container = document.getElementById('tag-filters');
    if (!container || dashboardState.tags.length === 0) return;

    let html = `<span class="tag ${!dashboardState.activeTag ? 'active' : ''}"
                      data-tag="" onclick="onTagClick(null)">All</span>`;

    for (const tag of dashboardState.tags) {
        const isActive = dashboardState.activeTag === tag;
        html += `<span class="tag ${isActive ? 'active' : ''}"
                       data-tag="${escapeHtml(tag)}" onclick="onTagClick('${escapeHtml(tag)}')">${escapeHtml(tag)}</span>`;
    }

    container.innerHTML = html;
}


function renderEmptyState() {
    const isFiltered = dashboardState.searchQuery || dashboardState.activeTag;

    if (isFiltered) {
        return `
            <div class="empty-state" style="grid-column: 1 / -1;">
                <span class="empty-state-icon">🔍</span>
                <h2 class="empty-state-title">No results found</h2>
                <p class="empty-state-text">Try a different search term or clear your filters.</p>
                <button class="btn btn-secondary" onclick="clearFilters()">Clear Filters</button>
            </div>
        `;
    }

    return `
        <div class="empty-state" style="grid-column: 1 / -1;">
            <span class="empty-state-icon">📚</span>
            <h2 class="empty-state-title">No lectures yet</h2>
            <p class="empty-state-text">
                Add your first YouTube lecture and we'll generate beautifully organized notes
                with AI-powered analysis and visual concept maps.
            </p>
            <button class="btn btn-primary btn-lg" onclick="openAddModal()">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="12" y1="5" x2="12" y2="19"></line>
                    <line x1="5" y1="12" x2="19" y2="12"></line>
                </svg>
                <span>Add Your First Video</span>
            </button>
        </div>
    `;
}


function onSearchInput(value) {
    dashboardState.searchQuery = value;

    // Debounce search
    clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(() => {
        loadDashboardData();
    }, 400);
}


function onTagClick(tag) {
    dashboardState.activeTag = tag;
    loadDashboardData();
}


function clearFilters() {
    dashboardState.searchQuery = '';
    dashboardState.activeTag = null;

    const searchInput = document.getElementById('search-input');
    if (searchInput) searchInput.value = '';

    loadDashboardData();
}
