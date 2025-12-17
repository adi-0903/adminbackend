from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UserAnalyticsViewSet, LiveDashboardViewSet
from .crm_views import InactiveUserTaskViewSet, TaskCommentViewSet

router = DefaultRouter()
router.register(r'user-analytics', UserAnalyticsViewSet, basename='useranalytics')
router.register(r'live-dashboard', LiveDashboardViewSet, basename='livedashboard')
router.register(r'crm-tasks', InactiveUserTaskViewSet, basename='crm-tasks')
router.register(r'task-comments', TaskCommentViewSet, basename='task-comments')

urlpatterns = [
    path('', include(router.urls)),
]
