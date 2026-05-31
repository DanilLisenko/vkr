import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "django-insecure-pn)%g0i6z!lo&^rn-zwhi^%nyv6r4@&li2u42ueifgdo(heu96"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = []

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "users",
    "movies",
    'django.contrib.postgres',
    'django_extensions',
]


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "movie_recommender.middleware.BlockUserMiddleware",  # Добавляем middleware
]

ROOT_URLCONF = "movie_recommender.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [os.path.join(BASE_DIR, 'templates')],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "movie_recommender.wsgi.application"

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'movie_recommend',
        'USER': 'postgres',
        'PASSWORD': '1105',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
LANGUAGE_CODE = 'ru'
TIME_ZONE = 'Europe/Moscow'
USE_I18N = True
USE_L10N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATICFILES_DIRS = []  # Удаляем movies/static/, так как AppDirectoriesFinder уже обрабатывает эту директорию
STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_FINDERS = [
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
]

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CSRF_FAILURE_VIEW = 'movie_recommender.views.csrf_failure'

AUTH_USER_MODEL = 'users.CustomUser'

LOGIN_URL = '/users/login/'
LOGIN_REDIRECT_URL = '/users/profile/'
LOGOUT_REDIRECT_URL = '/'

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media/')

TMDB_API_KEY = '8bf31002475b2fd4bc514cd9d272c4e5'

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'movierecommender-cache',
        'OPTIONS': {
            'MAX_ENTRIES': 2000,       # держим до 2000 объектов в памяти
            'CULL_FREQUENCY': 4,       # при переполнении удаляем 1/4
        }
    }
}

# Сессии в памяти — быстрее чем в БД
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': 'logs/admin_actions.log',
        },
    },
    'loggers': {
        'users': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}


AUTH_USER_MODEL = 'users.CustomUser'