/* Country favorites — localStorage-backed. Survives page reloads.
 *
 * Public API (window.countryFavorites):
 *   sortCountries(list) -> sorted array
 *       favorites first (in user-added order), then non-favorites alphabetical
 *   toggleFavorite(country) -> bool
 *   isFavorite(country) -> bool
 *   buildStarButton(country) -> <a> element
 *
 * Dispatches 'countryFavoritesChanged' CustomEvent on document.
 */
(function () {
    const KEY = 'lineup_country_favorites';

    function load() {
        try {
            const raw = localStorage.getItem(KEY);
            if (!raw) return [];
            const parsed = JSON.parse(raw);
            return Array.isArray(parsed) ? parsed.filter(c => typeof c === 'string' && c) : [];
        } catch (e) {
            console.warn('countryFavorites: read failed', e);
            return [];
        }
    }
    function save(list) {
        try {
            localStorage.setItem(KEY, JSON.stringify(list));
        } catch (e) {
            console.warn('countryFavorites: write failed', e);
        }
    }
    function isFavorite(country) {
        return load().indexOf(country) !== -1;
    }
    function addFavorite(country) {
        const list = load();
        if (list.indexOf(country) === -1) {
            list.unshift(country);
            save(list);
            notify();
        }
    }
    function removeFavorite(country) {
        const list = load();
        const i = list.indexOf(country);
        if (i !== -1) {
            list.splice(i, 1);
            save(list);
            notify();
        }
    }
    function toggleFavorite(country) {
        if (isFavorite(country)) { removeFavorite(country); return false; }
        addFavorite(country);
        return true;
    }
    function sortCountries(countries) {
        const favs = load();
        const favSet = new Set(favs);
        const favOrdered = favs.filter(c => countries.indexOf(c) !== -1);
        const rest = countries.filter(c => !favSet.has(c)).slice()
            .sort((a, b) => a.localeCompare(b));
        return favOrdered.concat(rest);
    }
    function buildStarButton(country) {
        const star = document.createElement('a');
        star.className = 'country-fav-star';
        star.href = 'javascript:void(0)';
        star.setAttribute('role', 'button');
        star.setAttribute('data-country', country);
        function refresh() {
            const fav = isFavorite(country);
            star.textContent = fav ? '★' : '☆';
            star.classList.toggle('is-fav', fav);
            star.setAttribute('aria-label', fav
                ? 'Remove ' + country + ' from favorites'
                : 'Add ' + country + ' to favorites');
            star.setAttribute('title', fav
                ? 'Remove ' + country + ' from favorites'
                : 'Add ' + country + ' to favorites');
        }
        refresh();
        star.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            toggleFavorite(country);
        });
        return star;
    }
    function notify() {
        document.dispatchEvent(new CustomEvent('countryFavoritesChanged'));
    }
    document.addEventListener('countryFavoritesChanged', function () {
        document.querySelectorAll('.country-fav-star').forEach(function (el) {
            const c = el.getAttribute('data-country');
            if (!c) return;
            const fav = isFavorite(c);
            el.textContent = fav ? '★' : '☆';
            el.classList.toggle('is-fav', fav);
        });
    });

    window.countryFavorites = {
        sortCountries: sortCountries,
        toggleFavorite: toggleFavorite,
        isFavorite: isFavorite,
        buildStarButton: buildStarButton,
        addFavorite: addFavorite,
        removeFavorite: removeFavorite,
    };
})();