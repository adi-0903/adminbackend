from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from decouple import config

def health_check(request):
    """
    Health check endpoint that verifies all important environment variables are loaded
    """
    # Only show if superuser is checking
    is_superuser = request.user.is_superuser if request.user.is_authenticated else False
    
    status = {
        'status': 'healthy',
        'environment': settings.ENVIRONMENT,
        'debug': settings.DEBUG,
        'timezone': settings.TIME_ZONE,
    }
    
    # Only show detailed config status to superusers
    if is_superuser:
        status.update({
            'database': {
                'configured': 'default' in settings.DATABASES,
                'engine': settings.DATABASES['default']['ENGINE'] if 'default' in settings.DATABASES else None,
                'name': settings.DATABASES['default']['NAME'] if 'default' in settings.DATABASES else None,
            },
            'email': {
                'backend': settings.EMAIL_BACKEND,
                'host': settings.EMAIL_HOST,
                'port': settings.EMAIL_PORT,
                'tls': settings.EMAIL_USE_TLS,
            },
            'security': {
                'allowed_hosts': settings.ALLOWED_HOSTS,
                'ssl_redirect': settings.SECURE_SSL_REDIRECT,
                'session_cookie_secure': settings.SESSION_COOKIE_SECURE,
                'csrf_cookie_secure': settings.CSRF_COOKIE_SECURE,
            },
            'services': {
                'razorpay': bool(settings.RAZORPAY_KEY_ID),
                'sentry': bool(settings.SENTRY_DSN),
                'redis': bool(settings.REDIS_URL),
            },
            'maintenance': settings.MAINTENANCE_MODE,
        })
    
    return JsonResponse(status)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('user.urls')),
    path('api/collector/', include('collector.urls')),
    path('api/', include('wallet.urls')),
    path('api/admin/', include('admin_management.urls')),
    path('api/analytics/', include('analytics.urls')),
    path('api/health/', health_check, name='health_check'),
]

if settings.DEBUG:
    urlpatterns += [
        path('__debug__/', include('debug_toolbar.urls')),
    ]
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
