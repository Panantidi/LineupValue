// Favorites functionality for LineupValue
// Uses server-side storage for each user

function getPlayerDataFromRow(row) {
    const cells = row.querySelectorAll('td');
    const nameCell = row.querySelector('.player-name');
    
    // Get national from flag image alt attribute
    const flagImg = cells[1]?.querySelector('img');
    const national = flagImg?.getAttribute('alt') || flagImg?.alt || '';
    
    // Get club from team name. The h1 lives inside .main-table; the .team-title
    // class is a CSS hook (style for h1) not a wrapper element, so query both.
    const club = document.querySelector('.team-title h1')?.textContent?.trim()
        || document.querySelector('.main-table h1')?.textContent?.trim()
        || '';
    
    // Get TEAM_ID from global variable
    const team_id = window.TEAM_ID || '';
    
    // Clean name - remove emoji
    let name = nameCell?.textContent?.trim() || '';
    name = name.replace(/[⚽️👟🦾🌀⭐️🔝]/g, '').trim();
    
    // Cell indices (after fixing for Last 3 being 3 separate <td>s):
    // 0 = number, 1 = flag, 2 = name, 3 = status, 4 = age, 5 = mv, 6 = pos, 7 = squad_role, 8 = impact
    // 9 = squad checkbox, 10 = possible XI checkbox, 11 = starting XI checkbox
    // 12 = Last 3 match 1, 13 = Last 3 match 2, 14 = Last 3 match 3
    // 15 = Apps, 16 = Min, 17 = G, 18 = A, 19 = YC, 20 = RC
    
    return {
        player_id: (row.dataset.playerNumber || '') + '_' + (row.dataset.playerName || ''),
        team_id: team_id,
        number: cells[0]?.textContent?.trim() || '?',
        name: name,
        club: club,
        national: national,
        age: cells[4]?.textContent?.trim() || '',
        mv: cells[5]?.textContent?.trim() || '',
        position: cells[6]?.textContent?.trim() || '',
        squad_role: cells[7]?.textContent?.trim() || '',
        impact: cells[8]?.textContent?.trim() || '',
        apps: cells[15]?.textContent?.trim() || '',
        minutes: cells[16]?.textContent?.trim() || '',
        goals: cells[17]?.textContent?.trim() || '',
        assists: cells[18]?.textContent?.trim() || '',
        yellows: cells[19]?.textContent?.trim() || '',
        reds: cells[20]?.textContent?.trim() || ''
    };
}

// Cache favorites in memory
let _favoritesCache = null;
let _favoritesSet = new Set();

async function loadFavoritesFromServer() {
    try {
        const res = await fetch('/api/favorites');
        const data = await res.json();
        const favorites = data.favorites || [];
        _favoritesSet = new Set(favorites.map(f => f.player_id));
        return favorites;
    } catch (e) {
        console.error('Failed to load favorites:', e);
        return [];
    }
}

async function toggleFavorite(el) {
    // Check if this is a World Championship team - disable favorites for WC
    const isWC = el.getAttribute('data-is-wc');
    console.log('toggleFavorite: data-is-wc =', isWC, typeof isWC);
    
    if (isWC === 'wc') {
        console.log('BLOCKED: World Championship team');
        showToast('Favorites not available for national teams', 'error');
        return;
    }
    
    const row = el.closest('tr');
    if (!row) {
        console.error('toggleFavorite: row not found');
        return;
    }
    
    const playerData = getPlayerDataFromRow(row);
    const playerId = playerData.player_id;
    const playerName = playerData.name;
    
    console.log('toggleFavorite: player', playerName, playerId);
    
    const isFavorite = _favoritesSet.has(playerId);
    
    try {
        if (isFavorite) {
            // Remove from favorites
            await fetch('/api/favorites/' + encodeURIComponent(playerId), { method: 'DELETE' });
            _favoritesSet.delete(playerId);
            el.classList.remove('favorite');
            showToast(playerName + ' removed from favorites', 'error');
        } else {
            // Add to favorites
            await fetch('/api/favorites', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    player_id: playerId,
                    player_data: playerData
                })
            });
            _favoritesSet.add(playerId);
            el.classList.add('favorite');
            showToast(playerName + ' added to favorites', 'success');
        }
    } catch (e) {
        console.error('Failed to update favorite:', e);
        showToast('Failed to update favorites', 'error');
    }
}

// Inject toast styles into the document head (favorites.css is not loaded
// on every page, so we add the rules inline to guarantee the toast hides).
(function injectToastStyles() {
    if (document.getElementById('favorites-toast-style')) return;
    const style = document.createElement('style');
    style.id = 'favorites-toast-style';
    style.textContent = [
        '#favorites-toast {',
        '  position: fixed;',
        '  bottom: 24px;',
        '  left: 24px;',
        '  background: #333;',
        '  color: white;',
        '  padding: 16px 24px;',
        '  border-radius: 8px;',
        '  font-size: 14px;',
        '  opacity: 0;',
        '  visibility: hidden;',
        '  transform: translateY(20px);',
        '  transition: opacity 0.3s, transform 0.3s, visibility 0.3s;',
        '  z-index: 10000;',
        '  pointer-events: none;',
        '}',
        '#favorites-toast.show {',
        '  opacity: 1;',
        '  visibility: visible;',
        '  transform: translateY(0);',
        '}',
        '#favorites-toast.success { background: #28a745; }',
        '#favorites-toast.error { background: #dc3545; }',
    ].join('\n');
    document.head.appendChild(style);
})();

// Track the active auto-hide timer so a new toast cancels the previous one.
let _toastHideTimer = null;

function showToast(message, type) {
    let toast = document.getElementById('favorites-toast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'favorites-toast';
        document.body.appendChild(toast);
    }
    // Cancel any pending hide from a previous toast so the new one stays visible
    // for the full 3 seconds, regardless of how rapidly the user clicks.
    if (_toastHideTimer !== null) {
        clearTimeout(_toastHideTimer);
        _toastHideTimer = null;
    }
    toast.textContent = message;
    toast.className = 'show ' + type;
    // Auto-hide after 3 seconds
    _toastHideTimer = setTimeout(function() {
        toast.classList.remove('show');
        _toastHideTimer = null;
    }, 3000);
}

async function initFavorites() {
    await loadFavoritesFromServer();
    document.querySelectorAll('.player-number-circle').forEach(el => {
        const row = el.closest('tr');
        if (!row) return;
        const playerId = (row.dataset.playerNumber || '') + '_' + (row.dataset.playerName || '');
        if (_favoritesSet.has(playerId)) {
            el.classList.add('favorite');
        }
    });
}

// Initialize favorites on page load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initFavorites);
} else {
    initFavorites();
}