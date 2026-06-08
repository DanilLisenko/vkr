"""
Content-based similarity recommender.
Uses the pre-computed MovieSimilarity matrix (built via build_similarity command)
with Jaccard-based genre similarity and weighted feature combination.
"""
from movies.models import Movie, Review, MovieSimilarity

def get_content_recommendations(user, limit=10):
    """
    Возвращает до `limit` рекомендованных фильмов для пользователя на основе:
    - Матрицы MovieSimilarity (взвешенные оценки жанров/актеров/команды/тегов/рейтинга/года)
    - Отзывов пользователя: вес = review.rating - 5.5 (положительный выше среднего, отрицательный ниже)
    - Элементов Watchlist: базовый вес 1.0
    - Фильмов, лайкнутых при регистрации (FavoriteMovie): базовый вес 1.5
    Служит фоллбэком к популярным фильмам для абсолютно «холодных» пользователей.
    """
    from movies.models import Watchlist
    from users.models import FavoriteMovie  # Импортируем модель избранного с регистрации

    # 1. Собираем все ID фильмов, с которыми пользователь уже взаимодействовал
    watched_ids = set(Watchlist.objects.filter(user=user).values_list('movie_id', flat=True))
    reviewed_ids = set(Review.objects.filter(user=user).values_list('movie_id', flat=True))
    favorite_ids = set(FavoriteMovie.objects.filter(user=user).values_list('movie_id', flat=True))
    
    # Объединяем их, чтобы исключить из выдачи рекомендаций (пользователь их уже знает)
    all_interacted_ids = watched_ids | reviewed_ids | favorite_ids

    # 2. Формируем словарь весов для профиля интересов пользователя
    movie_weights = {}
    
    # Добавляем фильмы, лайкнутые при регистрации (даем им высокий приоритет)
    for f_id in favorite_ids:
        movie_weights[f_id] = 1.5
        
    # Добавляем фильмы из списка отложенных «Буду смотреть» (базовый вес 1.0)
    for w_id in watched_ids:
        if w_id not in movie_weights:
            movie_weights[w_id] = 1.0
            
    # Добавляем или перезаписываем веса на основе явных оценок из отзывов
    for review in Review.objects.filter(user=user):
        movie_weights[review.movie_id] = review.rating - 5.5

    # Если профиль абсолютно пуст (пользователь пропустил все шаги регистрации и не ставил оценки)
    if not movie_weights:
        return list(
            Movie.objects.filter(poster_url__isnull=False, rating__gte=7.5)
            .exclude(poster_url='')
            .order_by('-rating')[:limit]
        )

    # 3. Выборка схожих фильмов из предсчитанной матрицы схожести объектов
    similarity_records = (
        MovieSimilarity.objects
        .filter(first_movie_id__in=movie_weights.keys())
        .exclude(second_movie_id__in=all_interacted_ids)
        .select_related('second_movie')
    )

    candidate_scores = {}
    for record in similarity_records:
        weight = movie_weights.get(record.first_movie_id, 1.0)
        score = record.score * weight
        entry = candidate_scores.setdefault(record.second_movie_id, {'movie': record.second_movie, 'total': 0.0})
        entry['total'] += score

    # Сортируем кандидатов по кумулятивному баллу
    ranked = sorted(candidate_scores.values(), key=lambda x: x['total'], reverse=True)
    recommended = [e['movie'] for e in ranked if e['total'] > 0][:limit]

    # Если рекомендаций по матрице не хватило до лимита, добиваем хорошими фильмами
    if len(recommended) < limit:
        extra = limit - len(recommended)
        exclude = all_interacted_ids | {m.id for m in recommended}
        recommended += list(
            Movie.objects.filter(poster_url__isnull=False, rating__gte=7.0)
            .exclude(id__in=exclude)
            .order_by('-rating')[:extra]
        )

    return recommended