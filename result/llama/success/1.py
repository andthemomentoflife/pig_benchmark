from django.core.exceptions import ImproperlyConfigured
from __future__ import unicode_literals, division, absolute_import, print_function
from pathlib import Path
import sys
import os
import datetime

env = os.environ.get
true_values = ["1", "true", "y", "yes", 1, True]


def require_env(name):
    value = env(name)
    if not value:
        raise ImproperlyConfigured("Missing {} env variable".format(name))
    return value


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ADMINS = (("Studentenportal Team", "team@studentenportal.ch"),)
MANAGERS = ADMINS
DEBUG = env("DJANGO_DEBUG", "True").lower() in true_values
DEBUG_TOOLBAR = env("DJANGO_DEBUG_TOOLBAR", "False").lower() in true_values
THUMBNAIL_DEBUG = DEBUG
COMPRESS_ENABLED = env("DJANGO_COMPRESS", str(not DEBUG)).lower() in true_values
TIME_ZONE = "Europe/Zurich"
LANGUAGE_CODE = "de-ch"
SITE_ID = 1
CSRF_COOKIE_HTTPONLY = True
if not DEBUG:
    ALLOWED_HOSTS = ["studentenportal.ch", "www.studentenportal.ch"]
    CSRF_COOKIE_SECURE = True
USE_I18N = True
USE_L10N = True
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql_psycopg2",
        "NAME": env("DB_NAME", "studentenportal"),
        "USER": env("DB_USER", "studentenportal"),
        "PASSWORD": env("DB_PASSWORD", "studentenportal"),
        "HOST": env("DB_HOST", "localhost"),
        "PORT": env("DB_PORT", ""),
    }
}
SECRET_KEY = env("SECRET_KEY", "DEBUG_SECRET_KEY")
if SECRET_KEY == "DEBUG_SECRET_KEY" and DEBUG is False:
    raise ImproperlyConfigured("Missing SECRET_KEY env variable")
MEDIA_ROOT = env("DJANGO_MEDIA_ROOT", str(PROJECT_ROOT / "media"))
MEDIA_URL = "/media/"
STATIC_ROOT = env("DJANGO_STATIC_ROOT", str(PROJECT_ROOT / "static"))
STATIC_URL = "/static/"
STATICFILES_DIRS = ()
STATICFILES_FINDERS = (
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
    "compressor.finders.CompressorFinder",
)
COMPRESS_CSS_FILTERS = [
    "compressor.filters.css_default.CssAbsoluteFilter",
    "compressor.filters.cssmin.CSSMinFilter",
]
COMPRESS_JS_FILTERS = ["compressor.filters.jsmin.JSMinFilter"]
COMPRESS_OFFLINE = not DEBUG
COMPRESS_PRECOMPILERS = (
    (
        "text/scss",
        "{} -mscss ".format(sys.executable)
        + ' --load-path "apps/front/static/sass/compass/compass/stylesheets" --load-path "apps/front/static/sass/compass/blueprint/stylesheets" -C -o {outfile} {infile}',
    ),
)
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.debug",
                "django.template.context_processors.i18n",
                "django.template.context_processors.media",
                "django.template.context_processors.static",
                "django.template.context_processors.tz",
                "django.contrib.messages.context_processors.messages",
                "apps.front.context_processors.global_stats",
                "apps.front.context_processors.debug",
            ]
        },
    }
]
MIDDLEWARE = []
if DEBUG_TOOLBAR:
    MIDDLEWARE.append("debug_toolbar.middleware.DebugToolbarMiddleware")
MIDDLEWARE += [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"
MAX_UPLOAD_SIZE = 1024 * 1024 * 20
AUTH_USER_MODEL = "front.User"
INSTALLED_APPS = (
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "compressor",
    "apps.tabs",
    "mathfilters",
    "easy_thumbnails",
    "rest_framework",
    "apps.front",
    "apps.documents",
    "apps.events",
    "apps.lecturers",
    "apps.tweets",
    "apps.api",
    "apps.user_stats",
    "messagegroups",
    "registration",
    "django.contrib.admin",
    "django.contrib.admindocs",
)
if DEBUG_TOOLBAR:
    INSTALLED_APPS += ("debug_toolbar",)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"require_debug_false": {"()": "django.utils.log.RequireDebugFalse"}},
    "handlers": {
        "console": {"level": "DEBUG", "class": "logging.StreamHandler"},
        "mail_admins": {
            "level": "ERROR",
            "filters": ["require_debug_false"],
            "class": "django.utils.log.AdminEmailHandler",
        },
    },
    "loggers": {
        "django.request": {
            "level": "WARNING",
            "handlers": ["console"],
            "propagate": False,
        },
        "django.db.backends": {
            "level": "ERROR",
            "handlers": ["console"],
            "propagate": False,
        },
    },
}
if not DEBUG:
    LOGGING["loggers"]["django.request"] = {
        "level": "WARNING",
        "handlers": ["mail_admins", "console"],
        "propagate": False,
    }
DEFAULT_FROM_EMAIL = "Studentenportal <noreply@studentenportal.ch>"
if DEBUG:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
else:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
if DEBUG:
    SENDFILE_BACKEND = "sendfile.backends.development"
else:
    SENDFILE_BACKEND = "sendfile.backends.nginx"
    SENDFILE_ROOT = os.path.join(MEDIA_ROOT, "documents")
    SENDFILE_URL = MEDIA_URL + "documents/"
LOGIN_REDIRECT_URL = "/"
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ),
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.BasicAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 20,
}
OAUTH_EXPIRE_DELTA = datetime.timedelta(days=90)
OAUTH_ENFORCE_SECURE = not DEBUG
REGISTRATION_OPEN = True
REGISTRATION_FORM = "apps.front.forms.HsrRegistrationForm"
REGISTRATION_EMAIL_HTML = False
ACCOUNT_ACTIVATION_DAYS = 7
GOOGLE_ANALYTICS_CODE = env("GOOGLE_ANALYTICS_CODE", None)


def show_debug_toolbar(request):
    return DEBUG_TOOLBAR


DEBUG_TOOLBAR_CONFIG = {
    "INTERCEPT_REDIRECTS": False,
    "SHOW_TOOLBAR_CALLBACK": "config.settings.show_debug_toolbar",
}
