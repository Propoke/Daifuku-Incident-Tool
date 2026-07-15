import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "insecure-dev-key-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "mozilla_django_oidc",
    "django_celery_beat",
    "core",
    "assets",
    "teams",
    "workorders",
    "maintenance",
    "inventory",
    "mobile_api",
    "reporting",
    "safety",
    "portal",
    "pwa",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "mozilla_django_oidc.middleware.SessionRefresh",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "cmms.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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

WSGI_APPLICATION = "cmms.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "cmms"),
        "USER": os.environ.get("POSTGRES_USER", "cmms"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "postgres"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Attachment uploads. Local disk for now - move to object storage (MinIO,
# already flagged in the infra plan) via django-storages once real volume
# shows up; not wired up yet since there's no MinIO instance to point at.
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Authentication ---
# Internal users authenticate via Entra ID (OIDC). Customer-portal users are
# a deliberately separate identity path (see docs/infrastructure-setup-plan.md)
# and will get their own auth backend when that module is built - not wired
# here yet.
AUTHENTICATION_BACKENDS = [
    "core.oidc.CMMSOIDCBackend",
    "django.contrib.auth.backends.ModelBackend",  # keeps /admin/ local login usable
]

LOGIN_URL = "/oidc/authenticate/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

OIDC_TENANT_ID = os.environ.get("OIDC_TENANT_ID", "")
OIDC_RP_CLIENT_ID = os.environ.get("OIDC_RP_CLIENT_ID", "")
OIDC_RP_CLIENT_SECRET = os.environ.get("OIDC_RP_CLIENT_SECRET", "")
OIDC_RP_SIGN_ALGO = "RS256"
OIDC_RP_SCOPES = "openid email profile"
OIDC_OP_AUTHORIZATION_ENDPOINT = (
    f"https://login.microsoftonline.com/{OIDC_TENANT_ID}/oauth2/v2.0/authorize"
)
OIDC_OP_TOKEN_ENDPOINT = f"https://login.microsoftonline.com/{OIDC_TENANT_ID}/oauth2/v2.0/token"
OIDC_OP_USER_ENDPOINT = "https://graph.microsoft.com/oidc/userinfo"
OIDC_OP_JWKS_ENDPOINT = (
    f"https://login.microsoftonline.com/{OIDC_TENANT_ID}/discovery/v2.0/keys"
)

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        # Interim mechanism for the mobile API (see docs/mobile-app-backlog.md)
        # so a client can be built/tested now. Production mobile auth should
        # move to Entra ID's mobile-native OAuth2/PKCE flow rather than
        # static tokens - not implemented yet.
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

# --- Email notifications (work order assignment, PM tickets, SLA/stock digest) ---
# Defaults to Django's console backend so this works with zero setup in
# dev/local iteration - point DJANGO_EMAIL_BACKEND at
# django.core.mail.backends.smtp.EmailBackend once a real relay is
# provisioned (this was flagged as never-provisioned in the CMMS audit).
EMAIL_BACKEND = os.environ.get("DJANGO_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "true").lower() == "true"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "cmms@localhost")

# Used to build links back into the app from notification emails. Falls
# back to CMMS_HOSTNAME (already used for the Traefik routing rule) so this
# doesn't need its own env var in the common case.
CMMS_BASE_URL = os.environ.get("CMMS_BASE_URL", f"https://{os.environ.get('CMMS_HOSTNAME', 'localhost')}")

# --- Celery / scheduled jobs (PM auto-ticketing) ---
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TIMEZONE = TIME_ZONE
# Schedule lives in the DB (django-celery-beat), editable via /admin/ rather
# than a hardcoded beat_schedule dict, matching the admin-editable pattern
# used elsewhere in this project.
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
