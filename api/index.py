import os
import sys
from django.core.wsgi import get_wsgi_application

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Milk_Saas.settings')

application = get_wsgi_application()

def handler(request):
    """Vercel serverless handler"""
    return application(request.environ, lambda status, headers: None)
