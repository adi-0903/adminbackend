from pathlib import Path
import os
from datetime import timedelta
from corsheaders.defaults import default_headers
from decouple import config
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.redis import RedisIntegration
from sentry_sdk.integrations.celery import CeleryIntegration
import sys
import dj_database_url

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Environment settings
ENVIRONMENT = config('ENVIRONMENT', default='development')
IS_DEVELOPMENT = ENVIRONMENT == 'development'
IS_PRODUCTION = ENVIRONMENT == 'production'

# Time zone setting
TIME_ZONE = config('TIME_ZONE', default='Asia/Kolkata')
USE_TZ = True

# Sentry Configuration with Performance Monitoring
SENTRY_DSN = config('SENTRY_DSN', default=None)
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            DjangoIntegration(),
            RedisIntegration(),
            CeleryIntegration(),
        ],
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
        environment=ENVIRONMENT,
        send_default_pii=True,
        before_send=lambda event, hint: filter_sensitive_data(event),
    )

# Prometheus Metrics
PROMETHEUS_METRICS = {
    'DIRECTORY': '/tmp/prometheus',
    'MULTIPROCESS_MODE': 'all',
}

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('DJANGO_SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DJANGO_DEBUG', default=False, cast=bool)

# Allowed Hosts Configuration
ALLOWED_HOSTS = ['*']

# Use this setting to validate Host headers
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third party apps
    'rest_framework',
    'corsheaders',
    'django_filters',
    'drf_yasg',
    'cacheops',
    'debug_toolbar',
    'maintenance_mode',
    'django_celery_beat',  # For database-backed Celery schedule
    
    # Local apps
    'user',
    'collector',
    'wallet',
    'admin_management',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'debug_toolbar.middleware.DebugToolbarMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'maintenance_mode.middleware.MaintenanceModeMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# Debug Toolbar Configuration
if 'test' not in sys.argv and 'debug_toolbar' not in INSTALLED_APPS:  # Only install debug toolbar if not running tests
    INSTALLED_APPS.append('debug_toolbar')
    MIDDLEWARE.insert(0, 'debug_toolbar.middleware.DebugToolbarMiddleware')
    DEBUG_TOOLBAR_CONFIG = {
        'SHOW_TOOLBAR_CALLBACK': lambda request: True,
    }

ROOT_URLCONF = 'Milk_Saas.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': ['templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'Milk_Saas.wsgi.application'

# Database Configuration
database_url = config('DATABASE_URL', default=None)
if database_url:
    DATABASES = {
        'default': dj_database_url.config(
            default=database_url,
            conn_max_age=600,
            conn_health_checks=True,
            engine='django.db.backends.postgresql'
        )
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': config('DB_NAME'),
            'USER': config('DB_USER'),
            'PASSWORD': config('DB_PASSWORD'),
            'HOST': config('DB_HOST', default='localhost'),
            'PORT': config('DB_PORT', default='5432'),
            'CONN_MAX_AGE': 600
        }
    }

# Cache settings with Redis
REDIS_URL = config('REDIS_URL')

# Celery Configuration
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ['application/json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60
CELERY_WORKER_CONCURRENCY = 2
CELERY_WORKER_MAX_TASKS_PER_CHILD = 500  # Reduced from 1000 for better memory management
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BROKER_POOL_LIMIT = 10
CELERY_BROKER_HEARTBEAT = 10  # Seconds between broker heartbeats
CELERY_BROKER_CONNECTION_TIMEOUT = 30  # Connection timeout
CELERY_EVENT_QUEUE_EXPIRES = 60  # Task events queue expiry in seconds
CELERY_TASK_SEND_SENT_EVENT = True  # Enable events for better monitoring
CELERY_WORKER_HIJACK_ROOT_LOGGER = False  # Don't hijack root logger

# Celery Queue Configuration
CELERY_TASK_QUEUES = {
    'high_priority': {
        'exchange': 'high_priority',
        'routing_key': 'high_priority',
        'queue_arguments': {'x-max-priority': 10},
    },
    'default': {
        'exchange': 'default',
        'routing_key': 'default',
        'queue_arguments': {'x-max-priority': 5},
    },
    'low_priority': {
        'exchange': 'low_priority',
        'routing_key': 'low_priority',
        'queue_arguments': {'x-max-priority': 1},
    }
}

CELERY_TASK_ROUTES = {
    'wallet.tasks.*': {'queue': 'high_priority'},
    'collector.tasks.*': {'queue': 'default'},
    'user.tasks.*': {'queue': 'low_priority'},
}

# Better Celery Error Handling
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_CREATE_MISSING_QUEUES = True
CELERY_TASK_STORE_ERRORS_EVEN_IF_IGNORED = True
CELERY_TASK_RETRY_POLICY = {
    'max_retries': 5,
    'interval_start': 0,
    'interval_step': 0.2,
    'interval_max': 1.0,
}

# Multi-layer Cache Configuration with fallback
try:
    import redis
    redis_conn = redis.from_url(REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
    redis_conn.ping()
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': REDIS_URL,
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                'COMPRESSOR': 'django_redis.compressors.zlib.ZlibCompressor',
            }
        },
        'local': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'unique-snowflake',
            'OPTIONS': {
                'MAX_ENTRIES': 1000
            }
        }
    }
except Exception:
    # Fallback to local memory cache if Redis is unavailable
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'unique-snowflake',
            'OPTIONS': {
                'MAX_ENTRIES': 10000
            }
        },
        'local': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'unique-snowflake-local',
            'OPTIONS': {
                'MAX_ENTRIES': 1000
            }
        }
    }

# Cache Configuration for Different Types of Data
CACHE_MIDDLEWARE_SECONDS = 300  # 5 minutes
CACHE_MIDDLEWARE_KEY_PREFIX = 'milk_saas'

# Cacheops Configuration with fallback
try:
    import redis
    redis_conn = redis.from_url(REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
    redis_conn.ping()
    CACHEOPS_REDIS = REDIS_URL
    CACHEOPS_DEFAULTS = {
        'timeout': 60*60  # 1 hour
    }
    CACHEOPS = {
        'auth.*': {'ops': 'all', 'timeout': 60*60},
        'user.*': {'ops': ('fetch', 'get'), 'timeout': 60*15},
        'wallet.*': {
            'ops': 'all',
            'timeout': 60*5,  # 5 minutes
            'cache_on_save': True
        },
        'collector.*': {
            'ops': ('fetch', 'get'),
            'timeout': 60*30,  # 30 minutes
            'cache_on_save': True
        }
    }
except Exception as e:
    # Fallback: disable cacheops if Redis is unavailable
    CACHEOPS = {}
    CACHEOPS_DEFAULTS = {}
    CACHEOPS_REDIS = None

# Cache Invalidation Settings
CACHE_MACHINE_USE_REDIS = True
CACHE_MACHINE_REDIS_PARAMS = {
    'host': 'redis',
    'port': 6379,
    'db': 1,
}

# Static files configuration
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static')
] if os.path.exists(os.path.join(BASE_DIR, 'static')) else []

# Create static directory if it doesn't exist
if not os.path.exists(STATIC_ROOT):
    os.makedirs(STATIC_ROOT, exist_ok=True)

# Use WhiteNoise for static files
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Security Settings - Adjusted for Coolify
SECURE_SSL_REDIRECT = False  # Let Coolify handle SSL
SESSION_COOKIE_SECURE = False  # Set to False for now
CSRF_COOKIE_SECURE = False  # Set to False for now
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

if IS_PRODUCTION:
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
else:
    SECURE_HSTS_SECONDS = 0
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False

# Session Configuration
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'

# REST Framework settings
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle'
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': config('THROTTLE_RATE_ANON', default='100/hour'),
        'user': config('THROTTLE_RATE_USER', default='1000/hour')
    },
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
    ) if not DEBUG else (
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ),
    'EXCEPTION_HANDLER': 'Milk_Saas.utils.custom_exception_handler'
}

# JWT Settings
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=30),
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'TOKEN_TYPE_CLAIM': 'token_type',
    'JTI_CLAIM': 'jti',
    'TOKEN_USER_CLASS': 'rest_framework_simplejwt.models.TokenUser',
    # Add these settings
    'SLIDING_TOKEN_REFRESH_EXP_CLAIM': 'refresh_exp',
    'SLIDING_TOKEN_LIFETIME': timedelta(days=30),
    'SLIDING_TOKEN_REFRESH_LIFETIME': timedelta(days=1),
    # Blacklist settings
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': False,
}

# Logging Configuration - Simplified for console only
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
        'json': {
            'format': '{"time": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s", "module": "%(module)s"}',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        }
    },
    'handlers': {
        'console': {
            'level': 'DEBUG' if DEBUG else 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'json' if IS_PRODUCTION else 'simple',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': True,
        },
        'user': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': True,
        },
        'collector': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': True,
        },
        'wallet': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': True,
        },
        'admin': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}

# Email Configuration
EMAIL_BACKEND = config('EMAIL_BACKEND')
EMAIL_HOST = config('EMAIL_HOST')
EMAIL_PORT = config('EMAIL_PORT', cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', cast=bool)
EMAIL_USE_SSL = config('EMAIL_USE_SSL', cast=bool, default=False)
EMAIL_HOST_USER = config('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL')

# CORS Settings for React Native
CORS_ALLOW_ALL_ORIGINS = True if not IS_PRODUCTION else False

if IS_PRODUCTION:
    CORS_ALLOWED_ORIGINS = config(
        'CORS_ALLOWED_ORIGINS',
        default='',
        cast=lambda v: [s.strip() for s in v.split(',') if s.strip()]
    )

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]

CORS_ALLOW_HEADERS = list(default_headers) + [
    'x-request-id',
    'authorization',
    'content-type',
]

# Headers needed for React Native
CORS_EXPOSE_HEADERS = [
    'content-length',
    'content-type',
    'x-request-id',
]

# React Native Development Settings
if DEBUG:
    CORS_ALLOWED_ORIGIN_REGEXES = [
        r"^exp://.*$",  # Allow Expo development client
        r"^http://localhost:[0-9]+$",  # Allow localhost with any port
        r"^http://192\.168\.[0-9]{1,3}\.[0-9]{1,3}:[0-9]+$",  # Allow local IP addresses
    ]
    
    # Enable all hosts in development for React Native testing
    ALLOWED_HOSTS = ['*']

# File Upload Settings - Not needed for now
DATA_UPLOAD_MAX_MEMORY_SIZE = None
FILE_UPLOAD_MAX_MEMORY_SIZE = None
MAX_UPLOAD_SIZE = None

# Custom User Model
AUTH_USER_MODEL = 'user.User'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Razorpay Configuration
RAZORPAY_KEY_ID = config('RAZORPAY_KEY_ID')
RAZORPAY_KEY_SECRET = config('RAZORPAY_KEY_SECRET')
RAZORPAY_WEBHOOK_SECRET = config('RAZORPAY_WEBHOOK_SECRET', default=RAZORPAY_KEY_SECRET)

# Request Logging Configuration
REQUEST_LOGGING_ENABLE_COLORIZE = True
REQUEST_LOGGING_MAX_BODY_LENGTH = 1000
REQUEST_LOGGING_HTTP_4XX_LOG_LEVEL = 'INFO'

# Razorpay timeout settings
RAZORPAY_TIMEOUT = 30  # seconds
RAZORPAY_MAX_RETRIES = 3
RAZORPAY_RETRY_BACKOFF = 0.5

# Wallet Welcome Bonus Settings
WALLET_WELCOME_BONUS = {
    'ENABLED': True, 
    'AMOUNT': 500,  
    'DESCRIPTION': 'Welcome bonus for new registration'
}

# Collection Fee Deduction Settings
COLLECTION_FEE = {
    'ENABLED': True,
    'PER_KG_RATE': 0.024,
    'DESCRIPTION': 'Collection fee based on weight'
}

# Collection Edit Settings
COLLECTION_EDIT = {
    'MAX_EDIT_DAYS': 7,  
    'MAX_EDIT_COUNT': 2,
    'ENABLED': True, 
}

# Referral System Settings
REFERRAL_SETTINGS = {
    'ENABLED': True, 
    'REFERRER_CREDIT': 100.00,  
    'REFEREE_CREDIT': 50.00,  

    'MAX_REFERRAL_SYSTEM': True, 
    'MAX_REFERRAL_USES': 100000,  
    'MAX_REFEREE_USES': 1, 

    'REFERRER_DESCRIPTION': 'Referral bonus for referring a user',
    'REFEREE_DESCRIPTION': 'Bonus for using referral code'
}

# OTP Verification
USE_OTP_FOR_LOGIN = False
OTP_AUTH_TOKEN = config('OTP_AUTH_TOKEN')
OTP_CUSTOMER_ID = config('OTP_CUSTOMER_ID')

# Maintenance Mode
MAINTENANCE_MODE = config('MAINTENANCE_MODE', default=False, cast=bool)
MAINTENANCE_MODE_IGNORE_ADMIN_SITE = True
MAINTENANCE_MODE_IGNORE_SUPERUSER = True
MAINTENANCE_MODE_IGNORE_URLS = (
    r'^/admin/.*$',  # Don't show maintenance mode in admin
    r'^/api/health/$',  # Don't show maintenance mode for health checks
)
MAINTENANCE_MODE_STATUS_CODE = 503  # Service Unavailable
MAINTENANCE_MODE_TEMPLATE = '503.html'  # Template to show during maintenance
 
  
