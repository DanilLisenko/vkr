from django.contrib import admin
from .models import Movie, Genre, Review, Watchlist, Actor, Person,MovieCredit  # Убери MovieCredit


# Регистрируем модели для отображения в админке
admin.site.register(Movie)
admin.site.register(Genre)
admin.site.register(Review)
admin.site.register(Watchlist)
admin.site.register(Actor)
admin.site.register(Person)
admin.site.register(MovieCredit)
