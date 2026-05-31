"""
Management command: загрузка новых фильмов с TMDb.

Использование:
    python manage.py fetch_new_movies              # последние 5 страниц (100 фильмов)
    python manage.py fetch_new_movies --pages 20  # 400 фильмов
    python manage.py fetch_new_movies --year 2024 # только фильмы 2024 года
    python manage.py fetch_new_movies --top       # топ-рейтинговые, не новинки
"""
import time
import requests
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.core.cache import cache
from movies.models import Movie, Genre, Actor, MovieCredit, Person

API_KEY  = '8bf31002475b2fd4bc514cd9d272c4e5'
BASE_URL = 'https://api.themoviedb.org/3'
HEADERS  = {'Accept': 'application/json'}


def tmdb_get(path, params=None, timeout=10):
    p = {'api_key': API_KEY, 'language': 'ru-RU'}
    if params:
        p.update(params)
    try:
        r = requests.get(f'{BASE_URL}{path}', params=p, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return None


def save_movie(data, stdout, verbosity=1):
    tmdb_id = data.get('id')
    if not tmdb_id:
        return None

    title = data.get('title') or data.get('name') or ''
    if not title:
        return None

    poster_path = data.get('poster_path')
    poster_url  = f'https://image.tmdb.org/t/p/w500{poster_path}' if poster_path else ''
    if not poster_url:
        return None  # без постера не добавляем

    rating       = round(data.get('vote_average', 0), 1)
    release_date = data.get('release_date') or None
    description  = data.get('overview') or ''

    movie, created = Movie.objects.update_or_create(
        tmdb_id=tmdb_id,
        defaults={
            'title':        title,
            'description':  description,
            'rating':       rating,
            'poster_url':   poster_url,
            'release_date': release_date or None,
        }
    )

    # Жанры
    for gdata in data.get('genres', []):
        genre, _ = Genre.objects.get_or_create(name=gdata['name'])
        movie.genres.add(genre)

    if verbosity >= 2:
        status = '✓ создан' if created else '↻ обновлён'
        stdout.write(f'  {status}: {title} ({release_date}) рейтинг {rating}')

    return movie, created


def fetch_credits(movie, tmdb_id, stdout):
    """Загружает актёров и режиссёров для фильма."""
    data = tmdb_get(f'/movie/{tmdb_id}/credits')
    if not data:
        return

    # Актёры (топ-10)
    for cast in data.get('cast', [])[:10]:
        person_tmdb = cast.get('id')
        name = cast.get('name') or ''
        photo_path = cast.get('profile_path')
        photo_url  = f'https://image.tmdb.org/t/p/w185{photo_path}' if photo_path else ''

        actor, _ = Actor.objects.get_or_create(
            tmdb_id=person_tmdb,
            defaults={'name': name, 'photo_url': photo_url}
        )
        if photo_url and not actor.photo_url:
            Actor.objects.filter(pk=actor.pk).update(photo_url=photo_url)
        movie.actors.add(actor)

    # Режиссёры
    for crew in data.get('crew', []):
        if crew.get('job') != 'Director':
            continue
        person_tmdb = crew.get('id')
        name = crew.get('name') or ''
        photo_path = crew.get('profile_path')
        photo_url  = f'https://image.tmdb.org/t/p/w185{photo_path}' if photo_path else ''

        person, _ = Person.objects.get_or_create(
            tmdb_id=person_tmdb,
            defaults={'name': name, 'photo_url': photo_url}
        )
        MovieCredit.objects.get_or_create(
            person=person, movie=movie,
            defaults={'role': 'Director', 'department': 'Directing'}
        )


class Command(BaseCommand):
    help = 'Загружает новые / популярные фильмы с TMDb в базу данных'

    def add_arguments(self, parser):
        parser.add_argument('--pages',    type=int, default=5,    help='Страниц для загрузки (20 фильмов = 1 страница)')
        parser.add_argument('--year',     type=int, default=None, help='Фильтр по году выхода (напр. --year 2024)')
        parser.add_argument('--top',      action='store_true',    help='Брать топ по рейтингу вместо новинок')
        parser.add_argument('--credits',  action='store_true',    help='Загружать актёров и режиссёров (медленнее)')
        parser.add_argument('--min-rating', type=float, default=6.0, help='Минимальный рейтинг (default: 6.0)')
        parser.add_argument('--detail',       type=int,   default=1,    help='Уровень вывода (1=кратко, 2=подробно)')
        parser.add_argument('--from-year',    type=int,   default=None, help='Загрузить фильмы начиная с года (discover mode)')
        parser.add_argument('--to-year',      type=int,   default=None, help='До года включительно')
        parser.add_argument('--min-votes',    type=int,   default=200,  help='Минимум голосов на TMDb (default: 200)')

    def handle(self, *args, **options):
        pages      = options['pages']
        year       = options['year']
        top_mode   = options['top']
        do_credits = options['credits']
        min_rating = options['min_rating']
        verbosity  = options['detail']
        from_year  = options['from_year']
        to_year    = options['to_year']
        min_votes  = options['min_votes']

        # Режим discover по диапазону лет
        if from_year:
            import datetime
            to_year = to_year or datetime.date.today().year
            self.stdout.write(self.style.SUCCESS(
                f'\n=== Discover: {from_year}-{to_year}, рейтинг >= {min_rating}, голосов >= {min_votes} ===\n'
            ))
            created_total = updated_total = skipped_total = 0
            for yr in range(from_year, to_year + 1):
                self.stdout.write(f'\n--- Год {yr} ---')
                for page in range(1, pages + 1):
                    params = {
                        'page': page,
                        'sort_by': 'vote_count.desc',
                        'primary_release_year': yr,
                        'vote_count.gte': min_votes,
                        'vote_average.gte': min_rating,
                    }
                    data = tmdb_get('/discover/movie', params)
                    if not data or 'results' not in data:
                        break
                    results = data['results']
                    total_pages = data.get('total_pages', 1)
                    self.stdout.write(f'  стр {page}/{min(pages,total_pages)}: {len(results)} фильмов')
                    for md in results:
                        if md.get('vote_average', 0) < min_rating:
                            skipped_total += 1; continue
                        detail = tmdb_get(f'/movie/{md["id"]}')
                        if not detail:
                            skipped_total += 1; continue
                        result = save_movie(detail, self.stdout, verbosity)
                        if result is None:
                            skipped_total += 1; continue
                        _, was_created = result
                        if was_created: created_total += 1
                        else: updated_total += 1
                        time.sleep(0.05)
                    if page >= min(pages, total_pages):
                        break
                    time.sleep(0.3)

            from django.core.cache import cache
            cache.delete('collections_ctx')
            cache.delete('admin_stats')
            self.stdout.write(self.style.SUCCESS(
                f'\nГОТОВО! Создано: {created_total}, Обновлено: {updated_total}, Пропущено: {skipped_total}\n'
            ))
            return

        endpoint = '/movie/top_rated' if top_mode else '/movie/now_playing'
        mode_name = 'топ-рейтинговые' if top_mode else 'новинки'
        self.stdout.write(self.style.SUCCESS(
            f'\n=== Загрузка фильмов с TMDb ({mode_name}, {pages} страниц) ===\n'
        ))

        created_total = 0
        updated_total = 0
        skipped_total = 0

        for page in range(1, pages + 1):
            params = {'page': page, 'region': 'RU'}
            if year:
                endpoint    = '/discover/movie'
                params['primary_release_year'] = year
                params['sort_by'] = 'vote_average.desc' if top_mode else 'release_date.desc'
                params['vote_count.gte'] = min_votes

            data = tmdb_get(endpoint, params)
            if not data or 'results' not in data:
                self.stdout.write(self.style.WARNING(f'  Страница {page}: нет данных'))
                break

            results = data['results']
            total_pages = data.get('total_pages', pages)
            self.stdout.write(f'Страница {page}/{min(pages, total_pages)} — {len(results)} фильмов')

            for movie_data in results:
                rating = movie_data.get('vote_average', 0)
                if rating < min_rating:
                    skipped_total += 1
                    continue

                # Получаем детали (жанры есть только в detail)
                detail = tmdb_get(f'/movie/{movie_data["id"]}')
                if not detail:
                    skipped_total += 1
                    continue

                result = save_movie(detail, self.stdout, verbosity)
                if result is None:
                    skipped_total += 1
                    continue

                movie_obj, was_created = result
                if was_created:
                    created_total += 1
                else:
                    updated_total += 1

                if do_credits and was_created:
                    fetch_credits(movie_obj, movie_data['id'], self.stdout)
                    time.sleep(0.1)  # не спамим API

                time.sleep(0.05)

            if page < pages:
                time.sleep(0.5)

        # Сбрасываем кэш подборок чтобы новые фильмы появились
        cache.delete('collections_ctx')
        cache.delete('admin_stats')

        self.stdout.write(self.style.SUCCESS(
            f'\nГОТОВО!\n'
            f'   Создано:   {created_total}\n'
            f'   Обновлено: {updated_total}\n'
            f'   Пропущено: {skipped_total}\n'
            f'   Кеш подборок сброшен.\n'
        ))
