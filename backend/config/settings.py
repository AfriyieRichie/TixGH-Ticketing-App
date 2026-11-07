"""
Django settings for the TixGH backend.

All environment-specific values come from environment variables (or a local
`.env` file). See `.env.example` for the full list.
"""

import os
import sys
from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CORS_ALLOWED_ORIGINS=(list, ["http://localhost:3000"]),
)
environ.Env.read_env(BASE_DIR / ".env")

# Tests must never call real payment/SMS providers, whatever .env says.
TESTING = len(sys.argv) > 1 and sys.argv[1] == "test"

# --------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------
SECRET_KEY = env("SECRET_KEY", default="dev-insecure-change-me")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# Render sets these automatically for the deployed service.
RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_EXTERNAL_HOSTNAME}")

PLATFORM_NAME = env("PLATFORM_NAME", default="TixGH")
FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:3000")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "drf_spectacular",
    # Local
    "apps.core",
    "apps.accounts",
    "apps.organizations",
    "apps.events",
    "apps.orders",
    "apps.payments",
    "apps.tickets",
    "apps.notifications",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # serves admin CSS/JS in production
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# SQLite locally; set DATABASE_URL=postgres://... in staging/production.
DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")
}
if DATABASES["default"]["ENGINE"].endswith("postgresql"):
    DATABASES["default"]["CONN_MAX_AGE"] = 60
    DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = [
    "apps.accounts.backends.EmailOrPhoneBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Africa/Accra"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Uploaded images go to Cloudinary when CLOUDINARY_URL is set (free hosts like
# Render lose files saved on their own disk); otherwise to MEDIA_ROOT locally.
CLOUDINARY_URL = env("CLOUDINARY_URL", default="")
CLOUDINARY_FOLDER = env("CLOUDINARY_FOLDER", default="tixgh")
STORAGES = {
    "default": {
        "BACKEND": "apps.core.storage.CloudinaryMediaStorage"
        if CLOUDINARY_URL and not TESTING
        else "django.core.files.storage.FileSystemStorage"
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        if not DEBUG and not TESTING
        else "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "otp_request": env("THROTTLE_OTP_REQUEST", default="5/min"),
        "otp_verify": env("THROTTLE_OTP_VERIFY", default="10/min"),
        "login": env("THROTTLE_LOGIN", default="10/min"),
        "checkout": env("THROTTLE_CHECKOUT", default="20/min"),
        "resend": env("THROTTLE_RESEND", default="3/hour"),
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_ACCESS_MINUTES", default=30)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("JWT_REFRESH_DAYS", default=30)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
}

SPECTACULAR_SETTINGS = {
    "TITLE": f"{PLATFORM_NAME} API",
    "DESCRIPTION": "Event ticketing platform for Ghana.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "ENUM_NAME_OVERRIDES": {
        "EventStatusEnum": "apps.events.models.EventStatus",
        "OrderStatusEnum": "apps.orders.models.OrderStatus",
        "TicketStatusEnum": "apps.orders.models.TicketStatus",
        "VerificationStatusEnum": "apps.organizations.models.VerificationStatus",
    },
}

CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")

# --------------------------------------------------------------------------
# Checkout & payments
# --------------------------------------------------------------------------
BACKEND_URL = env("BACKEND_URL", default=RENDER_EXTERNAL_URL or "http://127.0.0.1:8000")
ORDER_HOLD_MINUTES = env.int("ORDER_HOLD_MINUTES", default=10)
# Where the gateway sends the buyer after paying (the web app's order page).
PAYMENT_CALLBACK_URL = env("PAYMENT_CALLBACK_URL", default=f"{FRONTEND_URL}/checkout/complete")
# PAYMENT_GATEWAY: "simulated" (no real money, for development) or "paystack".
PAYMENT_GATEWAY = "simulated" if TESTING else env("PAYMENT_GATEWAY", default="simulated")
PAYSTACK_SECRET_KEY = env("PAYSTACK_SECRET_KEY", default="")
PAYSTACK_PUBLIC_KEY = env("PAYSTACK_PUBLIC_KEY", default="")
# Paystack requires an email; phone-only buyers get <digits>@<this domain>.
PAYSTACK_FALLBACK_EMAIL_DOMAIN = env("PAYSTACK_FALLBACK_EMAIL_DOMAIN", default="customers.tixgh.com")

# --------------------------------------------------------------------------
# OTP
# --------------------------------------------------------------------------
OTP_LENGTH = 6
OTP_TTL_MINUTES = env.int("OTP_TTL_MINUTES", default=10)
OTP_MAX_ATTEMPTS = env.int("OTP_MAX_ATTEMPTS", default=5)
OTP_MAX_PER_HOUR = env.int("OTP_MAX_PER_HOUR", default=5)

# --------------------------------------------------------------------------
# Messaging (SMS + email)
# --------------------------------------------------------------------------
# SMS_BACKEND: "console" (prints to terminal), "arkesel" or "hubtel".
SMS_BACKEND = "console" if TESTING else env("SMS_BACKEND", default="console")
SMS_SENDER_ID = env("SMS_SENDER_ID", default="TixGH")  # max 11 chars
ARKESEL_API_KEY = env("ARKESEL_API_KEY", default="")
HUBTEL_CLIENT_ID = env("HUBTEL_CLIENT_ID", default="")
HUBTEL_CLIENT_SECRET = env("HUBTEL_CLIENT_SECRET", default="")

EMAIL_BACKEND = env(
    "EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default=f"{PLATFORM_NAME} <no-reply@tixgh.com>")
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=15)
# For EMAIL_BACKEND=apps.core.email_backends.BrevoAPIBackend (works where SMTP is blocked)
BREVO_API_KEY = env("BREVO_API_KEY", default="")
if not EMAIL_BACKEND.endswith("console.EmailBackend"):
    EMAIL_HOST = env("EMAIL_HOST", default="")
    EMAIL_PORT = env.int("EMAIL_PORT", default=587)
    EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
    EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
    EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)

# --------------------------------------------------------------------------
# Celery (background jobs). Runs tasks inline until Redis is configured.
# --------------------------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="memory://")
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=True)
CELERY_TIMEZONE = TIME_ZONE

# --------------------------------------------------------------------------
# Production hardening
# --------------------------------------------------------------------------
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=not TESTING)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SECURE_CONTENT_TYPE_NOSNIFF = True
    # Let the host's plain-HTTP health check through without a redirect.
    SECURE_REDIRECT_EXEMPT = [r"^api/v1/health/$"]

# Scheduled jobs (expire unpaid orders, reminders) can be triggered by an
# external scheduler calling /api/v1/internal/cron/ with this secret.
CRON_SECRET = env("CRON_SECRET", default="")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
}

CELERY_BEAT_SCHEDULE = {
    "expire-unpaid-orders": {"task": "apps.orders.tasks.expire_orders", "schedule": 60.0},
    "event-reminders": {"task": "apps.notifications.tasks.send_reminders", "schedule": 3600.0},
}

if TESTING:
    # Real hashing is deliberately slow; tests don't need that.
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
