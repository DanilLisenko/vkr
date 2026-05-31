import os
import torch
import torch.nn as nn
import pickle
from django.conf import settings
from movies.models import Movie, Review


# =========================================================
# Архитектура в точности повторяет ту, что в твоем файле .pth
# =========================================================
class MovieRecommenderNet(nn.Module):
    def __init__(self, num_users, num_movies, embedding_size=50):
        super().__init__()
        # Слои строго из твоего файла (user_embeddings, movie_embeddings, fc1, fc2)
        self.user_embeddings = nn.Embedding(num_users, embedding_size)
        self.movie_embeddings = nn.Embedding(num_movies, embedding_size)

        # Предполагаем стандартный размер слоев 128.
        # Если при загрузке будет ошибка - поправим эти цифры!
        self.fc1 = nn.Linear(embedding_size * 2, 128)
        self.relu = nn.ReLU()
        self.fc2 = nn.Linear(128, 1)
        self.sigmoid = nn.Sigmoid()

    def forward(self, user_indices, movie_indices):
        user_embeds = self.user_embeddings(user_indices)
        movie_embeds = self.movie_embeddings(movie_indices)

        x = torch.cat([user_embeds, movie_embeds], dim=1)
        x = self.relu(self.fc1(x))
        x = self.sigmoid(self.fc2(x))
        return x


def get_ai_recommendation(user, limit=10):
    """
    Возвращает список из `limit` фильмов с наивысшим предсказанным рейтингом.
    """
    user_reviews = Review.objects.filter(user=user)

    # Фоллбэк 1: Если нет оценок
    if not user_reviews.exists():
        return list(Movie.objects.filter(rating__gte=8.0).order_by('?')[:limit])

    model_path = os.path.join(settings.BASE_DIR, 'ml_weights', 'recommender_weights.pth')
    encoders_path = os.path.join(settings.BASE_DIR, 'ml_weights', 'recommender_mapping.pkl')

    # Фоллбэк 2: Если файлов нет
    if not os.path.exists(model_path) or not os.path.exists(encoders_path):
        return list(Movie.objects.filter(rating__gte=7.5).order_by('?')[:limit])

    with open(encoders_path, 'rb') as f:
        mapping = pickle.load(f)

    if isinstance(mapping, dict):
        user_encoder = mapping.get('user_to_idx', {})
        movie_encoder = mapping.get('movie_to_idx', {})
    else:
        user_encoder, movie_encoder = mapping

    # Фоллбэк 3: Если новый пользователь
    if user.id not in user_encoder:
        return list(Movie.objects.filter(rating__gte=8.0).order_by('?')[:limit])

    encoded_user_id = user_encoder[user.id]
    num_users = len(user_encoder)
    num_movies = len(movie_encoder)

    model = MovieRecommenderNet(num_users, num_movies)
    model.load_state_dict(torch.load(model_path, map_location=torch.device('cpu')))
    model.eval()

    watched_movie_ids = set(user_reviews.values_list('movie_id', flat=True))

    candidates = []
    decoder_movie = {v: k for k, v in movie_encoder.items()}
    for internal_movie_id, real_movie_id in decoder_movie.items():
        if real_movie_id not in watched_movie_ids:
            candidates.append((internal_movie_id, real_movie_id))

    if not candidates:
        return list(Movie.objects.order_by('?')[:limit])

    user_tensor = torch.tensor([encoded_user_id] * len(candidates))
    movie_tensor = torch.tensor([c[0] for c in candidates])

    with torch.no_grad():
        predictions = model(user_tensor, movie_tensor).squeeze()

    # НАХОДИМ ТОП-N ФИЛЬМОВ (вместо одного)
    k = min(limit, len(candidates))
    top_indices = torch.topk(predictions, k=k).indices.tolist()

    if isinstance(top_indices, int):
        top_indices = [top_indices]

    best_real_movie_ids = [candidates[idx][1] for idx in top_indices]

    # Достаем фильмы из БД и сохраняем порядок от ИИ
    movies = list(Movie.objects.filter(id__in=best_real_movie_ids))
    movies.sort(key=lambda x: best_real_movie_ids.index(x.id))

    return movies