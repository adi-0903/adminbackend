from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UserAnalyticsViewSet, LiveDashboardViewSet

router = DefaultRouter()
router.register(r'user-analytics', UserAnalyticsViewSet, basename='useranalytics')
router.register(r'live-dashboard', LiveDashboardViewSet, basename='livedashboard')

urlpatterns = [
    path('', include(router.urls)),
]
