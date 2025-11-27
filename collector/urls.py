from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CollectionViewSet, CustomerViewSet,
    MarketMilkPriceViewSet, DairyInformationViewSet,
    RawCollectionViewSet
)
from .pro_rata_report_generation_views import ProRataReportViewSet
from .youtube_channel_views import YouTubeLinkViewSet

router = DefaultRouter()
router.register(r'collections', CollectionViewSet, basename='collection')
router.register(r'customers', CustomerViewSet, basename='customer')
router.register(r'market-milk-prices', MarketMilkPriceViewSet, basename='market-milk-price')
router.register(r'dairy-information', DairyInformationViewSet, basename='dairy-information')
router.register(r'raw-collections', RawCollectionViewSet, basename='raw-collection')
router.register(r'pro-rata-reports', ProRataReportViewSet, basename='pro-rata-report')
router.register(r'youtube-link',YouTubeLinkViewSet, basename='youtube-link')

urlpatterns = [
    path('', include(router.urls)),
] 