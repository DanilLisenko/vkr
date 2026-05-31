from django.core.management.base import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    help = 'Полная автоматизация ИИ: сбор данных → матрица похожести → обучение нейросети'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('=== СТАРТ ПОЛНОГО ОБНОВЛЕНИЯ ИИ-СИСТЕМЫ ==='))

        try:
            self.stdout.write('\n[Этап 1] Загрузка новых фильмов через TMDB API...')
            call_command('fetch_new_movies')
            self.stdout.write(self.style.SUCCESS('-> Новые фильмы загружены!'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Ошибка на Этапе 1: {e}'))

        try:
            self.stdout.write('\n[Этап 2] Расчёт матрицы похожести фильмов...')
            call_command('build_similarity', top=10, min_rating=6.0)
            self.stdout.write(self.style.SUCCESS('-> Матрица похожести пересчитана!'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Ошибка на Этапе 2: {e}'))

        try:
            self.stdout.write('\n[Этап 3] Переобучение нейросети...')
            call_command('train_recommender')
            self.stdout.write(self.style.SUCCESS('-> Нейросеть переобучена!'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Ошибка на Этапе 3: {e}'))

        self.stdout.write(self.style.SUCCESS('\n=== ВСЕ ЭТАПЫ ЗАВЕРШЕНЫ ==='))
