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
import re
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.models import Q
from movies.models import Movie, Watchlist, Genre

User = get_user_model()

# Регулярка для определения кириллического названия (переведённые русские названия)
_CYRILLIC_RE = re.compile('[а-яА-ЯёЁ]')

PROFILES = [
    {
        'username': 'action_fan',
        'display': 'Любитель боевиков',
        'liked_genres': ['Боевик', 'Action'],
        'disliked_genres': ['Мелодрама', 'Romance'],
        'high_rating': 9,
        'low_rating': 3,
    },
    {
        'username': 'comedy_fan',
        'display': 'Любитель комедий',
        'liked_genres': ['Комедия', 'Comedy'],
        'disliked_genres': ['Ужасы', 'Horror'],
        'high_rating': 9,
        'low_rating': 3,
    },
    {
        'username': 'drama_fan',
        'display': 'Любитель драм',
        'liked_genres': ['Драма', 'Drama'],
        'disliked_genres': ['Мультфильм', 'Animation'],
        'high_rating': 9,
        'low_rating': 3,
    },
    {
        'username': 'horror_fan',
        'display': 'Любитель ужасов',
        'liked_genres': ['Ужасы', 'Horror', 'Триллер', 'Thriller'],
        'disliked_genres': ['Комедия', 'Comedy'],
        'high_rating': 9,
        'low_rating': 3,
    },
    {
        'username': 'scifi_fan',
        'display': 'Любитель фантастики',
        'liked_genres': ['Фантастика', 'Science Fiction', 'Sci-Fi'],
        'disliked_genres': ['Мелодрама', 'Romance'],
        'high_rating': 9,
        'low_rating': 3,
    },
]

PASSWORD = 'Test1234!'
LIKED_COUNT = 8
DISLIKED_COUNT = 4
WATCHLIST_COUNT = 5

# Известные популярные фильмы по жанрам — приоритетный список.
# Если фильм есть в БД по точному названию, он ставится в начало выборки.
KNOWN_TITLES = {
    'action_fan': [
        'Тёмный рыцарь', 'Темный рыцарь', 'Властелин колец: возвращение короля',
        'Властелин колец: Братство кольца', 'Гладиатор', 'Матрица',
        'Терминатор 2: Судный день', 'Начало', 'Джон Уик', 'Мстители',
        'Первый мститель: Другая война', 'Железный человек',
        'Схватка', 'Бойцовский клуб', 'Без компромиссов',
    ],
    'comedy_fan': [
        'Форрест Гамп', 'Криминальное чтиво', 'Большой Лебовски',
        'Достать ножи', 'Реальная любовь', 'Один дома',
        'Бумажный волк', 'Игра в имитацию', 'Джентльмены',
        'Оружейный барон', 'Субурбикон', 'Отступники',
    ],
    'drama_fan': [
        'Зеленая миля', 'Зелёная миля', 'Побег из Шоушенка',
        'Список Шиндлера', 'Форрест Гамп', 'Пианист',
        'Жизнь прекрасна', 'Достучаться до небес',
        'Реквием по мечте', 'Аромат женщины', '1+1', 'Интouchables',
        'Бойцовский клуб', 'Семь', '7',
    ],
    'horror_fan': [
        'Психо', 'Чужой', 'Сияние', 'Оно', 'Прочь',
        'Тихое место', 'Астрал', 'Заклятие',
        'Мгла', 'Нечто', '28 дней спустя',
        'Молчание ягнят', 'Семь', 'Семь самураев',
    ],
    'scifi_fan': [
        'Интерстеллар', 'Начало', 'Матрица',
        'Звёздные войны: Эпизод 5 - Империя наносит ответный удар',
        'Звёздные войны: Эпизод 4 - Новая надежда',
        'Терминатор 2: Судный день', 'Бегущий по лезвию 2049',
        'Бегущий по лезвию', 'Марсианин', 'Прибытие',
        'Гравитация', 'Луна 2112', 'Из машины',
    ],
}


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

    def _get_movies_for_genres(self, genre_names, username, count, min_rating=6.5):
        """
        Возвращает до `count` фильмов для жанра.
        Приоритет: фильмы из KNOWN_TITLES → остальные русскоязычные по рейтингу.
        """
        # Поиск жанров (точное совпадение + icontains fallback)
        genres = Genre.objects.filter(name__in=genre_names)
        if not genres.exists():
            q = Q()
            for name in genre_names:
                q |= Q(name__icontains=name)
            genres = Genre.objects.filter(q)

        base_qs = (
            Movie.objects
            .filter(genres__in=genres, rating__gte=min_rating)
            .distinct()
        )

        # Сначала пробуем известные фильмы из приоритетного списка
        priority_titles = KNOWN_TITLES.get(username, [])
        result = []
        seen_ids = set()

        if priority_titles:
            q = Q()
            for title in priority_titles:
                q |= Q(title__icontains=title)
            priority_movies = list(base_qs.filter(q).order_by('-rating'))
            for m in priority_movies:
                if m.id not in seen_ids:
                    result.append(m)
                    seen_ids.add(m.id)
                if len(result) >= count:
                    break

        # Добираем из русскоязычных фильмов по рейтингу
        if len(result) < count:
            remaining = count - len(result)
            # Берём большой пул и фильтруем по кириллице
            pool = list(base_qs.exclude(id__in=seen_ids).order_by('-rating')[:200])
            russian = [m for m in pool if _CYRILLIC_RE.search(m.title)]
            for m in russian:
                if m.id not in seen_ids:
                    result.append(m)
                    seen_ids.add(m.id)
                if len(result) >= count:
                    break

        return result[:count]

    def _add_reviews(self, user, profile):
        liked_movies = self._get_movies_for_genres(
            profile['liked_genres'], profile['username'], LIKED_COUNT, min_rating=6.5)
        disliked_movies = self._get_movies_for_genres(
            profile['disliked_genres'], profile['username'], DISLIKED_COUNT, min_rating=6.0)
        watchlist_movies = self._get_movies_for_genres(
            profile['liked_genres'], profile['username'], WATCHLIST_COUNT + LIKED_COUNT, min_rating=7.0)

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

        self.stdout.write(f'\n  {profile["username"]} — любимые фильмы:')
        for movie in liked_movies:
            insert_review(movie.id, profile['high_rating'], 'Отличный фильм! Именно то, что люблю.')
            self.stdout.write(f'    ★{profile["high_rating"]} {movie.title} ({movie.rating:.1f})')
            reviews_created += 1

        self.stdout.write(f'  {profile["username"]} — нелюбимые фильмы:')
        for movie in disliked_movies:
            if movie.id not in liked_ids:
                insert_review(movie.id, profile['low_rating'], 'Не мой жанр, не понравилось.')
                self.stdout.write(f'    ✗{profile["low_rating"]} {movie.title} ({movie.rating:.1f})')
                reviews_created += 1

        watchlist_created = 0
        wl_ids = set(liked_ids)
        for movie in watchlist_movies:
            if movie.id not in wl_ids:
                Watchlist.objects.get_or_create(
                    user=user,
                    movie=movie,
                    defaults={'watched': False},
                )
                wl_ids.add(movie.id)
                watchlist_created += 1
                if watchlist_created >= WATCHLIST_COUNT:
                    break

        self.stdout.write(
            f'  → итого: {reviews_created} отзывов, {watchlist_created} в списке отложенных'
        )
