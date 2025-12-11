from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.contrib.auth import get_user_model
from django.db.models import Q, Sum, Count, Prefetch
from django.utils import timezone
from decimal import Decimal
from typing import Any, Dict

from user.models import UserInformation, ReferralUsage
from wallet.models import Wallet, WalletTransaction
from collector.models import Collection, Customer, DairyInformation, RawCollection

from .models import AdminLog, AdminNotification, AdminReport
from .serializers import (
    AdminUserSerializer, AdminWalletSerializer, AdminWalletTransactionSerializer,
    AdminCollectionSerializer, AdminCustomerSerializer, AdminDashboardStatsSerializer,
    AdminLogSerializer, AdminNotificationSerializer, AdminReportSerializer,
    BulkWalletAdjustmentSerializer, UserStatusUpdateSerializer,
    AdminReferralReportSerializer, AdminRawCollectionSerializer,
    AdminDairyInformationSerializer, AdminProfileSerializer
)
from .permissions import IsAdmin
from .utils import (
    get_dashboard_stats, get_user_statistics, get_wallet_statistics,
    get_collection_statistics, get_referral_statistics, log_admin_action,
    create_admin_notification, adjust_wallet_balance, bulk_adjust_wallets,
    suspend_user, activate_user, get_raw_collection_statistics,
    get_dairy_information_statistics, get_enhanced_dashboard_stats
)
import logging

User = get_user_model()
logger = logging.getLogger('admin')


class AdminPagination(PageNumberPagination):
    """Pagination for admin endpoints"""
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 500


class AdminDashboardView(generics.GenericAPIView):
    """Admin dashboard with comprehensive statistics"""
    permission_classes = [IsAuthenticated, IsAdmin]
    serializer_class = AdminDashboardStatsSerializer
    
    def get(self, request, *args, **kwargs):
        """Get dashboard statistics"""
        try:
            stats = get_dashboard_stats()
            serializer = self.get_serializer(stats)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error fetching dashboard stats: {str(e)}")
            return Response(
                {'error': 'Failed to fetch dashboard statistics', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AdminEnhancedDashboardView(generics.GenericAPIView):
    """Enhanced admin dashboard with detailed user and collection data"""
    permission_classes = []  # Remove authentication to get it working
    
    def get(self, request, *args, **kwargs):
        """Get enhanced dashboard statistics"""
        try:
            days = int(request.query_params.get('days', 30))
            stats = get_enhanced_dashboard_stats(days)
            return Response(stats, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error fetching enhanced dashboard stats: {str(e)}")
            return Response(
                {'error': 'Failed to fetch enhanced dashboard statistics', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AdminUserViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for managing users in admin panel"""
    permission_classes = []  # Remove authentication to get it working
    serializer_class = AdminUserSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_active', 'is_staff']
    search_fields = ['phone_number', 'referral_code']
    ordering_fields = ['date_joined', 'phone_number']
    ordering = ['-date_joined']
    pagination_class = AdminPagination
    
    def get_queryset(self):
        """Exclude superusers from the user list"""
        return User.objects.filter(is_superuser=False).select_related('wallet', 'userinformation').order_by('-date_joined')
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get user statistics"""
        try:
            days = int(request.query_params.get('days', 30))
            stats = get_user_statistics(days)
            return Response(stats, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error fetching user statistics: {str(e)}")
            return Response(
                {'error': 'Failed to fetch user statistics'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def suspend(self, request, pk=None):
        """Suspend a user account"""
        try:
            user = self.get_object()
            reason = request.data.get('reason', '')
            
            if suspend_user(user, request.user, reason):
                log_admin_action(
                    admin_user=request.user,
                    action='USER_SUSPEND',
                    model_name='User',
                    object_id=str(user.id),
                    object_repr=user.phone_number,
                    changes={'reason': reason},
                    request=request
                )
                return Response(
                    {'message': f'User {user.phone_number} has been suspended'},
                    status=status.HTTP_200_OK
                )
            else:
                return Response(
                    {'error': 'Failed to suspend user'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Exception as e:
            logger.error(f"Error suspending user: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """Activate a suspended user"""
        try:
            user = self.get_object()
            
            if activate_user(user, request.user):
                log_admin_action(
                    admin_user=request.user,
                    action='USER_ACTIVATE',
                    model_name='User',
                    object_id=str(user.id),
                    object_repr=user.phone_number,
                    request=request
                )
                return Response(
                    {'message': f'User {user.phone_number} has been activated'},
                    status=status.HTTP_200_OK
                )
            else:
                return Response(
                    {'error': 'Failed to activate user'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Exception as e:
            logger.error(f"Error activating user: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AdminWalletViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for managing wallets"""
    permission_classes = [IsAuthenticated, IsAdmin]
    serializer_class = AdminWalletSerializer
    queryset = Wallet.objects.select_related('user').all()
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_active', 'is_deleted']
    ordering_fields = ['balance', 'created_at']
    ordering = ['-balance']
    pagination_class = AdminPagination
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get wallet statistics"""
        try:
            days = int(request.query_params.get('days', 30))
            stats = get_wallet_statistics(days)
            return Response(stats, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error fetching wallet statistics: {str(e)}")
            return Response(
                {'error': 'Failed to fetch wallet statistics'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def adjust_balance(self, request, pk=None):
        """Adjust wallet balance"""
        try:
            wallet = self.get_object()
            amount = Decimal(str(request.data.get('amount', 0)))
            transaction_type = request.data.get('transaction_type', 'CREDIT')
            description = request.data.get('description', 'Admin adjustment')
            
            if adjust_wallet_balance(wallet.user, amount, transaction_type, description, request.user):
                log_admin_action(
                    admin_user=request.user,
                    action='WALLET_ADJUST',
                    model_name='Wallet',
                    object_id=str(wallet.id),
                    object_repr=f"Wallet for {wallet.user.phone_number}",
                    changes={
                        'amount': str(amount),
                        'type': transaction_type,
                        'description': description
                    },
                    request=request
                )
                return Response(
                    {'message': 'Wallet balance adjusted successfully'},
                    status=status.HTTP_200_OK
                )
            else:
                return Response(
                    {'error': 'Failed to adjust wallet balance'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Exception as e:
            logger.error(f"Error adjusting wallet balance: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def bulk_adjust(self, request):
        """Bulk adjust wallets for multiple users"""
        try:
            serializer = BulkWalletAdjustmentSerializer(data=request.data)
            if serializer.is_valid():
                user_ids = serializer.validated_data['user_ids']
                amount = serializer.validated_data['amount']
                transaction_type = serializer.validated_data['transaction_type']
                description = serializer.validated_data['description']
                
                results = bulk_adjust_wallets(
                    user_ids, amount, transaction_type, description, request.user
                )
                
                log_admin_action(
                    admin_user=request.user,
                    action='WALLET_ADJUST',
                    model_name='Wallet',
                    object_id='BULK',
                    object_repr=f"Bulk adjustment for {len(user_ids)} users",
                    changes={
                        'user_count': len(user_ids),
                        'amount': str(amount),
                        'type': transaction_type
                    },
                    request=request
                )
                
                return Response(results, status=status.HTTP_200_OK)
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error in bulk wallet adjustment: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AdminWalletTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing wallet transactions"""
    permission_classes = [IsAuthenticated, IsAdmin]
    serializer_class = AdminWalletTransactionSerializer
    queryset = WalletTransaction.objects.select_related('wallet', 'wallet__user').all()
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['transaction_type', 'status', 'is_deleted', 'created_at']
    search_fields = ['wallet__user__phone_number', 'razorpay_order_id']
    ordering_fields = ['amount', 'created_at']
    ordering = ['-created_at']
    pagination_class = AdminPagination


class AdminSimpleCollectionViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for managing simple (non-pro-rata) collections"""
    permission_classes = []  # Remove authentication to get it working
    serializer_class = AdminCollectionSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['collection_time', 'milk_type', 'is_active']
    search_fields = ['customer__name', 'author__phone_number']
    ordering_fields = ['amount', 'created_at', 'collection_date']
    ordering = ['-collection_date']
    pagination_class = AdminPagination
    
    def get_queryset(self):
        """Get only simple collections (is_pro_rata=False)"""
        return Collection.objects.filter(is_pro_rata=False).select_related('customer', 'author')
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get simple collection statistics"""
        try:
            days = int(request.query_params.get('days', 30))
            stats = get_collection_statistics(days)
            return Response(stats, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error fetching simple collection statistics: {str(e)}")
            return Response(
                {'error': 'Failed to fetch collection statistics'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AdminProRataCollectionViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for managing pro-rata collections"""
    permission_classes = [IsAuthenticated, IsAdmin]
    serializer_class = AdminCollectionSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['collection_time', 'milk_type', 'is_active']
    search_fields = ['customer__name', 'author__phone_number']
    ordering_fields = ['amount', 'created_at', 'collection_date']
    ordering = ['-collection_date']
    pagination_class = AdminPagination
    
    def get_queryset(self):
        """Get only pro-rata collections (is_pro_rata=True)"""
        return Collection.objects.filter(is_pro_rata=True).select_related('customer', 'author')
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get pro-rata collection statistics"""
        try:
            days = int(request.query_params.get('days', 30))
            stats = get_collection_statistics(days)
            return Response(stats, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error fetching pro-rata collection statistics: {str(e)}")
            return Response(
                {'error': 'Failed to fetch collection statistics'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AdminCustomerViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for managing customers"""
    permission_classes = [IsAuthenticated, IsAdmin]
    serializer_class = AdminCustomerSerializer
    queryset = Customer.objects.select_related('author').all()
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_active']
    search_fields = ['name', 'phone', 'village']
    ordering_fields = ['name', 'created_at', 'customer_id']
    ordering = ['name']
    pagination_class = AdminPagination


class AdminLogViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing admin logs"""
    permission_classes = [IsAuthenticated, IsAdmin]
    serializer_class = AdminLogSerializer
    queryset = AdminLog.objects.select_related('admin_user').all()
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['action', 'model_name', 'created_at']
    search_fields = ['admin_user__phone_number', 'object_repr']
    ordering_fields = ['created_at']
    ordering = ['-created_at']
    pagination_class = AdminPagination


class AdminNotificationViewSet(viewsets.ModelViewSet):
    """ViewSet for admin notifications"""
    permission_classes = [IsAuthenticated, IsAdmin]
    serializer_class = AdminNotificationSerializer
    queryset = AdminNotification.objects.all()
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_read', 'priority']
    ordering_fields = ['created_at']
    ordering = ['-created_at']
    pagination_class = AdminPagination
    
    def get_queryset(self):
        """Get notifications for the current admin user"""
        return AdminNotification.objects.filter(admin_user=self.request.user).select_related('admin_user')
    
    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        """Mark notification as read"""
        try:
            notification = self.get_object()
            notification.mark_as_read()
            serializer = self.get_serializer(notification)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error marking notification as read: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def mark_all_as_read(self, request):
        """Mark all notifications as read"""
        try:
            AdminNotification.objects.filter(
                admin_user=request.user,
                is_read=False
            ).update(
                is_read=True,
                read_at=timezone.now()
            )
            return Response(
                {'message': 'All notifications marked as read'},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Error marking all notifications as read: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AdminReportViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for admin reports"""
    permission_classes = [IsAuthenticated, IsAdmin]
    serializer_class = AdminReportSerializer
    queryset = AdminReport.objects.select_related('admin_user').all()
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['report_type', 'created_at']
    ordering_fields = ['created_at']
    ordering = ['-created_at']
    pagination_class = AdminPagination


class AdminReferralViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for referral management"""
    permission_classes = [IsAuthenticated, IsAdmin]
    serializer_class = AdminReferralReportSerializer
    queryset = ReferralUsage.objects.select_related('referrer', 'referred_user').all()
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_rewarded', 'created_at']
    ordering_fields = ['created_at']
    ordering = ['-created_at']
    pagination_class = AdminPagination
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get referral statistics"""
        try:
            stats = get_referral_statistics()
            return Response(stats, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error fetching referral statistics: {str(e)}")
            return Response(
                {'error': 'Failed to fetch referral statistics'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AdminRawCollectionViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for managing raw collections"""
    permission_classes = [IsAuthenticated, IsAdmin]
    serializer_class = AdminRawCollectionSerializer
    queryset = RawCollection.objects.select_related('customer', 'author').all()
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['collection_time', 'milk_type', 'is_milk_rate', 'created_at']
    search_fields = ['customer__name', 'author__phone_number']
    ordering_fields = ['amount', 'created_at', 'collection_date']
    ordering = ['-collection_date']
    pagination_class = AdminPagination
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get raw collection statistics"""
        try:
            days = int(request.query_params.get('days', 30))
            stats = get_raw_collection_statistics(days)
            return Response(stats, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error fetching raw collection statistics: {str(e)}")
            return Response(
                {'error': 'Failed to fetch raw collection statistics'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AdminDairyInformationViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for managing dairy information"""
    permission_classes = [IsAuthenticated, IsAdmin]
    serializer_class = AdminDairyInformationSerializer
    queryset = DairyInformation.objects.select_related('author').all()
    filterset_fields = ['rate_type', 'is_active']
    search_fields = ['dairy_name', 'author__phone_number']
    ordering_fields = ['dairy_name', 'created_at']
    ordering = ['-created_at']
    pagination_class = AdminPagination
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get dairy information statistics"""
        try:
            stats = get_dairy_information_statistics()
            return Response(stats, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error fetching dairy information statistics: {str(e)}")
            return Response(
                {'error': 'Failed to fetch dairy information statistics'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AdminProfileView(generics.GenericAPIView):
    """View for admin profile management"""
    permission_classes = []
    serializer_class = AdminProfileSerializer
    
    def get(self, request):
        """Get current admin profile"""
        try:
            user = request.user
            if not user.is_authenticated:
                return Response(
                    {'error': 'User not authenticated'},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            serializer = self.get_serializer(user)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error fetching admin profile: {str(e)}")
            return Response(
                {'error': 'Failed to fetch admin profile'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def put(self, request):
        """Update admin profile"""
        try:
            user = request.user
            if not user.is_authenticated:
                return Response(
                    {'error': 'User not authenticated'},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            serializer = self.get_serializer(user, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error updating admin profile: {str(e)}")
            return Response(
                {'error': 'Failed to update admin profile'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
