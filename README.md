# MovieRecommender

Веб-приложение для персонального подбора фильмов на основе матрицы схожести.

## Возможности

- Рекомендации фильмов на основе предпочтений пользователя
- Каталог фильмов с фильтрацией по жанрам
- Карточки актёров и страницы фильмов
- Интерактивная карта связей фильмов
- Живой поиск по фильмам и актёрам
- Тёмная и светлая тема
- Личный кабинет с избранным

## Стек

- **Backend:** Python 3, Django
- **Frontend:** Bootstrap 5, JavaScript
- **База данных:** PostgreSQL
- **Данные:** TMDB API

## Установка и запуск

```bash
# Клонировать репозиторий
git clone https://gitverse.ru/danillisenko/vkr2.git
cd vkr2

# Создать виртуальное окружение
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/macOS

# Установить зависимости
pip install -r requirements.txt

# Применить миграции
python manage.py migrate

# Запустить сервер
python manage.py runserver
```

## Лицензия

[MIT](LICENSE)
