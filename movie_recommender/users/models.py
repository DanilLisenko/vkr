from django.contrib.auth.models import AbstractUser
from django.db import models

# ИМПОРТ MOVIE УДАЛЕН ОТСЮДА!

class CustomUser(AbstractUser):
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True, verbose_name="Аватар")
    bio = models.TextField(max_length=500, blank=True, verbose_name="О себе")
    birth_date = models.DateField(null=True, blank=True, verbose_name="Дата рождения")
    is_blocked = models.BooleanField(default=False, verbose_name="Заблокирован")
    is_admin = models.BooleanField(default=False, verbose_name="Администратор")

    favorite_movies = models.ManyToManyField(
        'movies.Movie',  # <-- Заменили на строку
        through='FavoriteMovie',
        related_name='favorited_by',
        blank=True,
        verbose_name="Избранные фильмы"
    )

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"

    def __str__(self):
        return self.username


class FavoriteMovie(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    movie = models.ForeignKey('movies.Movie', on_delete=models.CASCADE)  # <-- Заменили на строку
    added_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата добавления")

    class Meta:
        unique_together = ('user', 'movie')
        verbose_name = "Избранный фильм"
        verbose_name_plural = "Избранные фильмы"