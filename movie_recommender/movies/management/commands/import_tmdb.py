import asyncio
import aiohttp
from aiohttp import ClientTimeout
from asgiref.sync import sync_to_async
from django.core.management.base import BaseCommand
from movies.models import Movie, Genre, Actor
import time

API_KEY = "8bf31002475b2fd4bc514cd9d272c4e5"
BASE_URL = "https://api.themoviedb.org/3"
MAX_CONCURRENT_REQUESTS = 30  # Лимит параллельных запросов
MAX_PAGES = 500  # TMDB позволяет до 500 страниц (10,000 фильмов при 20 на страницу)

class Command(BaseCommand):
    help = "Импорт фильмов и обновление актеров из TMDB в базу данных"

    def add_arguments(self, parser):
        parser.add_argument('--pages', type=int, default=MAX_PAGES, help='Количество страниц для импорта фильмов из TMDB')
        parser.add_argument('--update-actors', action='store_true', help='Обновить информацию об актерах (биография, фото, дата рождения)')

    async def fetch_json(self, session, url, params=None, retries=3):
        """Асинхронный запрос к API с обработкой таймаута и повторными попытками."""
        timeout = ClientTimeout(total=30)
        for attempt in range(retries):
            try:
                async with session.get(url, params=params, timeout=timeout) as response:
                    response.raise_for_status()
                    return await response.json()
            except (asyncio.TimeoutError, aiohttp.ClientError) as e:
                if attempt < retries - 1:
                    self.stdout.write(self.style.WARNING(f"Таймаут/ошибка на попытке {attempt + 1} для {url}: {str(e)}, пробую снова..."))
                    await asyncio.sleep(2)
                    continue
                else:
                    self.stdout.write(self.style.ERROR(f"Ошибка после {retries} попыток для {url}: {str(e)}"))
                    return None
        return None

    async def fetch_movies_list(self, session, pages):
        """Получает список фильмов с TMDB."""
        url = f"{BASE_URL}/movie/popular"
        params = {"api_key": API_KEY, "language": "ru-RU"}
        movies = []

        for page in range(1, pages + 1):
            params["page"] = page
            data = await self.fetch_json(session, url, params)
            if not data or "results" not in data:
                self.stdout.write(self.style.ERROR(f"Ошибка на странице {page}: {data}"))
                break
            movies.extend(data["results"])
            self.stdout.write(f"Загружено {len(movies)} фильмов (страница {page}/{pages})")
            await asyncio.sleep(0.25)  # Задержка для соблюдения лимита API

        return movies

    async def fetch_movie_details(self, session, tmdb_id, semaphore):
        """Получает детальную информацию о фильме."""
        url = f"{BASE_URL}/movie/{tmdb_id}"
        params = {"api_key": API_KEY, "language": "ru-RU", "append_to_response": "credits"}
        async with semaphore:
            return await self.fetch_json(session, url, params)

    async def process_movie(self, session, movie_data, semaphore):
        """Обрабатывает и сохраняет фильм в базе данных."""
        try:
            tmdb_id = movie_data["id"]
            data = await self.fetch_movie_details(session, tmdb_id, semaphore)
            if not data or "status_code" in data:
                self.stdout.write(self.style.WARNING(f"Не удалось получить данные для TMDB ID {tmdb_id}"))
                return

            title = data.get("title", "Неизвестно")
            description = data.get("overview", "")
            release_date = data.get("release_date") or None
            rating = data.get("vote_average", 0)
            poster_url = f"https://image.tmdb.org/t/p/w500{data.get('poster_path')}" if data.get("poster_path") else ""

            genre_names = [genre["name"] for genre in data.get("genres", [])]
            cast = data.get("credits", {}).get("cast", [])

            movie, created = await sync_to_async(Movie.objects.update_or_create)(
                tmdb_id=tmdb_id,
                defaults={
                    "title": title,
                    "description": description,
                    "release_date": release_date,
                    "rating": rating,
                    "poster_url": poster_url,
                },
            )

            action = "Добавлен" if created else "Обновлен"
            self.stdout.write(self.style.SUCCESS(f'{action} фильм: "{title}" (TMDB ID: {tmdb_id})'))

            await self.update_movie_genres(movie, genre_names)
            await self.update_movie_actors(movie, cast)

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Ошибка обработки TMDB ID {tmdb_id}: {str(e)}"))

    @sync_to_async
    def update_movie_genres(self, movie, genre_names):
        """Обновляет жанры фильма."""
        genres = [Genre.objects.get_or_create(name=name)[0] for name in genre_names]
        movie.genres.set(genres)

    @sync_to_async
    def update_movie_actors(self, movie, cast):
        """Обновляет актеров фильма."""
        actors = []
        for actor_data in cast:
            actor, _ = Actor.objects.get_or_create(
                tmdb_id=actor_data["id"],
                defaults={"name": actor_data["name"]}
            )
            actors.append(actor)
        movie.actors.set(actors)

    async def fetch_actor_details(self, session, tmdb_id, semaphore):
        """Получает детальную информацию об актере."""
        url = f"{BASE_URL}/person/{tmdb_id}"
        params = {"api_key": API_KEY, "language": "ru-RU"}
        async with semaphore:
            return await self.fetch_json(session, url, params)

    async def update_actor(self, session, actor, semaphore):
        """Обновляет информацию об актере."""
        try:
            if not actor.tmdb_id:
                self.stdout.write(self.style.WARNING(f"У актера {actor.name} отсутствует tmdb_id, пропускаем..."))
                return

            data = await self.fetch_actor_details(session, actor.tmdb_id, semaphore)
            if not data or "status_code" in data:
                self.stdout.write(self.style.WARNING(f"Не удалось получить данные для актера TMDB ID {actor.tmdb_id}"))
                return

            # Обновляем данные
            actor.bio = data.get("biography", "") or ""
            actor.birth_date = data.get("birthday") or None

            # Сохраняем URL фото
            profile_path = data.get("profile_path")
            if profile_path:
                actor.photo_url = f"https://image.tmdb.org/t/p/w500{profile_path}"
            else:
                actor.photo_url = ""

            # Сохраняем изменения
            await sync_to_async(actor.save)()
            self.stdout.write(self.style.SUCCESS(f"Обновлен актер: {actor.name} (TMDB ID: {actor.tmdb_id})"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Ошибка обновления актера TMDB ID {actor.tmdb_id}: {str(e)}"))

    async def update_actors(self):
        """Основной метод обновления актеров."""
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        batch_size = 1000  # Обрабатываем по 1000 актеров за раз
        offset = 0

        while True:
            actors = await sync_to_async(list)(Actor.objects.all()[offset:offset + batch_size])
            if not actors:
                break
            self.stdout.write(f"Обрабатываем актеров с {offset} по {offset + len(actors)}...")
            async with aiohttp.ClientSession() as session:
                tasks = [self.update_actor(session, actor, semaphore) for actor in actors]
                await asyncio.gather(*tasks)
            offset += batch_size

    async def load_movies(self, pages):
        """Основной метод загрузки фильмов с TMDB."""
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        async with aiohttp.ClientSession() as session:
            movies = await self.fetch_movies_list(session, pages)
            self.stdout.write(f"Всего найдено фильмов: {len(movies)}")
            tasks = [self.process_movie(session, movie_data, semaphore) for movie_data in movies]
            await asyncio.gather(*tasks)

    def handle(self, *args, **options):
        """Запускает асинхронную загрузку фильмов или обновление актеров."""
        start_time = time.time()
        if options['update_actors']:
            self.stdout.write("Начинаем обновление информации об актерах...")
            asyncio.run(self.update_actors())
        else:
            pages = min(options['pages'], MAX_PAGES)
            self.stdout.write(f"Начинаем импорт фильмов с TMDB (страниц: {pages})...")
            asyncio.run(self.load_movies(pages))
        elapsed_time = time.time() - start_time
        self.stdout.write(self.style.SUCCESS(f"Процесс завершен за {elapsed_time:.2f} секунд!"))

#завершили 80000 актеров начиная с 1