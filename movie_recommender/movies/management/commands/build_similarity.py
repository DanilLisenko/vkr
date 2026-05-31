"""
Генерирует матрицу похожести фильмов на основе:
  - общих жанров (вес 0.6)
  - близости рейтинга (вес 0.2)
  - близости года выхода (вес 0.2)

Результат: { movie_id: [sim_id1, sim_id2, ...] } (топ-10 похожих)
Сохраняется в ml_weights/movie_similarities.pkl

Использование:
    python manage.py build_similarity
    python manage.py build_similarity --top 8    # топ-8 вместо 10
    python manage.py build_similarity --min-rating 6.0
"""
import os
import pickle
import time
from django.core.management.base import BaseCommand
from django.conf import settings
from movies.models import Movie


class Command(BaseCommand):
    help = 'Строит матрицу похожести фильмов и сохраняет в ml_weights/movie_similarities.pkl'

    def add_arguments(self, parser):
        parser.add_argument('--top',        type=int,   default=10,  help='Сколько похожих хранить (default 10)')
        parser.add_argument('--min-rating', type=float, default=6.0, help='Минимальный рейтинг (default 6.0)')
        parser.add_argument('--chunk',      type=int,   default=500, help='Размер батча (default 500)')

    def handle(self, *args, **options):
        top        = options['top']
        min_rating = options['min_rating']
        chunk      = options['chunk']

        self.stdout.write('Загружаем фильмы...')
        movies = list(
            Movie.objects.filter(
                poster_url__isnull=False,
                rating__gte=min_rating,
            ).exclude(poster_url='')
            .prefetch_related('genres')
        )
        self.stdout.write(f'Загружено: {len(movies)} фильмов')

        # Строим словари для быстрого доступа
        movie_genres = {}  # id -> set of genre ids
        movie_rating = {}  # id -> rating
        movie_year   = {}  # id -> year

        for m in movies:
            movie_genres[m.id] = set(m.genres.values_list('id', flat=True))
            movie_rating[m.id] = float(m.rating or 0)
            movie_year[m.id]   = m.release_date.year if m.release_date else 2000

        ids = [m.id for m in movies]
        n   = len(ids)

        # Нормализация года для сравнения
        min_year = min(movie_year.values()) if movie_year else 1900
        max_year = max(movie_year.values()) if movie_year else 2025
        year_range = max(max_year - min_year, 1)

        similarity_matrix = {}
        t0 = time.time()

        self.stdout.write(f'Строим матрицу похожести ({n}x{n})...')

        for i in range(0, n, chunk):
            batch = ids[i:i + chunk]
            for aid in batch:
                genres_a = movie_genres[aid]
                rating_a = movie_rating[aid]
                year_a   = movie_year[aid]
                scores   = []

                for bid in ids:
                    if bid == aid:
                        continue
                    genres_b = movie_genres[bid]

                    # 1. Жанровое сходство (Jaccard)
                    union     = genres_a | genres_b
                    intersect = genres_a & genres_b
                    genre_sim = len(intersect) / len(union) if union else 0

                    # 2. Близость рейтинга (1 - нормализованная разница)
                    rating_sim = 1.0 - min(abs(rating_a - movie_rating[bid]) / 4.0, 1.0)

                    # 3. Близость года
                    year_sim = 1.0 - abs(year_a - movie_year[bid]) / year_range

                    score = genre_sim * 0.6 + rating_sim * 0.2 + year_sim * 0.2
                    scores.append((bid, score))

                scores.sort(key=lambda x: -x[1])
                similarity_matrix[aid] = [sid for sid, _ in scores[:top]]

            done = min(i + chunk, n)
            elapsed = time.time() - t0
            eta = elapsed / done * (n - done) if done > 0 else 0
            self.stdout.write(
                f'  {done}/{n}  ({100*done//n}%)  '
                f'прошло: {elapsed:.0f}s  осталось: ~{eta:.0f}s'
            )

        out_path = os.path.join(settings.BASE_DIR, 'ml_weights', 'movie_similarities.pkl')
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, 'wb') as f:
            pickle.dump(similarity_matrix, f, protocol=pickle.HIGHEST_PROTOCOL)

        elapsed = time.time() - t0
        self.stdout.write(self.style.SUCCESS(
            f'\nГОТОВО за {elapsed:.1f}s\n'
            f'Фильмов: {len(similarity_matrix)}\n'
            f'Сохранено в: {out_path}\n'
        ))
