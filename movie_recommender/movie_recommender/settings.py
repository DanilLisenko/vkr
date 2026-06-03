import os
from pathlib import Path
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent

# ------------------------------------------------------------------ #
# Безопасность                                                         #
# ------------------------------------------------------------------ #
SECRET_KEY = config('SECRET_KEY', default='django-insecure-pn)%g0i6z!lo&^rn-zwhi^%nyv6r4@&li2u42ueifgdo(heu96')
DEBUG = config('DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())

# ------------------------------------------------------------------ #
# Приложения                                                           #
# ------------------------------------------------------------------ #
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
    "whitenoise.middleware.WhiteNoiseMiddleware",          # статика в продакшене
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "movie_recommender.middleware.BlockUserMiddleware",
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

# ------------------------------------------------------------------ #
# База данных                                                          #
# ------------------------------------------------------------------ #
DATABASE_URL = config('DATABASE_URL', default=None)

if DATABASE_URL:
    # Railway / любой хостинг передаёт DATABASE_URL
    import dj_database_url
    DATABASES = {
        'default': dj_database_url.parse(DATABASE_URL, conn_max_age=600)
    }
else:
    # Локальная разработка
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': config('DB_NAME', default='movie_recommend'),
            'USER': config('DB_USER', default='postgres'),
            'PASSWORD': config('DB_PASSWORD', default='1105'),
            'HOST': config('DB_HOST', default='localhost'),
            'PORT': config('DB_PORT', default='5432'),
        }
    }

# ------------------------------------------------------------------ #
# Валидация паролей                                                    #
# ------------------------------------------------------------------ #
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ------------------------------------------------------------------ #
# Локализация                                                          #
# ------------------------------------------------------------------ #
LANGUAGE_CODE = 'ru'
TIME_ZONE = 'Europe/Moscow'
USE_I18N = True
USE_L10N = True
# Форматы дат принимаемые Django (ДД.ММ.ГГГГ + ISO)
DATE_INPUT_FORMATS = ['%d.%m.%Y', '%Y-%m-%d', '%d/%m/%Y']
USE_TZ = True

# ------------------------------------------------------------------ #
# Статические файлы                                                    #
# ------------------------------------------------------------------ #
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = []
STATICFILES_FINDERS = [
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
]
# WhiteNoise — сжатие и кэширование статики
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media/')

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ------------------------------------------------------------------ #
# Аутентификация                                                       #
# ------------------------------------------------------------------ #
AUTH_USER_MODEL = 'users.CustomUser'
LOGIN_URL = '/users/login/'
LOGIN_REDIRECT_URL = '/users/profile/'
LOGOUT_REDIRECT_URL = '/'
CSRF_FAILURE_VIEW = 'movie_recommender.views.csrf_failure'

# ------------------------------------------------------------------ #
# API ключи                                                            #
# ------------------------------------------------------------------ #
TMDB_API_KEY = config('TMDB_API_KEY', default='8bf31002475b2fd4bc514cd9d272c4e5')

# ------------------------------------------------------------------ #
# Кэш                                                                  #
# ------------------------------------------------------------------ #
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'movierecommender-cache',
        'OPTIONS': {
            'MAX_ENTRIES': 2000,
            'CULL_FREQUENCY': 4,
        }
    }
}

SESSION_ENGINE = 'django.contrib.sessions.backends.db'

# Railway работает за HTTPS-прокси — без этого куки сессии не устанавливаются
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = 'Lax'

# ------------------------------------------------------------------ #
# Логирование                                                          #
# ------------------------------------------------------------------ #
LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': str(LOGS_DIR / 'admin_actions.log'),
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
