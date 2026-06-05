from django.core.management.base import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    help = 'Полное обновление: загрузка фильмов и пересчёт матрицы схожести'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('=== СТАРТ ПОЛНОГО ОБНОВЛЕНИЯ ==='))

        try:
            self.stdout.write('\n[Этап 1] Загрузка новых фильмов через TMDB API...')
            call_command('fetch_new_movies')
            self.stdout.write(self.style.SUCCESS('-> Новые фильмы загружены!'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Ошибка на Этапе 1: {e}'))

        try:
            self.stdout.write('\n[Этап 2] Расчёт матрицы схожести фильмов...')
            call_command('build_similarity')
            self.stdout.write(self.style.SUCCESS('-> Матрица схожести пересчитана!'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Ошибка на Этапе 2: {e}'))

        self.stdout.write(self.style.SUCCESS('\n=== ВСЕ ЭТАПЫ ЗАВЕРШЕНЫ ==='))
