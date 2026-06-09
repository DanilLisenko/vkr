import os
from urllib.parse import quote as _url_quote
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse


def _proxy_url(url):
    """Возвращает URL без изменений — прокси обрабатывается JS onerror."""
    return url or ''
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from .models import Movie, Watchlist, Review, Actor, Genre , MovieCredit, SearchHistory, MovieSimilarity
from .forms import ReviewForm
from django.core.paginator import Paginator
from django.urls import reverse
from django.db.models import Q, Count
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank, TrigramSimilarity
import re
from .models import Movie, Watchlist, Review, Actor, Genre, MovieCredit, SearchHistory, Person
import requests
from django.conf import settings
from datetime import datetime


def search(request):
    query = request.GET.get('q', '').strip()
    genre = request.GET.get('genre', '')
    sort = request.GET.get('sort', 'rating')
    is_live = request.GET.get('live', '0') == '1'

    if not query or len(query) < 2:
        return JsonResponse({'movies': [], 'actors': []})

    # --- Фильмы: быстрый icontains + trigram fallback ---
    base_qs = Movie.objects.filter(poster_url__isnull=False).exclude(poster_url='')
    if genre:
        base_qs = base_qs.filter(genres__name=genre)

    # Точное совпадение подстроки (быстро, по индексу)
    exact_movies = list(base_qs.filter(title__icontains=query).order_by('-rating')[:10])
    exact_ids = {m.id for m in exact_movies}

    # Если меньше 5 точных — добавляем trigram (нечёткий, обрабатывает опечатки)
    fuzzy_movies = []
    if len(exact_movies) < 5:
        fuzzy_movies = list(
            base_qs.exclude(id__in=exact_ids)
            .annotate(sim=TrigramSimilarity('title', query))
            .filter(sim__gt=0.2)
            .order_by('-sim', '-rating')[:10 - len(exact_movies)]
        )

    movies = exact_movies + fuzzy_movies

    # --- Актёры ---
    exact_actors = list(Actor.objects.filter(name__icontains=query)[:6])
    actor_ids = {a.id for a in exact_actors}
    fuzzy_actors = []
    if len(exact_actors) < 3:
        fuzzy_actors = list(
            Actor.objects.exclude(id__in=actor_ids)
            .annotate(sim=TrigramSimilarity('name', query))
            .filter(sim__gt=0.25)
            .order_by('-sim')[:6 - len(exact_actors)]
        )
    actors = exact_actors + fuzzy_actors

    if not is_live and request.user.is_authenticated and len(query) >= 3:
        SearchHistory.objects.create(user=request.user, query=query)

    return JsonResponse({
        'movies': [
            {'id': m.id, 'title': m.title, 'poster_url': _proxy_url(m.poster_url),
             'rating': round(m.rating or 0, 1)}
            for m in movies
        ],
        'actors': [
            {'id': a.id, 'name': a.name, 'photo_url': _proxy_url(a.photo_url)}
            for a in actors
        ],
    })


@login_required
def recommend_movie(request):
    """
    Формирование персональных рекомендаций на основе комплексного анализа профиля пользователя:
    учитываются добавления в списки (Watchlist), выставленные оценки (Review) 
    и фильмы, выбранные при регистрации (FavoriteMovie).
    """
    from users.models import FavoriteMovie  # Импортируем модель избранного с регистрации

    # 1. Собираем все фильмы, с которыми пользователь уже взаимодействовал
    watched_ids = set(Watchlist.objects.filter(user=request.user).values_list('movie_id', flat=True))
    reviewed_ids = set(Review.objects.filter(user=request.user).values_list('movie_id', flat=True))
    favorite_ids = set(FavoriteMovie.objects.filter(user=request.user).values_list('movie_id', flat=True))
    
    # Объединяем их, чтобы исключить из выдачи (не рекомендуем то, что пользователь уже видел/лайкнул)
    all_interacted_ids = watched_ids.union(reviewed_ids).union(favorite_ids)

    # 2. Извлекаем отзывы пользователя (явная обратная связь)
    user_reviews = Review.objects.filter(user=request.user)

    # Собираем «интересы» пользователя с весами
    movie_weights = {}

    # Добавляем фильмы, лайкнутые при регистрации (выставляем им высокий приоритет, например, 1.5)
    for f_id in favorite_ids:
        movie_weights[f_id] = 1.5

    # Добавляем фильмы из Watchlist (базовый положительный вес 1.0)
    for m_id in watched_ids:
        if m_id not in movie_weights:
            movie_weights[m_id] = 1.0

    # Корректируем или перезаписываем веса на основе оценок из отзывов
    for review in user_reviews:
        rating_weight = review.rating - 5.5  # Если оценка 10, вес +4.5. Если оценка 1, вес -4.5
        movie_weights[review.movie_id] = rating_weight

    # Если профиль абсолютно пуст (холодный старт без истории и без регистрации)
    if not movie_weights:
        recommended_movies = list(Movie.objects.filter(
            poster_url__isnull=False,
            rating__gte=7.5
        ).exclude(poster_url='').order_by('-rating')[:10])

        context = {'movies': recommended_movies}
        return render(request, 'movies/recommend.html', context)

    # 3. Вычисляем итоговые кумулятивные баллы для кандидатов на рекомендацию
    similarity_records = MovieSimilarity.objects.filter(
        first_movie_id__in=movie_weights.keys()
    ).exclude(
        second_movie_id__in=all_interacted_ids  # Исключаем уже просмотренное и лайкнутое
    ).select_related('second_movie')

    # Расчет взвешенной суммы схожести для каждого потенциального фильма
    candidate_scores = {}
    for record in similarity_records:
        source_movie_id = record.first_movie_id
        candidate_id = record.second_movie_id

        # Информационный вес исходного фильма (из отзывов/отложенного/избранного)
        user_weight = movie_weights.get(source_movie_id, 1.0)

        # Вклад текущего сопоставления = Схожесть объектов * Вес отношения пользователя к фильму
        contribution = record.score * user_weight

        if candidate_id not in candidate_scores:
            candidate_scores[candidate_id] = {
                'movie': record.second_movie,
                'total_score': 0.0
            }
        candidate_scores[candidate_id]['total_score'] += contribution

    # 4. Сортируем кандидатов по убыванию набранных баллов
    sorted_candidates = sorted(
        candidate_scores.values(),
        key=lambda x: x['total_score'],
        reverse=True
    )

    # Отбираем топ-10 лучших рекомендаций
    recommended_movies = [item['movie'] for item in sorted_candidates if item['total_score'] > 0][:10]

    # Если рекомендаций по матрице схожести не хватило, добиваем популярными
    if len(recommended_movies) < 10:
        additional_count = 10 - len(recommended_movies)
        exclude_ids = all_interacted_ids.union({m.id for m in recommended_movies})
        backup_movies = Movie.objects.filter(
            poster_url__isnull=False,
            rating__gte=7.0
        ).exclude(id__in=exclude_ids).order_by('-rating')[:additional_count]
        recommended_movies.extend(list(backup_movies))

    # Определяем любимые жанры пользователя для отображения (включая регистрационные)
    positive_movie_ids = [
        m_id for m_id, w in movie_weights.items() if w > 0
    ]
    from collections import Counter
    genre_counter = Counter()
    if positive_movie_ids:
        genre_rows = Movie.objects.filter(id__in=positive_movie_ids).values_list('genres__name', flat=True)
        for genre_name in genre_rows:
            if genre_name:
                genre_counter[genre_name] += 1
    top_genres = [name for name, _ in genre_counter.most_common(5)]

    context = {
        'movies': recommended_movies,
        'top_genres': top_genres,
    }
    return render(request, 'movies/recommend.html', context)


def _fetch_trailers(tmdb_id, api_key):
    """
    Возвращает список YouTube-трейлеров.
    Приоритет: русский → английский → любой оригинальный.
    """
    def get_videos(language=None):
        params = f'?api_key={api_key}'
        if language:
            params += f'&language={language}'
        try:
            r = requests.get(
                f'https://api.themoviedb.org/3/movie/{tmdb_id}/videos{params}',
                timeout=5
            )
            if r.status_code == 200:
                return r.json().get('results', [])
        except Exception:
            pass
        return []

    def only_trailers(videos):
        return [v for v in videos if v.get('site') == 'YouTube'
                and v.get('type') in ('Trailer', 'Teaser')]

    ru = only_trailers(get_videos('ru-RU'))
    if ru:
        return ru
    en = only_trailers(get_videos('en-US'))
    if en:
        return en
    return only_trailers(get_videos())


def movie_detail(request, movie_id):
    from django.core.cache import cache as _cache

    movie = get_object_or_404(Movie, id=movie_id)

    # Только реальные отзывы (не ml_user_*)
    reviews = movie.reviews.exclude(
        user__username__startswith='ml_user_'
    ).select_related('user').order_by('-created_at')

    # Похожие фильмы — кэшируем на 1 час
    sim_key = f'similar_{movie_id}'
    similar_movies = _cache.get(sim_key)
    if similar_movies is None:
        similar_movies = get_similar_movies(movie, limit=10)
        _cache.set(sim_key, similar_movies, 3600)

    # Трейлеры — кэшируем на 24 часа (они почти не меняются)
    trailer_key = f'trailers_{movie.tmdb_id}'
    trailers = _cache.get(trailer_key)
    if trailers is None:
        trailers = []
        if movie.tmdb_id and settings.TMDB_API_KEY:
            trailers = _fetch_trailers(movie.tmdb_id, settings.TMDB_API_KEY)
        _cache.set(trailer_key, trailers, 86400)  # 24 часа

    # Актёры всегда из БД — быстрый запрос, не нужен кэш
    actors = list(movie.actors.all().order_by('id')[:20])

    # Режиссёры и съёмочная группа — кэшируем на 6 часов
    credits_key = f'credits_v2_{movie_id}'
    credits_data = _cache.get(credits_key)
    if credits_data is None:
        credits_qs = MovieCredit.objects.filter(movie=movie).select_related('person')
        directors = list(credits_qs.filter(role='Director')[:5])
        crew      = list(credits_qs.exclude(role__in=['Actor', 'Director'])[:8])
        credits_data = {'directors': directors, 'crew': crew}
        _cache.set(credits_key, credits_data, 21600)

    directors = credits_data['directors']
    crew      = credits_data['crew']

    user_review = None
    if request.user.is_authenticated:
        try:
            user_review = reviews.get(user=request.user)
        except Review.DoesNotExist:
            user_review = None

    if request.method == 'POST':
        if not request.user.is_authenticated:
            return redirect('users:login')
        if user_review:
            form = ReviewForm(request.POST, instance=user_review)
        else:
            form = ReviewForm(request.POST)
        if form.is_valid():
            review = form.save(commit=False)
            review.user = request.user
            review.movie = movie
            review.save()
            return redirect('movies:movie_detail', movie_id=movie.id)
    else:
        form = ReviewForm(instance=user_review) if user_review else ReviewForm()

    in_watchlist = False
    is_watched = False
    if request.user.is_authenticated:
        wl = Watchlist.objects.filter(user=request.user, movie=movie).first()
        if wl:
            is_watched = wl.watched
            in_watchlist = not wl.watched

    context = {
        'movie': movie,
        'actors': actors,
        'directors': directors,
        'crew': crew,
        'similar_movies': similar_movies,
        'reviews': reviews,
        'form': form,
        'user_review': user_review,
        'in_watchlist': in_watchlist,
        'is_watched': is_watched,
        'trailers': trailers,
    }
    return render(request, 'movies/movie_detail.html', context)

@login_required
def add_to_watchlist(request, movie_id):
    """
    Переключает статус «Буду смотреть»:
    - нет записи → добавить (watched=False)
    - есть, watched=False → удалить (убрать из списка)
    - есть, watched=True → перевести обратно в «отложенные» (watched=False)
    """
    movie = get_object_or_404(Movie, id=movie_id)
    try:
        item = Watchlist.objects.get(user=request.user, movie=movie)
        if item.watched:
            # Было «просмотрено» → переводим в «отложено»
            item.watched = False
            item.save()
            return JsonResponse({'in_watchlist': True, 'is_watched': False})
        else:
            # Уже в «отложенных» → убираем совсем
            item.delete()
            return JsonResponse({'in_watchlist': False, 'is_watched': False})
    except Watchlist.DoesNotExist:
        Watchlist.objects.create(user=request.user, movie=movie, watched=False)
        return JsonResponse({'in_watchlist': True, 'is_watched': False})


@login_required
def mark_as_watched(request, movie_id):
    """
    Переключает статус «Просмотрено»:
    - нет записи → создать (watched=True)
    - есть, watched=False → перевести в watched=True
    - есть, watched=True → убрать совсем (отменить отметку)
    """
    movie = get_object_or_404(Movie, id=movie_id)
    try:
        item = Watchlist.objects.get(user=request.user, movie=movie)
        if item.watched:
            # Уже «просмотрено» → убираем совсем
            item.delete()
            return JsonResponse({'in_watchlist': False, 'is_watched': False})
        else:
            # Было «отложено» → переводим в «просмотрено»
            item.watched = True
            item.save()
            return JsonResponse({'in_watchlist': False, 'is_watched': True})
    except Watchlist.DoesNotExist:
        Watchlist.objects.create(user=request.user, movie=movie, watched=True)
        return JsonResponse({'in_watchlist': False, 'is_watched': True})


def get_similar_movies(movie, limit=10):
    """
    Похожие фильмы: извлекаются из предсчитанной в БД взвешенной
    матрицы мультикритериального сходства объектов.
    """
    similar_records = MovieSimilarity.objects.filter(
        first_movie=movie
    ).order_by('-score').select_related('second_movie')[:limit]

    return [record.second_movie for record in similar_records]


_POPULAR_IDS_CACHE = None

def _get_popular_ids():
    """Кэшируем ID популярных фильмов в памяти процесса (сброс при рестарте)."""
    global _POPULAR_IDS_CACHE
    if _POPULAR_IDS_CACHE is None:
        _POPULAR_IDS_CACHE = list(
            Review.objects.filter(user__username__startswith='ml_user_')
            .values('movie_id').annotate(cnt=Count('id'))
            .filter(cnt__gte=10).values_list('movie_id', flat=True)
        )
    return _POPULAR_IDS_CACHE


def _quality_qs():
    """Популярные фильмы (кэшированные ID), рейтинг 7–9.4, есть постер."""
    pop_ids = _get_popular_ids()
    return Movie.objects.filter(
        id__in=pop_ids,
        poster_url__isnull=False,
        rating__gte=7.0,
        rating__lt=9.5,
    ).exclude(poster_url='').order_by('-rating')


def _build_collections_context():
    """Строит контекст подборок — вызывается один раз, затем берётся из кэша."""
    from datetime import date
    from django.core.cache import cache as _cache
    from movies.templatetags.movie_tags import translit_slug

    cached = _cache.get('collections_ctx')
    if cached is not None:
        return cached

    base_qs = _quality_qs()
    current_year = date.today().year

    # Предварительно загружаем related genres одним запросом
    def fetch(qs, limit):
        return list(qs[:limit])

    top_movies    = fetch(base_qs, 16)
    new_movies    = fetch(base_qs.filter(release_date__year__gte=current_year - 5, rating__gte=7.0), 12)
    classic_movies = fetch(base_qs.filter(release_date__year__lt=2000, rating__gte=7.5), 12)

    # Жанры — один запрос на все нужные жанры
    TARGET_GENRES = [
        'Action', 'Drama', 'Comedy', 'Thriller', 'Crime',
        'Adventure', 'Sci-Fi', 'Horror', 'Romance', 'Animation',
        'Боевик', 'Драма', 'Комедия', 'Триллер', 'Криминал',
        'Приключения', 'Фантастика', 'Ужасы', 'Мелодрама', 'Анимация',
    ]
    names_lower = [n.lower() for n in TARGET_GENRES]
    priority_genres = {
        g.name.lower(): g
        for g in Genre.objects.filter(name__in=TARGET_GENRES)
    }
    # Также пробуем iexact (регистр)
    for name in TARGET_GENRES:
        nl = name.lower()
        if nl not in priority_genres:
            try:
                g = Genre.objects.get(name__iexact=name)
                priority_genres[g.name.lower()] = g
            except Genre.DoesNotExist:
                pass

    genre_sections = []
    seen_ids = set()
    for name in TARGET_GENRES:
        g = priority_genres.get(name.lower())
        if not g or g.id in seen_ids:
            continue
        movies = fetch(base_qs.filter(genres=g), 10)
        if len(movies) >= 4:
            genre_sections.append({'genre': g, 'movies': movies, 'slug': f'genre-{translit_slug(g.name)}'})
            seen_ids.add(g.id)

    if len(genre_sections) < 8:
        pop_ids = _get_popular_ids()
        other = Genre.objects.exclude(id__in=seen_ids).annotate(
            qcount=Count('movie', filter=Q(
                movie__id__in=pop_ids,
                movie__poster_url__isnull=False,
                movie__rating__gte=7.0,
                movie__rating__lt=9.5,
            ))
        ).filter(qcount__gte=8).order_by('-qcount')[:10]
        for g in other:
            if len(genre_sections) >= 12:
                break
            movies = fetch(base_qs.filter(genres=g), 10)
            if len(movies) >= 4:
                genre_sections.append({'genre': g, 'movies': movies, 'slug': f'genre-{translit_slug(g.name)}'})

    # Годы — один bulk-запрос вместо 8 отдельных
    year_sections = []
    for year in range(current_year, current_year - 8, -1):
        movies = fetch(base_qs.filter(release_date__year=year), 10)
        if len(movies) >= 4:
            year_sections.append({'year': year, 'year_slug': f'year-{year}', 'movies': movies})

    ctx = {
        'top_movies': top_movies,
        'new_movies': new_movies,
        'classic_movies': classic_movies,
        'genre_sections': genre_sections,
        'year_sections': year_sections,
    }
    _cache.set('collections_ctx', ctx, 60 * 60 * 3)  # кэш на 3 часа
    return ctx


def movie_collections(request):
    context = _build_collections_context()
    return render(request, 'movies/movie_collections.html', context)


def actor_detail(request, actor_id):
    actor = get_object_or_404(Actor, id=actor_id)

    # ЛЕНИВАЯ ЗАГРУЗКА: Если биографии нет, а TMDB ID есть - докачиваем данные
    if not actor.bio and actor.tmdb_id:
        try:
            api_key = settings.TMDB_API_KEY
            url = f"https://api.themoviedb.org/3/person/{actor.tmdb_id}?api_key={api_key}&language=ru-RU"
            response = requests.get(url, timeout=5)

            if response.status_code == 200:
                data = response.json()

                if data.get('biography'):
                    actor.bio = data['biography']
                if data.get('birthday'):
                    actor.birth_date = datetime.strptime(data['birthday'], '%Y-%m-%d').date()
                if not actor.photo_url and data.get('profile_path'):
                    actor.photo_url = f"https://image.tmdb.org/t/p/w500{data['profile_path']}"

                actor.save()  # Сохраняем в базу навсегда
        except Exception as e:
            print(f"Ошибка ленивой загрузки TMDB для актера {actor.name}: {e}")

    movies = list(actor.movies.all().order_by('-rating')[:30])
    return render(request, 'movies/actor_detail.html', {
        'actor': actor,
        'movies': movies,
    })


def actors_list(request):
    """Страница со списком актеров — с кэшированием по странице."""
    from django.core.cache import cache as _cache
    page_number = int(request.GET.get('page', 1))
    cache_key = f'actors_list_p{page_number}'

    cached = _cache.get(cache_key)
    if cached:
        return render(request, 'movies/actors_list.html', cached)

    actors = Actor.objects.annotate(movies_count=Count('movies')).order_by('-movies_count')
    paginator = Paginator(actors, 16)
    actors_page = paginator.get_page(page_number)

    ctx = {'actors': actors_page, 'total_pages': paginator.num_pages}
    _cache.set(cache_key, ctx, 1800)  # 30 минут
    return render(request, 'movies/actors_list.html', ctx)


def load_more_actors(request):
    """AJAX-запрос для подгрузки следующих 16 актеров."""
    page = int(request.GET.get('page', 2))
    actors = Actor.objects.annotate(movies_count=Count('movies')).order_by('-movies_count')

    paginator = Paginator(actors, 16)  # Здесь тоже меняем на 16, чтобы шаг совпадал
    actors_page = paginator.get_page(page)

    actors_data = [
        {
            'id': actor.id,
            'name': actor.name,
            'photo_url': _proxy_url(actor.photo_url) or 'https://via.placeholder.com/200x300',
            'birth_date': actor.birth_date.strftime('%d.%m.%Y') if actor.birth_date else 'Дата рождения неизвестна',
            'detail_url': request.build_absolute_uri(reverse('movies:actor_detail', args=[actor.id]))
        }
        for actor in actors_page
    ]

    return JsonResponse({
        'actors': actors_data,
        'has_next': actors_page.has_next(),
        'next_page': actors_page.next_page_number() if actors_page.has_next() else None
    })


def search_page(request):
    genres = Genre.objects.all()
    return render(request, 'movies/search_page.html', {'genres': genres})


def person_detail(request, person_id):
    person = get_object_or_404(Person, id=person_id)

    # ЛЕНИВАЯ ЗАГРУЗКА для режиссеров и сценаристов
    if not person.bio and person.tmdb_id:
        try:
            api_key = settings.TMDB_API_KEY
            url = f"https://api.themoviedb.org/3/person/{person.tmdb_id}?api_key={api_key}&language=ru-RU"
            response = requests.get(url, timeout=5)

            if response.status_code == 200:
                data = response.json()

                if data.get('biography'):
                    person.bio = data['biography']
                if data.get('birthday'):
                    person.birth_date = datetime.strptime(data['birthday'], '%Y-%m-%d').date()
                if not person.photo_url and data.get('profile_path'):
                    person.photo_url = f"https://image.tmdb.org/t/p/w500{data['profile_path']}"

                person.save()
        except Exception as e:
            print(f"Ошибка ленивой загрузки TMDB для {person.name}: {e}")

    credits = MovieCredit.objects.filter(person=person).select_related('movie').prefetch_related('movie__genres')

    return render(request, 'movies/person_detail.html', {
        'person': person,
        'credits': credits,
    })


def collection_detail(request, collection_type):
    title_map = {
        'top-100': 'Топ-100 фильмов',
        'decade-2010s': '2010–2020 годы',
    }
    if collection_type == 'top-100':
        movies = Movie.objects.filter(
            poster_url__isnull=False
        ).exclude(poster_url='').order_by('-rating')[:100]
        collection_title = 'Топ-100 фильмов'
    elif collection_type.startswith('genre-'):
        genre_name = collection_type[len('genre-'):]
        # Обратная транслитерация не нужна — ищем по slug в genre
        from .templatetags.movie_tags import translit_slug
        genre = None
        for g in Genre.objects.all():
            if translit_slug(g.name) == genre_name:
                genre = g
                break
        if genre:
            movies = genre.movie_set.filter(poster_url__isnull=False).exclude(poster_url='').order_by('-rating')
            collection_title = f'Жанр: {genre.name}'
        else:
            movies = Movie.objects.none()
            collection_title = genre_name
    elif collection_type.startswith('year-'):
        year = collection_type[len('year-'):]
        movies = Movie.objects.filter(
            release_date__year=year, poster_url__isnull=False
        ).exclude(poster_url='').order_by('-rating')
        collection_title = f'Фильмы {year} года'
    elif collection_type == 'decade-2010s':
        movies = Movie.objects.filter(
            release_date__year__gte=2010, release_date__year__lt=2020,
            poster_url__isnull=False
        ).exclude(poster_url='').order_by('-rating')
        collection_title = '2010–2020 годы'
    elif collection_type.startswith('decade-'):
        start = int(collection_type[len('decade-'):])
        movies = Movie.objects.filter(
            release_date__year__gte=start, release_date__year__lt=start + 10,
            poster_url__isnull=False
        ).exclude(poster_url='').order_by('-rating')
        collection_title = f'{start}–{start+10} годы'
    else:
        movies = Movie.objects.none()
        collection_title = collection_type

    return render(request, 'movies/movie_collection_detail.html', {
        'movies': movies,
        'collection_title': collection_title,
    })


def is_admin(user):
    return user.is_authenticated and user.is_staff


@login_required
@user_passes_test(is_admin)
def admin_dashboard(request):
    from django.contrib.auth import get_user_model
    from django.core.cache import cache as _cache
    User = get_user_model()

    stats = _cache.get('admin_stats')
    if stats is None:
        # Убираем странный вызов .__class__(...) и пишем просто и понятно:
        stats = {
            'movies_count': Movie.objects.count(),
            'users_count': User.objects.exclude(username__startswith='ml_user_').count(),
            'reviews_count': Review.objects.exclude(user__username__startswith='ml_user_').count(),
        }
        _cache.set('admin_stats', stats, 300)
        
        
    # Только реальные пользователи (не ml_user_*), последние 200
    users = User.objects.exclude(
        username__startswith='ml_user_'
    ).order_by('-date_joined')[:200]

    # Только реальные отзывы, последние 200
    reviews = Review.objects.exclude(
        user__username__startswith='ml_user_'
    ).select_related('user', 'movie').order_by('-created_at')[:200]

    return render(request, 'movies/admin_dashboard.html', {
        'users': users,
        'reviews': reviews,
        'movies_count': stats['movies_count'],
        'users_count': stats['users_count'],
        'reviews_count': stats['reviews_count'],
    })


@login_required
@user_passes_test(is_admin)
def block_user(request, user_id):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user = get_object_or_404(User, id=user_id)
    user.is_blocked = True
    user.is_active = False
    user.save()
    messages.success(request, f'Пользователь {user.username} заблокирован.')
    return redirect('movies:admin_dashboard')


@login_required
@user_passes_test(is_admin)
def unblock_user(request, user_id):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user = get_object_or_404(User, id=user_id)
    user.is_blocked = False
    user.is_active = True
    user.save()
    messages.success(request, f'Пользователь {user.username} разблокирован.')
    return redirect('movies:admin_dashboard')


@login_required
@user_passes_test(is_admin)
def delete_review(request, review_id):
    review = get_object_or_404(Review, id=review_id)
    review.delete()
    messages.success(request, 'Отзыв удалён.')
    return redirect('movies:admin_dashboard')



def mindmap_page(request):
    """Интерактивная карта связей между фильмами."""
    initial = Movie.objects.filter(
        rating__gte=7.0,
        poster_url__isnull=False,
    ).exclude(poster_url='').order_by('-rating')[:15]
    return render(request, 'movies/mindmap.html', {'initial_movies': initial})


def mindmap_initial_api(request):
    """AJAX: начальные фильмы для карты — только с русскими названиями."""
    movies = Movie.objects.filter(
        poster_url__isnull=False,
        poster_url__startswith='http',
        rating__gte=6.0,
        title__regex=r'[а-яА-ЯёЁ]',
    ).exclude(poster_url='').exclude(title='').order_by('-rating')[:60]
    return JsonResponse({'movies': [
        {
            'id': m.id,
            'title': m.title,
            'rating': round(m.rating or 0, 1),
            'poster_url': _proxy_url(m.poster_url),
            'year': m.release_date.year if m.release_date else '',
        }
        for m in movies
    ]})


def mindmap_similar_api(request, movie_id):
    """AJAX: похожие фильмы для карты связей — из реляционной матрицы в БД."""
    movie_id = int(movie_id)

    # Фильтр для названий на русском языке и наличия постеров
    RU_filters = {
        'second_movie__poster_url__isnull': False,
        'second_movie__poster_url__startswith': 'http',
        'second_movie__title__regex': r'[а-яА-ЯёЁ]'
    }

    # Забираем топ-8 похожих фильмов из нашей взвешенной матрицы
    similar_records = MovieSimilarity.objects.filter(
        first_movie_id=movie_id,
        **RU_filters
    ).order_by('-score').select_related('second_movie')[:8]

    movies = [record.second_movie for record in similar_records]

    # Если в нашей матрице вдруг пусто (например, для этого фильма еще не считали), делаем фоллбэк
    if not movies:
        source = Movie.objects.filter(id=movie_id).prefetch_related('genres').first()
        if source:
            genre_ids = list(source.genres.values_list('id', flat=True))
            qs = Movie.objects.filter(
                rating__gte=6.0,
                poster_url__isnull=False,
                poster_url__startswith='http',
                title__regex=r'[а-яА-ЯёЁ]'
            ).exclude(id=movie_id)
            if genre_ids:
                qs = qs.filter(genres__id__in=genre_ids).annotate(
                    common=Count('genres', filter=Q(genres__id__in=genre_ids))
                ).order_by('-common', '-rating')
            else:
                qs = qs.order_by('-rating')
            movies = list(qs.distinct()[:8])

    return JsonResponse({'movies': [
        {
            'id': m.id,
            'title': m.title,
            'rating': round(m.rating or 0, 1),
            'poster_url': _proxy_url(m.poster_url),
            'year': m.release_date.year if m.release_date else '',
        }
        for m in movies
    ]})


def delete_own_review(request, review_id):
    review = get_object_or_404(Review, id=review_id, user=request.user)
    movie_id = review.movie.id
    review.delete()
    return redirect('movies:movie_detail', movie_id=movie_id)


def search_actors(request):
    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return JsonResponse({'actors': []})
    actors = Actor.objects.filter(name__icontains=query)[:8]
    return JsonResponse({'actors': [
        {'id': a.id, 'name': a.name, 'photo_url': _proxy_url(a.photo_url)}
        for a in actors
    ]})


def proxy_image(request):
    """
    Проксирует изображения с image.tmdb.org через сервер Railway.
    Нужно для пользователей из РФ, где домен может быть заблокирован.
    Использование: /movies/img/?url=https://image.tmdb.org/...
    """
    url = request.GET.get('url', '').strip()

    # Разрешаем только TMDB-изображения — защита от open redirect
    ALLOWED_HOSTS = ('image.tmdb.org', 'www.themoviedb.org', 'i.ytimg.com', 'img.youtube.com')
    if not url:
        return HttpResponse(status=400)
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc
        if host not in ALLOWED_HOSTS:
            return HttpResponse(status=403)
    except Exception:
        return HttpResponse(status=400)

    try:
        resp = requests.get(
            url,
            timeout=10,
            headers={
                'User-Agent': 'Mozilla/5.0 (compatible; MovieRecommender/1.0)',
                'Referer': 'https://www.themoviedb.org/',
            },
        )
        if resp.status_code != 200:
            return HttpResponse(status=resp.status_code)
        content_type = resp.headers.get('Content-Type', 'image/jpeg')
        response = HttpResponse(resp.content, content_type=content_type)
        # Кэш на 7 дней — постеры не меняются
        response['Cache-Control'] = 'public, max-age=604800'
        return response
    except Exception:
        return HttpResponse(status=502)
