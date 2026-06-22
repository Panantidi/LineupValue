// Favorites functionality for LineupValue
const FAV_STORAGE_KEY = 'favorites_players';

function getFavorites() {
    try {
        const data = localStorage.getItem(FAV_STORAGE_KEY);
        return data ? JSON.parse(data) : [];
    } catch (e) {
        return [];
    }
}

function saveFavorites(favs) {
    try {
        localStorage.setItem(FAV_STORAGE_KEY, JSON.stringify(favs));
    } catch (e) {}
}

function findFavoriteIndex(playerId) {
    const favs = getFavorites();
    return favs.findIndex(f => f.id === playerId);
}

function getPlayerDataFromRow(row) {
    const cells = row.querySelectorAll('td');
    const nameCell = row.querySelector('.player-name');
    
    // Get national from flag image alt attribute
    const flagImg = cells[1]?.querySelector('img');
    const national = flagImg?.getAttribute('alt') || flagImg?.alt || '';
    
    // Get club from team title
    const club = document.querySelector('.team-title h1')?.textContent?.trim() || '';
    
    // Clean name - remove emoji
    let name = nameCell?.textContent?.trim() || '';
    name = name.replace(/[⚽️👟🦾🌀⭐️🔝]/g, '').trim();
    
    return {
        id: (row.dataset.playerNumber || '') + '_' + (row.dataset.playerName || ''),
        number: cells[0]?.textContent?.trim() || '?',
        name: name,
        club: club,
        national: national,
        age: cells[4]?.textContent?.trim() || '',
        mv: cells[5]?.textContent?.trim() || '',
        position: cells[6]?.textContent?.trim() || '',
        squad_role: cells[7]?.textContent?.trim() || '',
        impact: cells[8]?.textContent?.trim() || '',
        // Skip cells 9, 10, 11 (checkboxes) and 12 (Last 3 circles)
        apps: cells[13]?.textContent?.trim() || '',
        minutes: cells[14]?.textContent?.trim() || '',
        goals: cells[15]?.textContent?.trim() || '',
        assists: cells[16]?.textContent?.trim() || '',
        yellows: cells[17]?.textContent?.trim() || '',
        reds: cells[18]?.textContent?.trim() || ''
    };
}

function toggleFavorite(el) {
    const row = el.closest('tr');
    if (!row) return;
    
    const playerData = getPlayerDataFromRow(row);
    const playerId = playerData.id;
    const playerName = playerData.name;
    
    let favs = getFavorites();
    const idx = findFavoriteIndex(playerId);
    
    if (idx >= 0) {
        favs.splice(idx, 1);
        el.classList.remove('favorite');
        showToast(playerName + ' removed from favorites', 'error');
    } else {
        favs.push(playerData);
        el.classList.add('favorite');
        showToast(playerName + ' added to favorites', 'success');
    }
    
    saveFavorites(favs);
}

function showToast(message, type) {
    let toast = document.getElementById('favorites-toast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'favorites-toast';
        document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.className = 'show ' + type;
    setTimeout(() => { toast.classList.remove('show'); }, 3000);
}

function initFavorites() {
    const favs = getFavorites();
    document.querySelectorAll('.player-number-circle').forEach(el => {
        const row = el.closest('tr');
        if (!row) return;
        const playerId = (row.dataset.playerNumber || '') + '_' + (row.dataset.playerName || '');
        if (findFavoriteIndex(playerId) >= 0) {
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