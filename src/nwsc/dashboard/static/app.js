// Dashboard auto-refresh: polls /status every 2 seconds

const POLL_INTERVAL = 2000;

async function fetchStatus() {
    try {
        const resp = await fetch("/status");
        if (!resp.ok) return null;
        return await resp.json();
    } catch {
        return null;
    }
}

function updateGameState(data) {
    const gameId = document.getElementById("game-id");
    const period = document.getElementById("period");
    const jam = document.getElementById("jam");

    if (gameId) gameId.textContent = data.game_id || "--";
    if (period) period.textContent = data.period ?? "--";
    if (jam) jam.textContent = data.jam ?? "--";
}

function updateIntegrations(integrations) {
    const container = document.getElementById("integration-list");
    if (!container) return;

    if (!integrations || Object.keys(integrations).length === 0) {
        container.innerHTML = '<p class="loading">No integrations registered</p>';
        return;
    }

    container.innerHTML = Object.entries(integrations)
        .map(([name, status]) => `
            <div class="integration-item">
                <span class="status-dot ${status.healthy ? 'healthy' : 'unhealthy'}"></span>
                <span class="integration-name">${name}</span>
                <span class="integration-detail">${status.detail || ''}</span>
                ${status.latency_ms != null ? `<span class="integration-detail">${Math.round(status.latency_ms)}ms</span>` : ''}
            </div>
        `).join("");
}

function updateClips(clips) {
    const tbody = document.getElementById("clips-body");
    if (!tbody) return;

    if (!clips || clips.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="loading">No clips yet</td></tr>';
        return;
    }

    tbody.innerHTML = clips.map(clip => `
        <tr>
            <td>${clip.period}</td>
            <td>${clip.jam}</td>
            <td class="status-${clip.status}">${clip.status}</td>
            <td title="${clip.path}">${clip.path.split(/[/\\]/).pop()}</td>
            <td>${clip.created_at ? new Date(clip.created_at).toLocaleTimeString() : ''}</td>
        </tr>
    `).join("");
}

async function poll() {
    const data = await fetchStatus();
    if (data) {
        updateGameState(data);
        updateIntegrations(data.integrations);
        updateClips(data.recent_clips);
    }
}

// Start polling
poll();
setInterval(poll, POLL_INTERVAL);
