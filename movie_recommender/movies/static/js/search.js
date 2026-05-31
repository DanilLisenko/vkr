// movies/static/js/search.js
document.addEventListener("DOMContentLoaded", function() {
    const searchInput = document.getElementById('search-input');
    const searchForm = document.getElementById('search-form');
    const genreFilter = document.getElementById('genre-filter');
    const sortFilter = document.getElementById('sort-filter');

    if (!searchInput || !searchForm) {
        console.warn('Основные элементы поиска (search-input или search-form) не найдены');
        return;
    }

    const resultsContainer = document.createElement('div');
    resultsContainer.className = 'search-results';
    searchForm.appendChild(resultsContainer);

    let timeoutId;
    let isFetching = false;
    const searchCache = new Map();

    function displayResults(data) {
        resultsContainer.innerHTML = '';
        if (data.error) {
            resultsContainer.innerHTML = `<div class="search-error">Ошибка: ${data.error}</div>`;
            resultsContainer.classList.add('visible');
            return;
        }

        if (data.movies?.length || data.actors?.length) {
            if (data.movies?.length) {
                data.movies.forEach(movie => {
                    const item = document.createElement('div');
                    item.className = 'search-item';
                    item.innerHTML = `
                        <img src="${movie.poster_url}" alt="${movie.title}" onerror="this.src='/static/images/placeholder.png';">
                        <a href="/movies/${movie.id}/">${movie.title}</a>
                    `;
                    resultsContainer.appendChild(item);
                });
            }
            if (data.actors?.length) {
                data.actors.forEach(actor => {
                    const item = document.createElement('div');
                    item.className = 'search-item';
                    item.innerHTML = `
                        <img src="${actor.photo_url}" alt="${actor.name}" onerror="this.src='/static/images/placeholder.png';">
                        <a href="/movies/actor/${actor.id}/">${actor.name}</a>
                    `;
                    console.log(`Generated actor link: /movies/actor/${actor.id}/`);
                    resultsContainer.appendChild(item);
                });
            }
        } else {
            resultsContainer.innerHTML = '<div class="search-empty">Ничего не найдено</div>';
        }
        resultsContainer.classList.add('visible');
    }

    function performLocalSearch(query) {
        const cached = searchCache.get('popular');
        if (cached && query.length <= 2) {
            const filtered = {
                movies: cached.movies.filter(m => m.title.toLowerCase().startsWith(query.toLowerCase())),
                actors: cached.actors.filter(a => a.name.toLowerCase().startsWith(query.toLowerCase())),
            };
            if (filtered.movies.length || filtered.actors.length) {
                displayResults(filtered);
                return true;
            }
        }
        return false;
    }

    function performSearch() {
        if (isFetching) return;
        clearTimeout(timeoutId);
        const query = searchInput.value.trim();
        const genre = genreFilter ? genreFilter.value : '';
        const sort = sortFilter ? sortFilter.value : '';
        const cacheKey = `${query}:${genre}:${sort}`;

        if (searchCache.has(cacheKey)) {
            displayResults(searchCache.get(cacheKey));
            return;
        }

        if (performLocalSearch(query)) return;

        timeoutId = setTimeout(() => {
            if (query.length > 0) {
                isFetching = true;
                resultsContainer.innerHTML = '<div>Загрузка...</div>';
                const url = `/movies/search/?q=${encodeURIComponent(query)}&genre=${encodeURIComponent(genre)}&sort=${encodeURIComponent(sort)}`;
                console.log(`Fetching search: ${url}`);
                fetch(url)
                    .then(response => {
                        if (!response.ok) {
                            throw new Error(`HTTP error! status: ${response.status}`);
                        }
                        return response.json();
                    })
                    .then(data => {
                        searchCache.set(cacheKey, data);
                        displayResults(data);
                    })
                    .catch(error => {
                        console.error('Ошибка поиска:', error);
                        displayResults({ error: 'Не удалось выполнить поиск. Попробуйте позже.' });
                    })
                    .finally(() => {
                        isFetching = false;
                    });
            } else {
                resultsContainer.innerHTML = '';
                resultsContainer.classList.remove('visible');
            }
        }, 100);
    }

    searchInput.addEventListener('input', performSearch);
    if (genreFilter) {
        genreFilter.addEventListener('change', performSearch);
    }
    if (sortFilter) {
        sortFilter.addEventListener('change', performSearch);
    }

    document.addEventListener('click', function(event) {
        if (!searchForm.contains(event.target)) {
            resultsContainer.classList.remove('visible');
        }
    });

    fetch('/movies/search/?q=')
        .then(response => response.json())
        .then(data => searchCache.set('popular', data))
        .catch(error => console.error('Ошибка загрузки популярных результатов:', error));
});