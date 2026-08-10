"""
CyberTrust KSA - Django Settings
AI-Driven NCA Compliance Platform
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

from .env_checks import DEFAULT_SECRET_KEY, validate_secret_key, validate_allowed_hosts

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', DEFAULT_SECRET_KEY)
# Safe-by-default: DEBUG is OFF unless explicitly enabled via the environment.
DEBUG = os.getenv('DEBUG', 'False') == 'True'
# Explicit hostnames only in production (no wildcard default). Empty in DEBUG lets Django
# fall back to localhost; validated fail-closed below when DEBUG is off.
ALLOWED_HOSTS = [h.strip() for h in os.getenv('ALLOWED_HOSTS', '').split(',') if h.strip()]
# CSRF trusted origins (scheme + host), e.g. "https://app.example.sa". Empty by default
# so local development is unaffected; set via env for HTTPS deployments.
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.getenv('CSRF_TRUSTED_ORIGINS', '').split(',') if o.strip()]
TESTING = any(arg in {'test', 'pytest'} for arg in sys.argv[1:])
if TESTING:
    # The Django test client uses these hosts; keep tests independent of env config.
    ALLOWED_HOSTS = list(dict.fromkeys(ALLOWED_HOSTS + ['testserver', 'localhost', '127.0.0.1']))

# Fail-closed: refuse to boot in production with an unsafe secret key or host config.
validate_secret_key(SECRET_KEY, DEBUG, TESTING)
validate_allowed_hosts(ALLOWED_HOSTS, DEBUG, TESTING)

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'drf_spectacular',
    'corsheaders',
    'django_filters',
    'core',
    'compliance',
    'ai_engine',
    'dashboard',
    'auditor_portal',
    'monitoring',
    'api',
    'billing',
    'auditors',
    'risk',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.middleware.ContentSecurityPolicyMiddleware',
    'core.middleware.EnforceAdminMFAMiddleware',
    'core.middleware.AuditLogMiddleware',
]

ROOT_URLCONF = 'cybertrust_ksa.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.template.context_processors.i18n',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.notifications',
            ],
        },
    },
]

WSGI_APPLICATION = 'cybertrust_ksa.wsgi.application'

# Database: SQLite by default (local dev / tests). When POSTGRES_DB is provided
# (e.g. the Docker deployment), use PostgreSQL via the standard Django pattern.
# Additive and opt-in: with no POSTGRES_DB set, behavior is unchanged.
if os.getenv('POSTGRES_DB'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('POSTGRES_DB'),
            'USER': os.getenv('POSTGRES_USER', 'cybertrust'),
            'PASSWORD': os.getenv('POSTGRES_PASSWORD', ''),
            'HOST': os.getenv('POSTGRES_HOST', 'db'),
            'PORT': os.getenv('POSTGRES_PORT', '5432'),
            'CONN_MAX_AGE': int(os.getenv('DB_CONN_MAX_AGE', '60')),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_USER_MODEL = 'core.User'
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'ar'
TIME_ZONE = 'Asia/Riyadh'
USE_I18N = True
USE_TZ = True

LANGUAGES = [
    ('ar', 'العربية'),
    ('en', 'English'),
]
LOCALE_PATHS = [BASE_DIR / 'locale']

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    # Must define 'default' explicitly: when STORAGES is set, Django does not
    # backfill it, so FileField saves (evidence upload, FR-005) fail without it.
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}
if TESTING:
    # Tests run without `collectstatic`, so the manifest storage would raise
    # "Missing staticfiles manifest entry" on any {% static %}. Use the plain,
    # non-manifest backend so the suite is green from a clean venv.
    STORAGES['staticfiles'] = {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    }

# DD-fix (scalability): when an S3 bucket is configured, store evidence media on S3 so the
# app scales horizontally (uploads no longer live on one node's disk). Falls back to local
# FileSystemStorage otherwise. Requires django-storages + boto3 (in requirements).
AWS_STORAGE_BUCKET_NAME = os.getenv('AWS_STORAGE_BUCKET_NAME', '')
if AWS_STORAGE_BUCKET_NAME and not TESTING:
    AWS_S3_REGION_NAME = os.getenv('AWS_S3_REGION_NAME', 'me-central-1')  # KSA region by default (PDPL)
    AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID', '')
    AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY', '')
    AWS_S3_ENDPOINT_URL = os.getenv('AWS_S3_ENDPOINT_URL', '') or None
    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = True   # signed, expiring URLs — evidence never publicly listable
    STORAGES['default'] = {'BACKEND': 'storages.backends.s3.S3Storage'}

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# P0-01: sensitive uploads (evidence files, RFI attachments) are stored PRIVATELY — on S3
# they use signed/expiring URLs (above); on local disk they live OUTSIDE MEDIA_ROOT, in
# PRIVATE_MEDIA_ROOT, so the /media/ handler (dev static() or any reverse proxy) can never
# reach them. They are served ONLY through authenticated, tenant-scoped download views.
PRIVATE_MEDIA_ROOT = Path(os.getenv('PRIVATE_MEDIA_ROOT') or (BASE_DIR / 'private_media'))
# Optional nginx internal prefix for X-Accel-Redirect handoff in production. Empty (default)
# = stream through Django FileResponse. This deployment ships no reverse proxy, so it is off.
PRIVATE_MEDIA_XACCEL_PREFIX = os.getenv('PRIVATE_MEDIA_XACCEL_PREFIX', '').strip()

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
    ],
    # NFR-020: rate limiting.
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.UserRateThrottle',
        'rest_framework.throttling.AnonRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'user': '100/min',
        'anon': '20/min',
    },
    # DD-fix: paginate list endpoints (was unbounded — a 417-control company returned all).
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 25,
    # Auto-generated OpenAPI schema (drf-spectacular) for /api/v1/docs.
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

# OpenAPI / Swagger docs (drf-spectacular). Schema served at /api/v1/schema/,
# Swagger UI at /api/v1/docs/, ReDoc at /api/v1/redoc/.
SPECTACULAR_SETTINGS = {
    'TITLE': 'Cyber-5 API',
    'DESCRIPTION': 'CyberTrust KSA — نظام إدارة الامتثال السيبراني. REST API (SRS Appendix D).',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
}

CORS_ALLOW_ALL_ORIGINS = DEBUG

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o')
# Data sovereignty (PDPL / NCA data classification). Controls whether evidence/company
# text may leave the Kingdom for an external LLM:
#   disabled (default) — no evidence text is ever sent to an external AI; advisory results
#                        are produced locally/deferred to human review.
#   external           — explicit opt-in: text MAY be sent to the configured external LLM.
#   local              — reserved for an in-Kingdom LLM adapter (not yet wired → treated as
#                        disabled for external calls).
AI_DATA_RESIDENCY_MODE = os.getenv('AI_DATA_RESIDENCY_MODE', 'disabled').strip().lower()

CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_TASK_ALWAYS_EAGER = os.getenv('CELERY_TASK_ALWAYS_EAGER', 'False') == 'True'
# Evidence analysis dispatch. Default OFF: with no Celery worker/broker provisioned,
# calling .delay() would attempt a broker connection (and can hang) before the sync
# fallback. When off, uploads go straight to synchronous processing — deterministic,
# no broker round-trip. Set True only once a real worker+broker is running.
EVIDENCE_ASYNC_ENABLED = os.getenv('EVIDENCE_ASYNC_ENABLED', 'False') == 'True'

# Celery beat schedule (FR-010): continuous monitoring jobs.
from celery.schedules import crontab
CELERY_BEAT_SCHEDULE = {
    'daily-score-recalc': {
        'task': 'monitoring.tasks.recalculate_all_scores',
        'schedule': crontab(hour=1, minute=0),
    },
    'monthly-reports': {
        'task': 'monitoring.tasks.generate_monthly_reports',
        'schedule': crontab(day_of_month=1, hour=2, minute=0),
    },
    'daily-compliance-checks': {
        'task': 'monitoring.tasks.run_compliance_checks',
        'schedule': crontab(hour=3, minute=0),
    },
}

# ---- Email (FR-002.8 / FR-010.5 / FR-011.8 / FR-012.7) ----
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = os.getenv('EMAIL_HOST', '')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True') == 'True'
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'no-reply@cyber-5.com')
SITE_URL = os.getenv('SITE_URL', 'http://localhost:8000')

# ---- Payments / Moyasar (Phase 8I-B — sandbox checkout only) ----
# Publishable key is safe for the browser; the SECRET key stays server-side and
# is NEVER passed to templates. No live keys ship in code; defaults are empty.
PAYMENT_PROVIDER = os.getenv('PAYMENT_PROVIDER', 'manual')          # 'manual' | 'moyasar'
MOYASAR_MODE = os.getenv('MOYASAR_MODE', 'sandbox')                 # 'sandbox' | 'live'
MOYASAR_PUBLISHABLE_KEY = os.getenv('MOYASAR_PUBLISHABLE_KEY', '')  # pk_test_... in sandbox
MOYASAR_SECRET_KEY = os.getenv('MOYASAR_SECRET_KEY', '')            # server-side only (Phase 8I-C verify)
PUBLIC_BASE_URL = os.getenv('PUBLIC_BASE_URL', SITE_URL)
# Optional shared token echoed by Moyasar dashboard webhooks (Phase 8I-C). When set,
# the webhook rejects payloads whose secret_token/header does not match. When empty,
# security relies on server-side Fetch-Payment verification instead. Full HMAC header
# signature validation is deferred until Moyasar's exact header format is confirmed.
MOYASAR_WEBHOOK_SECRET = os.getenv('MOYASAR_WEBHOOK_SECRET', '')

# ---- Content Security Policy (NFR-017) ----
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdnjs.cloudflare.com; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
    "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
    "img-src 'self' data:; connect-src 'self'"
)

# ---- Production security hardening (active when DEBUG is off, but never in tests) ----
if not DEBUG and not TESTING:
    SECURE_SSL_REDIRECT = True
    # The container/LB liveness probe hits /healthz/ over plain HTTP; exempt only that
    # path from the HTTPS redirect so the healthcheck succeeds behind a TLS-terminating
    # proxy. All other routes are still force-redirected to HTTPS.
    SECURE_REDIRECT_EXEMPT = [r'^healthz/?$']
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    X_FRAME_OPTIONS = 'DENY'

# ---- Data retention / PDPL (NFR-045 / NFR-047 / NFR-048) ----
DATA_RETENTION_DAYS = {
    'audit_logs': int(os.getenv('RETAIN_AUDIT_LOGS_DAYS', '365')),
    'alerts': int(os.getenv('RETAIN_ALERTS_DAYS', '365')),
    'ai_logs': int(os.getenv('RETAIN_AI_LOGS_DAYS', '1825')),
    'verification_tokens': int(os.getenv('RETAIN_VERIFICATION_TOKENS_DAYS', '7')),
}

# Evidence files may be up to 50 MB (SRS FR-005.2 / NFR-006).
MAX_EVIDENCE_FILE_SIZE = 50 * 1024 * 1024
# Spool larger uploads to a temp file instead of memory.
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
# Whole request body cap; must exceed the largest allowed file.
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_EVIDENCE_FILE_SIZE + (5 * 1024 * 1024)
# Allowed evidence extensions (FR-005.1 / FR-005.11).
ALLOWED_EVIDENCE_EXTENSIONS = ['pdf', 'png', 'jpg', 'jpeg', 'tiff', 'bmp', 'docx', 'xlsx', 'txt', 'csv']

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ============================================================================
# DD-fix batch — ops / performance / security hardening
# ============================================================================

# ---- Cache (Redis in prod via REDIS_URL; safe local-memory fallback) --------
_REDIS_URL = os.getenv('REDIS_URL', '')
if _REDIS_URL and not TESTING:
    CACHES = {'default': {'BACKEND': 'django.core.cache.backends.redis.RedisCache',
                          'LOCATION': _REDIS_URL}}
else:
    CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
                          'LOCATION': 'cybertrust-local'}}

# ---- Session hardening (DD: explicit flags + bounded lifetime) --------------
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_HTTPONLY = False   # JS must read it for AJAX POSTs
SESSION_COOKIE_AGE = int(os.getenv('SESSION_COOKIE_AGE', str(60 * 60 * 12)))  # 12h default
SESSION_SAVE_EVERY_REQUEST = True   # sliding expiry on activity

# ---- Login brute-force throttle (DD: HTML /login/ had no protection) --------
# Cache-based lockout, no extra dependency. See core/login_throttle.py.
LOGIN_FAILURE_LIMIT = int(os.getenv('LOGIN_FAILURE_LIMIT', '8'))
LOGIN_FAILURE_WINDOW = int(os.getenv('LOGIN_FAILURE_WINDOW', '900'))   # 15 min

# ---- Enforce MFA for staff/admin (DD: MFA was optional). Opt-in via env so the
# default keeps existing sessions working; set True in production for privileged users.
ENFORCE_ADMIN_MFA = os.getenv('ENFORCE_ADMIN_MFA', 'False') == 'True'

# ---- Structured logging (DD: no LOGGING config existed) ---------------------
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {'format': '[{asctime}] {levelname} {name}: {message}', 'style': '{'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'standard'},
    },
    'root': {'handlers': ['console'], 'level': os.getenv('LOG_LEVEL', 'INFO')},
    'loggers': {
        'django.request': {'handlers': ['console'], 'level': 'ERROR', 'propagate': False},
        'cybertrust': {'handlers': ['console'], 'level': os.getenv('LOG_LEVEL', 'INFO'), 'propagate': False},
    },
}

# ---- Error tracking (DD: no monitoring). Active only if SENTRY_DSN set. ------
_SENTRY_DSN = os.getenv('SENTRY_DSN', '')
if _SENTRY_DSN and not DEBUG and not TESTING:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration
        sentry_sdk.init(dsn=_SENTRY_DSN, integrations=[DjangoIntegration()],
                        traces_sample_rate=float(os.getenv('SENTRY_TRACES_RATE', '0.1')),
                        send_default_pii=False, environment=os.getenv('SENTRY_ENV', 'production'))
    except Exception:
        pass   # never let telemetry wiring break boot
