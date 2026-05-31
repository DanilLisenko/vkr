from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    path('register/', views.RegisterView.as_view(), name='register'),
    path('login/', views.UserLoginView.as_view(), name='login'),
    path('logout/', views.UserLogoutView.as_view(), name='logout'),
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('profile/edit/', views.EditProfileView.as_view(), name='edit_profile'),
    path('saved-movies/', views.SavedMoviesView.as_view(), name='saved_movies'),
    path('profile/<str:username>/', views.UserProfileView.as_view(), name='user_profile'),
    path('api/similar-movies/', views.similar_movies_api, name='similar_movies_api'),
]