import os
import pickle
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
from django.core.management.base import BaseCommand
from django.conf import settings
from movies.models import Review
from movies.ml_recommender import MovieRecommenderNet


class Command(BaseCommand):
    help = 'Обучает PyTorch модель коллаборативной фильтрации на основе отзывов пользователей'

    def handle(self, *args, **options):
        self.stdout.write('Загрузка отзывов из базы данных...')
        reviews = list(Review.objects.all().values('user_id', 'movie_id', 'rating'))

        if len(reviews) < 10:
            self.stdout.write(self.style.ERROR('Недостаточно данных (отзывов) для обучения нейросети!'))
            return

        user_ids  = [r['user_id']  for r in reviews]
        movie_ids = [r['movie_id'] for r in reviews]
        ratings   = [float(r['rating']) for r in reviews]

        unique_users  = list(set(user_ids))
        unique_movies = list(set(movie_ids))

        user_to_idx  = {uid: idx for idx, uid in enumerate(unique_users)}
        movie_to_idx = {mid: idx for idx, mid in enumerate(unique_movies)}

        X_user  = torch.tensor([user_to_idx[u]  for u in user_ids],  dtype=torch.long)
        X_movie = torch.tensor([movie_to_idx[m] for m in movie_ids], dtype=torch.long)

        max_rating = max(ratings) if ratings else 10.0
        Y = torch.tensor([r / max_rating for r in ratings], dtype=torch.float32)

        dataset = TensorDataset(X_user, X_movie, Y)
        loader  = DataLoader(dataset, batch_size=32, shuffle=True)

        num_users  = len(user_to_idx)
        num_movies = len(movie_to_idx)

        self.stdout.write(
            f'Пользователей: {num_users}, Фильмов: {num_movies}, Оценок: {len(ratings)}'
        )

        model     = MovieRecommenderNet(num_users, num_movies, embedding_size=50)
        criterion = nn.MSELoss()
        optimizer = optim.Adam(model.parameters(), lr=0.005)

        model.train()
        epochs = 15
        for epoch in range(epochs):
            total_loss = 0
            for batch_user, batch_movie, batch_y in loader:
                optimizer.zero_grad()
                preds = model(batch_user, batch_movie).squeeze()
                if preds.dim() == 0:
                    preds = preds.unsqueeze(0)
                loss = criterion(preds, batch_y)
                loss.backward()
                optimizer.step()
                total_loss += loss.item()

            if (epoch + 1) % 5 == 0 or epoch == 0:
                self.stdout.write(
                    f'  Эпоха {epoch+1}/{epochs} | Loss: {total_loss/len(loader):.4f}'
                )

        weights_dir   = os.path.join(settings.BASE_DIR, 'ml_weights')
        os.makedirs(weights_dir, exist_ok=True)
        model_path    = os.path.join(weights_dir, 'recommender_weights.pth')
        encoders_path = os.path.join(weights_dir, 'recommender_mapping.pkl')

        torch.save(model.state_dict(), model_path)
        with open(encoders_path, 'wb') as f:
            pickle.dump({'user_to_idx': user_to_idx, 'movie_to_idx': movie_to_idx}, f)

        self.stdout.write(self.style.SUCCESS('Модель и маппинги сохранены в ml_weights/'))
