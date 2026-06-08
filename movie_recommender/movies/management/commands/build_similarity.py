import time
import numpy as np
from django.core.management.base import BaseCommand
from movies.models import Movie, MovieSimilarity, Genre, Actor, MovieCredit
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import MinMaxScaler


def jaccard_similarity_matrix(binary_matrix):
    """
    Вычисляет матрицу схожести Жаккара для бинарной матрицы признаков.
    Жаккар(A, B) = |A ∩ B| / |A ∪ B| = dot(a,b) / (|a| + |b| - dot(a,b))
    """
    intersection = binary_matrix @ binary_matrix.T
    row_sums = binary_matrix.sum(axis=1)
    union = row_sums[:, None] + row_sums[None, :] - intersection
    with np.errstate(invalid='ignore', divide='ignore'):
        sim = np.where(union == 0, 0.0, intersection / union)
    return sim


class Command(BaseCommand):
    help = 'Комплексный расчет матрицы схожести фильмов с учетом весов различных признаков'

    def _step(self, label):
        """Печатает метку шага и возвращает время начала."""
        self.stdout.write(f'  → {label}...', ending=' ')
        self.stdout.flush()
        return time.time()

    def _done(self, t0, extra=''):
        elapsed = time.time() - t0
        suffix = f'  {extra}' if extra else ''
        self.stdout.write(self.style.SUCCESS(f'готово ({elapsed:.1f}с){suffix}'))

    def handle(self, *args, **options):
        total_start = time.time()

        self.stdout.write(self.style.MIGRATE_HEADING('\n=== Построение матрицы схожести фильмов ==='))

        # ------------------------------------------------------------------
        # 0. Загрузка данных
        # ------------------------------------------------------------------
        self.stdout.write('\n[1/7] Загрузка данных из базы')
        t = self._step('фильмы')
        movies = list(Movie.objects.all())
        if not movies:
            self.stdout.write(self.style.WARNING('База фильмов пуста.'))
            return
        n_movies = len(movies)
        movie_to_idx = {movie.id: idx for idx, movie in enumerate(movies)}
        self._done(t, f'({n_movies} фильмов)')

        # === ВЕСА ПРИЗНАКОВ (сумма = 1.0) ===
        W_GENRES = 0.30   # Жаккар по жанрам
        W_ACTORS = 0.20   # Косинус по актёрам
        W_CREW   = 0.15   # Косинус по съёмочной группе
        W_TAGS   = 0.20   # TF-IDF по описанию
        W_RATING = 0.08   # Близость рейтингов
        W_YEAR   = 0.07   # Близость по году

        self.stdout.write(
            f'     Веса: жанры={W_GENRES} | актёры={W_ACTORS} | группа={W_CREW} '
            f'| теги={W_TAGS} | рейтинг={W_RATING} | год={W_YEAR}'
        )

        # ------------------------------------------------------------------
        # А) Жанры — коэффициент Жаккара
        # ------------------------------------------------------------------
        self.stdout.write('\n[2/7] Жанровая матрица (коэффициент Жаккара)')
        t = self._step('загрузка жанров')
        all_genres = list(Genre.objects.values_list('id', flat=True))
        genre_to_idx = {g_id: i for i, g_id in enumerate(all_genres)}
        genres_matrix = np.zeros((n_movies, len(all_genres)), dtype=np.float32)
        for idx, movie in enumerate(movies):
            for g_id in movie.genres.values_list('id', flat=True):
                if g_id in genre_to_idx:
                    genres_matrix[idx, genre_to_idx[g_id]] = 1.0
        self._done(t, f'({len(all_genres)} жанров)')

        t = self._step('расчёт Жаккара')
        sim_genres = jaccard_similarity_matrix(genres_matrix)
        self._done(t, f'(матрица {n_movies}×{n_movies})')

        # ------------------------------------------------------------------
        # Б) Актёры — косинусное сходство
        # ------------------------------------------------------------------
        self.stdout.write('\n[3/7] Матрица актёров (косинусное сходство)')
        t = self._step('загрузка актёров')
        all_actors = list(Actor.objects.values_list('id', flat=True))
        actor_to_idx = {a_id: i for i, a_id in enumerate(all_actors)}
        actors_matrix = np.zeros((n_movies, len(all_actors)), dtype=np.float32)
        for idx, movie in enumerate(movies):
            for a_id in movie.actors.values_list('id', flat=True):
                if a_id in actor_to_idx:
                    actors_matrix[idx, actor_to_idx[a_id]] = 1.0
        self._done(t, f'({len(all_actors)} актёров)')

        t = self._step('расчёт косинуса')
        if actors_matrix.shape[1] == 0:
            sim_actors = np.zeros((n_movies, n_movies), dtype=np.float32)
            self._done(t, '(нет данных → пропуск)')
        else:
            sim_actors = cosine_similarity(actors_matrix)
            self._done(t)

        # ------------------------------------------------------------------
        # В) Съёмочная группа — косинусное сходство
        # ------------------------------------------------------------------
        self.stdout.write('\n[4/7] Матрица съёмочной группы (косинусное сходство)')
        t = self._step('загрузка MovieCredit')
        all_crew_persons = list(MovieCredit.objects.values_list('person_id', flat=True).distinct())
        crew_to_idx = {p_id: i for i, p_id in enumerate(all_crew_persons)}
        crew_matrix = np.zeros((n_movies, len(all_crew_persons)), dtype=np.float32)
        credits = list(MovieCredit.objects.all())
        for credit in credits:
            if credit.movie_id in movie_to_idx and credit.person_id in crew_to_idx:
                crew_matrix[movie_to_idx[credit.movie_id], crew_to_idx[credit.person_id]] = 1.0
        self._done(t, f'({len(all_crew_persons)} человек, {len(credits)} записей)')

        t = self._step('расчёт косинуса')
        if crew_matrix.shape[1] == 0:
            sim_crew = np.zeros((n_movies, n_movies), dtype=np.float32)
            self._done(t, '(нет данных → пропуск)')
        else:
            sim_crew = cosine_similarity(crew_matrix)
            self._done(t)

        # ------------------------------------------------------------------
        # Г) Теги из описания — TF-IDF
        # ------------------------------------------------------------------
        self.stdout.write('\n[5/7] Текстовые теги из описания (TF-IDF)')
        t = self._step('векторизация')
        descriptions = [m.description if m.description else '' for m in movies]
        non_empty = sum(1 for d in descriptions if d)
        russian_stop_words = [
            'и', 'в', 'во', 'что', 'он', 'на', 'я', 'with', 'с', 'со', 'как', 'а', 'то', 'все', 'она',
            'так', 'его', 'но', 'да', 'ты', 'к', 'у', 'же', 'вы', 'за', 'бы', 'по', 'только',
            'ее', 'мне', 'было', 'вот', 'от', 'меня', 'еще', 'о', 'из', 'ему', 'теперь', 'когда',
            'даже', 'вдруг', 'ли', 'если', 'уже', 'или', 'ни', 'быть', 'был', 'него', 'до', 'вас',
        ]
        tfidf = TfidfVectorizer(max_features=400, stop_words=russian_stop_words)
        tfidf_matrix = tfidf.fit_transform(descriptions)
        self._done(t, f'({non_empty} описаний, {tfidf_matrix.shape[1]} признаков)')

        t = self._step('расчёт косинуса')
        sim_tags = cosine_similarity(tfidf_matrix)
        self._done(t)

        # ------------------------------------------------------------------
        # Д) Рейтинг и год
        # ------------------------------------------------------------------
        self.stdout.write('\n[6/7] Близость по рейтингу и году выпуска')
        t = self._step('нормализация')
        ratings = np.array([m.rating for m in movies], dtype=np.float32).reshape(-1, 1)
        years = np.array(
            [m.release_date.year if m.release_date else 2000 for m in movies],
            dtype=np.float32,
        ).reshape(-1, 1)
        scaler = MinMaxScaler()
        norm_ratings = scaler.fit_transform(ratings)
        norm_years = scaler.fit_transform(years)

        sim_rating = np.zeros((n_movies, n_movies), dtype=np.float32)
        sim_year = np.zeros((n_movies, n_movies), dtype=np.float32)
        for i in range(n_movies):
            sim_rating[i] = 1.0 - np.abs(norm_ratings - norm_ratings[i]).flatten()
            sim_year[i] = 1.0 - np.abs(norm_years - norm_years[i]).flatten()
        self._done(t)

        # ------------------------------------------------------------------
        # Е) Агрегация
        # ------------------------------------------------------------------
        self.stdout.write('\n[7/7] Агрегация и сохранение в базу данных')
        t = self._step('объединение матриц')
        np.nan_to_num(sim_genres, copy=False)
        np.nan_to_num(sim_actors, copy=False)
        np.nan_to_num(sim_crew, copy=False)
        np.nan_to_num(sim_tags, copy=False)
        final = (
            W_GENRES * sim_genres +
            W_ACTORS * sim_actors +
            W_CREW   * sim_crew   +
            W_TAGS   * sim_tags   +
            W_RATING * sim_rating +
            W_YEAR   * sim_year
        )
        self._done(t)

        t = self._step('удаление старых записей')
        deleted, _ = MovieSimilarity.objects.all().delete()
        self._done(t, f'(удалено {deleted})')

        t = self._step('формирование новых записей')
        similarity_objects = []
        for i in range(n_movies):
            similar_indices = np.argsort(final[i])[::-1]
            count = 0
            for idx in similar_indices:
                if idx == i:
                    continue
                if count >= 10:
                    break
                similarity_objects.append(MovieSimilarity(
                    first_movie=movies[i],
                    second_movie=movies[idx],
                    score=float(final[i][idx]),
                ))
                count += 1
            if (i + 1) % 500 == 0 or (i + 1) == n_movies:
                self.stdout.write(f'\r  → формирование новых записей... {i + 1}/{n_movies}', ending=' ')
                self.stdout.flush()
        self._done(t, f'({len(similarity_objects)} пар)')

        t = self._step('запись в БД (bulk_create)')
        MovieSimilarity.objects.bulk_create(similarity_objects, batch_size=5000)
        self._done(t)

        total = time.time() - total_start
        self.stdout.write(self.style.SUCCESS(
            f'\n✓ Готово! Матрица схожести обновлена за {total:.1f}с. '
            f'Записей в БД: {len(similarity_objects)}'
        ))
        
        
        
def update_similarity_for_single_movie(new_movie):
    """
    Вычисляет и сохраняет топ-10 похожих фильмов для ОДНОГО нового фильма,
    а также находит фильмы, для которых этот новый фильм входит в топ-10.
    """
    all_movies = list(Movie.objects.exclude(id=new_movie.id))
    if not all_movies:
        return

    # Подготавливаем списки
    movies = [new_movie] + all_movies
    n_movies = len(movies)
    
    # 1. Жанры (Jaccard)
    all_genres = list(Genre.objects.values_list('id', flat=True))
    genre_to_idx = {g_id: i for i, g_id in enumerate(all_genres)}
    genres_matrix = np.zeros((n_movies, len(all_genres)), dtype=np.float32)
    for idx, m in enumerate(movies):
        for g_id in m.genres.values_list('id', flat=True):
            if g_id in genre_to_idx:
                genres_matrix[idx, genre_to_idx[g_id]] = 1.0
    
    intersection = genres_matrix[0] * genres_matrix
    union = genres_matrix[0].sum() + genres_matrix.sum(axis=1) - intersection.sum(axis=1)
    sim_genres = np.where(union == 0, 0.0, intersection.sum(axis=1) / union)

    # 2. Актеры (Cosine)
    all_actors = list(Actor.objects.values_list('id', flat=True))
    actor_to_idx = {a_id: i for i, a_id in enumerate(all_actors)}
    actors_matrix = np.zeros((n_movies, len(all_actors)), dtype=np.float32)
    for idx, m in enumerate(movies):
        for a_id in m.actors.values_list('id', flat=True):
            if a_id in actor_to_idx:
                actors_matrix[idx, actor_to_idx[a_id]] = 1.0
    
    sim_actors = cosine_similarity(actors_matrix[0:1], actors_matrix).flatten() if len(all_actors) > 0 else np.zeros(n_movies)

    # 3. Группа (Cosine)
    all_crew_persons = list(MovieCredit.objects.values_list('person_id', flat=True).distinct())
    crew_to_idx = {p_id: i for i, p_id in enumerate(all_crew_persons)}
    crew_matrix = np.zeros((n_movies, len(all_crew_persons)), dtype=np.float32)
    
    # Тянем кредиты только для участвующих фильмов
    movie_ids = [m.id for m in movies]
    credits = MovieCredit.objects.filter(movie_id__in=movie_ids)
    movie_to_idx = {m_id: idx for idx, m_id in enumerate(movie_ids)}
    for credit in credits:
        if credit.person_id in crew_to_idx:
            crew_matrix[movie_to_idx[credit.movie_id], crew_to_idx[credit.person_id]] = 1.0
            
    sim_crew = cosine_similarity(crew_matrix[0:1], crew_matrix).flatten() if len(all_crew_persons) > 0 else np.zeros(n_movies)

    # 4. Описание TF-IDF
    descriptions = [m.description if m.description else '' for m in movies]
    russian_stop_words = ['и', 'в', 'во', 'что', 'он', 'на', 'я', 'с', 'со', 'как', 'а', 'то', 'все']
    tfidf = TfidfVectorizer(max_features=400, stop_words=russian_stop_words)
    try:
        tfidf_matrix = tfidf.fit_transform(descriptions)
        sim_tags = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix).flatten()
    except Exception:
        sim_tags = np.zeros(n_movies)

    # 5. Рейтинг и год
    ratings = np.array([m.rating for m in movies], dtype=np.float32).reshape(-1, 1)
    years = np.array([m.release_date.year if m.release_date else 2000 for m in movies], dtype=np.float32).reshape(-1, 1)
    
    scaler = MinMaxScaler()
    norm_ratings = scaler.fit_transform(ratings)
    norm_years = scaler.fit_transform(years)
    
    sim_rating = (1.0 - np.abs(norm_ratings - norm_ratings[0])).flatten()
    sim_year = (1.0 - np.abs(norm_years - norm_years[0])).flatten()

    # Агрегация (коэффициенты из Вашей команды build_similarity)
    final_scores = (
        0.30 * sim_genres +
        0.20 * sim_actors +
        0.15 * sim_crew   +
        0.20 * sim_tags   +
        0.08 * sim_rating +
        0.07 * sim_year
    )

    # Удаляем старые связи для этого фильма
    MovieSimilarity.objects.filter(first_movie=new_movie).delete()

    # Записываем новые Топ-10 рекомендаций ДЛЯ этого фильма
    similarity_objects = []
    # Индекс 0 — это сам фильм, поэтому исключаем его через argsort
    similar_indices = np.argsort(final_scores)[::-1]
    
    count = 0
    for idx in similar_indices:
        if idx == 0: # Пропуск самого себя
            continue
        if count >= 10:
            break
        similarity_objects.append(MovieSimilarity(
            first_movie=new_movie,
            second_movie=movies[idx],
            score=float(final_scores[idx])
        ))
        count += 1
        
    MovieSimilarity.objects.bulk_create(similarity_objects)
