from django.contrib import admin
from django.urls import path, include
from django.shortcuts import render
from django.conf import settings
from django.conf.urls.static import static
from movies.models import Movie, Genre
from movies.views import _get_popular_ids
from datetime import timedelta
from django.utils import timezone
from django.db.models import Count, Q


def _get_recent_movies(today, target=20):
    """
    Расширяет окно дат пока не наберём target фильмов.
    30 дней → 60 → 90 → 180 → 365 → 3 года
    """
    base = Movie.objects.filter(
        poster_url__isnull=False,
        release_date__lte=today,
    ).exclude(poster_url='').order_by('-release_date', '-rating')

    for days in (30, 60, 90, 180, 365, 365 * 3):
        from_date = today - timedelta(days=days)
        qs = list(base.filter(release_date__gte=from_date)[:target])
        if len(qs) >= target:
            return qs, days
    return list(base[:target]), None


def home(request):
    from django.core.cache import cache

    today = timezone.now().date()

    # ── Новинки с динамическим расширением окна ──────────────────
    recent_movies, days_used = _get_recent_movies(today, target=20)

    # ── Популярные фильмы — только реально известные ─────────────
    # Берём фильмы с ≥50 отзывами от ml_user_* (проверенно популярные)
    # + хороший рейтинг + постер + не мусор (рейтинг < 9.5)
    pop_movies = cache.get('home_popular')
    if pop_movies is None:
        pop_ids = _get_popular_ids()
        pop_movies = list(
            Movie.objects.filter(
                id__in=pop_ids,
                poster_url__isnull=False,
                rating__gte=7.5,
                rating__lt=9.0,          # отсекаем накрученный 9+ мусор
            ).exclude(poster_url='')
            .annotate(
                ml_reviews=Count(
                    'reviews',
                    filter=Q(reviews__user__username__startswith='ml_user_')
                )
            )
            .filter(ml_reviews__gte=50)   # минимум 50 голосов в датасете
            .order_by('-ml_reviews', '-rating')[:20]
        )
        cache.set('home_popular', pop_movies, 3600)

    genres = Genre.objects.all()

    return render(request, 'base.html', {
        'recent_movies': recent_movies,
        'popular_movies': pop_movies,
        'recent_days': days_used,
        'genres': genres,
    })


urlpatterns = [
    path('admin/', admin.site.urls),  # Админка Django
    path('users/', include('users.urls')),  # Маршруты приложения пользователей
    path('movies/', include(('movies.urls', 'movies'), namespace='movies')),
    path('', home, name='home'),  # Главная страница
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)