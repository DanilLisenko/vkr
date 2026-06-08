from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from .models import Movie
from .management.commands.build_similarity import update_similarity_for_single_movie

@receiver(m2m_changed, sender=Movie.genres.through)
def movie_genres_changed_receiver(sender, instance, action, **kwargs):
    """
    Сигнал срабатывает, когда у фильма привязываются/изменяются жанры.
    Обычно при парсинге (TMDB) это финальный шаг сохранения связей.
    """
    if action == "post_add":
        try:
            update_similarity_for_single_movie(instance)
        except Exception as e:
            # Важно обернуть в try-except, чтобы сбой в ML не ломал транзакцию импорта фильма
            print(f"Ошибка автоматического расчета схожести для фильма {instance.title}: {e}")