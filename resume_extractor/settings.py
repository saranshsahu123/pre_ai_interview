"""
Django settings for resume_extractor project.
"""

from pathlib import Path
import os
from dotenv import load_dotenv


load_dotenv()  # Load .env file


# Base Directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Temporary upload directory (for resume processing only)
TEMP_UPLOAD_DIR = BASE_DIR / "temp_uploads"
if not os.path.exists(TEMP_UPLOAD_DIR):
    os.makedirs(TEMP_UPLOAD_DIR)


SECRET_KEY = 'django-insecure-skp#=3_myojphsm%)k9307_xk%ss*s#tlhm0_q&kci5l)1%w&9'
DEBUG = True
ALLOWED_HOSTS = []

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")



INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'resume',
]


MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]


ROOT_URLCONF = 'resume_extractor.urls'


TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',

        # make sure your folder is named "template" exactly
        'DIRS': [BASE_DIR / "templates"],

        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]


WSGI_APPLICATION = 'resume_extractor.wsgi.application'


# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True


# STATIC FILES
STATIC_URL = '/static/'
# Remove STATICFILES_DIRS if static folder does not exist
# STATICFILES_DIRS = [BASE_DIR / "static"]


# MEDIA (only for extracted profile images)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / "media"

if not os.path.exists(MEDIA_ROOT):
    os.makedirs(MEDIA_ROOT)


DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
