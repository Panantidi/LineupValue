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
    
    // Cell indices (after fixing for Last 3 being 3 separate <td>s):
    // 0 = number, 1 = flag, 2 = name, 3 = status, 4 = age, 5 = mv, 6 = pos, 7 = squad_role, 8 = impact
    // 9 = squad checkbox, 10 = possible XI checkbox, 11 = starting XI checkbox
    // 12 = Last 3 match 1, 13 = Last 3 match 2, 14 = Last 3 match 3
    // 15 = Apps, 16 = Min, 17 = G, 18 = A, 19 = YC, 20 = RC
    
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
        apps: cells[15]?.textContent?.trim() || '',
        minutes: cells[16]?.textContent?.trim() || '',
        goals: cells[17]?.textContent?.trim() || '',
        assists: cells[18]?.textContent?.trim() || '',
        yellows: cells[19]?.textContent?.trim() || '',
        reds: cells[20]?.textContent?.trim() || ''
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