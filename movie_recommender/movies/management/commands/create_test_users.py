"""
Создает 5 тестовых пользователей с разными вкусами для демонстрации системы рекомендаций.

Пользователь            Вкус                    Логин / пароль
───────────────────────────────────────────────────────────────
action_fan              Боевики                 action_fan / Test1234!
comedy_fan              Комедии                 comedy_fan / Test1234!
drama_fan               Драмы                   drama_fan / Test1234!
horror_fan              Ужасы                   horror_fan / Test1234!
scifi_fan               Фантастика              scifi_fan / Test1234!
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import connection
from movies.models import Movie, Watchlist, Genre

User = get_user_model()

# Профили тестовых пользователей
PROFILES = [
    {
        'username': 'action_fan',
        'display': 'Любитель боевиков',
        'liked_genres': ['боевик', 'action', 'Боевик', 'Action'],
        'disliked_genres': ['мелодрама', 'romance', 'Мелодрама', 'Romance'],
        'high_rating': 9,
        'low_rating': 3,
    },
    {
        'username': 'comedy_fan',
        'display': 'Любитель комедий',
        'liked_genres': ['комедия', 'comedy', 'Комедия', 'Comedy'],
        'disliked_genres': ['ужасы', 'horror', 'Ужасы', 'Horror'],
        'high_rating': 9,
        'low_rating': 3,
    },
    {
        'username': 'drama_fan',
        'display': 'Любитель драм',
        'liked_genres': ['драма', 'drama', 'Драма', 'Drama'],
        'disliked_genres': ['мультфильм', 'animation', 'Мультфильм', 'Animation'],
        'high_rating': 9,
        'low_rating': 3,
    },
    {
        'username': 'horror_fan',
        'display': 'Любитель ужасов',
        'liked_genres': ['ужасы', 'horror', 'Ужасы', 'Horror', 'триллер', 'thriller', 'Триллер', 'Thriller'],
        'disliked_genres': ['комедия', 'comedy', 'Комедия', 'Comedy'],
        'high_rating': 9,
        'low_rating': 3,
    },
    {
        'username': 'scifi_fan',
        'display': 'Любитель фантастики',
        'liked_genres': ['фантастика', 'science fiction', 'Фантастика', 'Science Fiction',
                         'sci-fi', 'Sci-Fi', 'научная фантастика'],
        'disliked_genres': ['мелодрама', 'romance', 'Мелодрама', 'Romance'],
        'high_rating': 9,
        'low_rating': 3,
    },
]

PASSWORD = 'Test1234!'
# Количество фильмов каждого жанра которым выставляем высокую/низкую оценку
LIKED_COUNT = 8
DISLIKED_COUNT = 4
WATCHLIST_COUNT = 5


class Command(BaseCommand):
    help = 'Создает 5 тестовых пользователей с разными вкусами для демонстрации рекомендаций'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true',
                            help='Удалить и пересоздать тестовых пользователей')

    def handle(self, *args, **options):
        for profile in PROFILES:
            username = profile['username']

            if options['reset']:
                User.objects.filter(username=username).delete()
                self.stdout.write(f'Удален пользователь {username}')

            user, created = User.objects.get_or_create(
                username=username,
                defaults={'email': f'{username}@example.com'},
            )
            if created:
                user.set_password(PASSWORD)
                user.save()
                self.stdout.write(self.style.SUCCESS(f'Создан пользователь {username}'))
            else:
                self.stdout.write(f'Пользователь {username} уже существует, обновляем данные...')
                # Очищаем старые отзывы и список
                with connection.cursor() as cursor:
                    cursor.execute('DELETE FROM movies_review WHERE user_id = %s', [user.id])
                Watchlist.objects.filter(user=user).delete()

            self._add_reviews(user, profile)

        self.stdout.write(self.style.SUCCESS(
            '\nГотово! Тестовые пользователи:\n'
            '  action_fan  — боевики     (пароль: Test1234!)\n'
            '  comedy_fan  — комедии     (пароль: Test1234!)\n'
            '  drama_fan   — драмы       (пароль: Test1234!)\n'
            '  horror_fan  — ужасы       (пароль: Test1234!)\n'
            '  scifi_fan   — фантастика  (пароль: Test1234!)\n'
        ))

    def _get_movies_for_genres(self, genre_names, count, min_rating=5.0):
        """Возвращает до `count` фильмов, принадлежащих хотя бы одному из указанных жанров."""
        genres = Genre.objects.filter(name__in=genre_names)
        if not genres.exists():
            # Fallback: case-insensitive partial match
            from django.db.models import Q
            q = Q()
            for name in genre_names:
                q |= Q(name__icontains=name)
            genres = Genre.objects.filter(q)

        movies = (
            Movie.objects
            .filter(genres__in=genres, rating__gte=min_rating)
            .distinct()
            .order_by('-rating')[:count]
        )
        return list(movies)

    def _add_reviews(self, user, profile):
        liked_movies = self._get_movies_for_genres(profile['liked_genres'], LIKED_COUNT, min_rating=6.0)
        disliked_movies = self._get_movies_for_genres(profile['disliked_genres'], DISLIKED_COUNT, min_rating=5.0)
        watchlist_movies = self._get_movies_for_genres(profile['liked_genres'], WATCHLIST_COUNT + LIKED_COUNT, min_rating=7.0)

        liked_ids = {m.id for m in liked_movies}
        reviews_created = 0

        def insert_review(movie_id, rating, text):
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO movies_review (user_id, movie_id, rating, review_text, created_at, is_deleted)
                    VALUES (%s, %s, %s, %s, NOW(), FALSE)
                    ON CONFLICT (user_id, movie_id) DO NOTHING
                    """,
                    [user.id, movie_id, rating, text],
                )

        for movie in liked_movies:
            insert_review(movie.id, profile['high_rating'], 'Отличный фильм! Именно то, что люблю.')
            reviews_created += 1

        for movie in disliked_movies:
            if movie.id not in liked_ids:
                insert_review(movie.id, profile['low_rating'], 'Не мой жанр, не понравилось.')
                reviews_created += 1

        watchlist_created = 0
        wl_ids = {m.id for m in liked_movies}
        for movie in watchlist_movies:
            if movie.id not in wl_ids:
                Watchlist.objects.get_or_create(
                    user=user,
                    movie=movie,
                    defaults={'watched': False},
                )
                watchlist_created += 1
                if watchlist_created >= WATCHLIST_COUNT:
                    break

        self.stdout.write(
            f'  {user.username}: {reviews_created} отзывов, {watchlist_created} в списке'
        )
