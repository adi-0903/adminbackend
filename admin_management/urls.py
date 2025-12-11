from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AdminDashboardView,
    AdminEnhancedDashboardView,
    AdminUserViewSet,
    AdminWalletViewSet,
    AdminWalletTransactionViewSet,
    AdminSimpleCollectionViewSet,
    AdminProRataCollectionViewSet,
    AdminCustomerViewSet,
    AdminLogViewSet,
    AdminNotificationViewSet,
    AdminReportViewSet,
    AdminReferralViewSet,
    AdminRawCollectionViewSet,
    AdminDairyInformationViewSet,
    AdminProfileView,
)

router = DefaultRouter()
router.register(r'users', AdminUserViewSet, basename='admin-users')
router.register(r'wallets', AdminWalletViewSet, basename='admin-wallets')
router.register(r'transactions', AdminWalletTransactionViewSet, basename='admin-transactions')
router.register(r'collections/simple', AdminSimpleCollectionViewSet, basename='admin-simple-collections')
router.register(r'collections/pro-rata', AdminProRataCollectionViewSet, basename='admin-pro-rata-collections')
router.register(r'collections/raw', AdminRawCollectionViewSet, basename='admin-raw-collections')
router.register(r'customers', AdminCustomerViewSet, basename='admin-customers')
router.register(r'logs', AdminLogViewSet, basename='admin-logs')
router.register(r'notifications', AdminNotificationViewSet, basename='admin-notifications')
router.register(r'reports', AdminReportViewSet, basename='admin-reports')
router.register(r'referrals', AdminReferralViewSet, basename='admin-referrals')
router.register(r'dairy-information', AdminDairyInformationViewSet, basename='admin-dairy-information')

urlpatterns = [
    path('dashboard/', AdminDashboardView.as_view(), name='admin-dashboard'),
    path('dashboard/enhanced/', AdminEnhancedDashboardView.as_view(), name='admin-enhanced-dashboard'),
    path('profile/', AdminProfileView.as_view(), name='admin-profile'),
    path('', include(router.urls)),
]
