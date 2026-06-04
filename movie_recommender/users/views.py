from urllib.parse import quote as _url_quote
from django.shortcuts import render, redirect, get_object_or_404


def _proxy_url(url):
    """Возвращает URL без изменений — прокси обрабатывается JS onerror."""
    return url or ''
from django.views.generic import CreateView, UpdateView, TemplateView, DetailView
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.http import JsonResponse
from django.db.models import Count, Q
from .models import CustomUser
from .forms import CustomUserCreationForm, CustomUserChangeForm
from movies.models import Watchlist, Review, Genre, Movie


class RegisterView(CreateView):
    form_class = CustomUserCreationForm
    success_url = reverse_lazy('users:profile')
    template_name = 'users/register.html'

    def get_context_data(self, **kwargs):
        from django.core.cache import cache
        from movies.views import _get_popular_ids
        ctx = super().get_context_data(**kwargs)
        ctx['genres'] = Genre.objects.all()

        # Реально популярные фильмы из ML-датасета — много голосов + хороший рейтинг
        reg_movies = cache.get('reg_popular_movies')
        if reg_movies is None:
            pop_ids = _get_popular_ids()
            reg_movies = list(
                Movie.objects.filter(
                    id__in=pop_ids,
                    poster_url__isnull=False,
                    rating__gte=7.5,
                    rating__lt=9.0,
                ).exclude(poster_url='')
                .annotate(ml_cnt=Count(
                    'reviews',
                    filter=Q(reviews__user__username__startswith='ml_user_')
                ))
                .filter(ml_cnt__gte=100)   # минимум 100 оценок в датасете = реально известный
                .order_by('-ml_cnt', '-rating')[:80]  # берём 80 лучших для разнообразия
            )
            cache.set('reg_popular_movies', reg_movies, 3600 * 6)
        ctx['popular_movies'] = reg_movies
        return ctx

    def form_valid(self, form):
        from django.contrib.auth import login
        from .models import FavoriteMovie

        user = form.save()  # создаём пользователя напрямую

        # Сохраняем избранные фильмы
        movie_ids = self.request.POST.get('favorite_movies', '')
        if movie_ids:
            for mid in movie_ids.split(','):
                try:
                    movie = Movie.objects.get(id=int(mid.strip()))
                    FavoriteMovie.objects.get_or_create(user=user, movie=movie)
                except (Movie.DoesNotExist, ValueError):
                    pass

        # Авто-логин и редирект в профиль
        login(self.request, user, backend='django.contrib.auth.backends.ModelBackend')
        return redirect('users:profile')


class UserLoginView(LoginView):
    template_name = 'users/login.html'

    def get_success_url(self):
        return reverse_lazy('users:profile')


class UserLogoutView(LogoutView):
    next_page = '/'


class ProfileView(LoginRequiredMixin, TemplateView):
    template_name = 'users/profile.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        watchlist = Watchlist.objects.filter(user=user, watched=False).select_related('movie')
        watched = Watchlist.objects.filter(user=user, watched=True).select_related('movie')
        reviews = Review.objects.filter(user=user).select_related('movie').order_by('-created_at')
        ctx['watchlist_movies'] = watchlist
        ctx['watched_movies'] = watched
        ctx['reviews'] = reviews
        ctx['watched_count'] = watched.count()
        ctx['watchlist_count'] = watchlist.count()
        return ctx


class EditProfileView(LoginRequiredMixin, UpdateView):
    model = CustomUser
    form_class = CustomUserChangeForm
    template_name = 'users/edit_profile.html'
    success_url = reverse_lazy('users:profile')

    def get_object(self, queryset=None):
        return self.request.user


class SavedMoviesView(LoginRequiredMixin, TemplateView):
    template_name = 'users/saved_movies.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        ctx['watchlist'] = Watchlist.objects.filter(user=user, watched=False).select_related('movie')
        ctx['watched'] = Watchlist.objects.filter(user=user, watched=True).select_related('movie')
        return ctx


class UserProfileView(DetailView):
    model = CustomUser
    template_name = 'users/user_profile.html'
    context_object_name = 'profile_user'

    def get_object(self, queryset=None):
        return get_object_or_404(CustomUser, username=self.kwargs.get('username'))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        profile_user = self.get_object()
        ctx['reviews'] = Review.objects.filter(user=profile_user).select_related('movie').order_by('-created_at')
        ctx['watched_count'] = Watchlist.objects.filter(user=profile_user, watched=True).count()
        return ctx


def similar_movies_api(request):
    """AJAX: похожие фильмы для шага выбора при регистрации."""
    movie_ids = request.GET.get('selected', '')
    preferred_genre_ids_raw = request.GET.get('genres', '')
    page = int(request.GET.get('page', 0))
    exclude_ids = []
    genre_ids = []

    # Явно переданные жанры (из шага 2 регистрации) — наивысший приоритет
    preferred_genre_ids = []
    if preferred_genre_ids_raw:
        try:
            preferred_genre_ids = [int(x) for x in preferred_genre_ids_raw.split(',') if x.strip()]
        except ValueError:
            pass

    if movie_ids:
        try:
            exclude_ids = [int(x) for x in movie_ids.split(',') if x.strip()]
            # Добавляем жанры из лайкнутых фильмов к явным
            movie_genre_ids = list(Movie.objects.filter(
                id__in=exclude_ids
            ).values_list('genres__id', flat=True).distinct())
            genre_ids = list(set(preferred_genre_ids + movie_genre_ids))
        except ValueError:
            pass
    else:
        genre_ids = preferred_genre_ids

    qs = Movie.objects.filter(
        poster_url__isnull=False,
        poster_url__startswith='http',
        rating__gte=6.5,
        rating__lt=9.5,
        title__regex=r'[а-яА-ЯёЁ]',  # только фильмы с русскими названиями
    ).exclude(poster_url='').exclude(title='')

    if genre_ids:
        qs = qs.filter(genres__id__in=genre_ids).annotate(
            common=Count('genres', filter=Q(genres__id__in=genre_ids))
        ).order_by('-common', '-rating')
    else:
        qs = qs.order_by('-rating')

    if exclude_ids:
        qs = qs.exclude(id__in=exclude_ids)

    offset = page * 30
    movies = list(qs.distinct()[offset:offset + 30])
    return JsonResponse({'movies': [
        {
            'id': m.id,
            'title': m.title,
            'poster_url': _proxy_url(m.poster_url),
            'rating': round(m.rating, 1),
            'year': m.release_date.year if m.release_date else '',
        }
        for m in movies
    ]})