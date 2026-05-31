from django.urls import path
from . import views

app_name = 'movies'

urlpatterns = [
    path('recommend/', views.recommend_movie, name='recommend_movie'),
    path('<int:movie_id>/', views.movie_detail, name='movie_detail'),
    path('<int:movie_id>/add_to_watchlist/', views.add_to_watchlist, name='add_to_watchlist'),
    path('<int:movie_id>/mark_as_watched/', views.mark_as_watched, name='mark_as_watched'),
    path('collections/', views.movie_collections, name='movie_collections'),

    path('actor/<int:actor_id>/', views.actor_detail, name='actor_detail'),
    path('actors/', views.actors_list, name='actors_list'),
    path('load-more-actors/', views.load_more_actors, name='load_more_actors'),

    # === ДОБАВЛЯЕМ ВОТ ЭТУ СТРОКУ ===
    path('person/<int:person_id>/', views.person_detail, name='person_detail'),

    path('search/', views.search, name='search'),
    path('search-page/', views.search_page, name='search_page'),
    path('search_actors/', views.search_actors, name='search_actors'),
    path('mindmap/', views.mindmap_page, name='mindmap'),
    path('api/similar/<int:movie_id>/', views.mindmap_similar_api, name='mindmap_similar_api'),

    path('collections/<str:collection_type>/', views.collection_detail, name='collection_detail'),

    path('review/<int:review_id>/delete-own/', views.delete_own_review, name='delete_own_review'),

    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('admin-dashboard/block/<int:user_id>/', views.block_user, name='block_user'),
    path('admin-dashboard/unblock/<int:user_id>/', views.unblock_user, name='unblock_user'),
    path('admin-dashboard/delete-review/<int:review_id>/', views.delete_review, name='delete_review'),
]