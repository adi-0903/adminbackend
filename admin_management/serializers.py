from rest_framework import serializers
from django.contrib.auth import get_user_model
from user.models import UserInformation, ReferralUsage
from wallet.models import Wallet, WalletTransaction
from collector.models import Collection, Customer, DairyInformation, RawCollection
from .models import AdminLog, AdminNotification, AdminReport
from decimal import Decimal
from typing import Any, Dict
from django.db.models import Count

# Import tracking serializer for device info
try:
    from tracking.serializers import DeviceInfoSerializer
except ImportError:
    DeviceInfoSerializer = None

# Import DairyInformation for supplier info
from collector.models import DairyInformation

User = get_user_model()


class AdminUserSerializer(serializers.ModelSerializer):
    """Serializer for user information in admin panel"""
    user_info = serializers.SerializerMethodField()
    wallet = serializers.SerializerMethodField()
    total_collections = serializers.SerializerMethodField()
    total_spent = serializers.SerializerMethodField()
    referral_count = serializers.SerializerMethodField()
    device_info = serializers.SerializerMethodField()
    supplier_info = serializers.SerializerMethodField()
    collections_this_month = serializers.SerializerMethodField()
    revenue_this_month = serializers.SerializerMethodField()
    premium_purchases = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'phone_number', 'referral_code', 'is_active', 'is_staff',
            'date_joined', 'last_active', 'last_login', 'login_count', 'total_sessions',
            'user_info', 'wallet', 'total_collections', 'total_spent', 'referral_count', 'device_info', 'supplier_info',
            'collections_this_month', 'revenue_this_month', 'premium_purchases'
        ]
        read_only_fields = ['id', 'phone_number', 'referral_code', 'date_joined', 'last_active', 'last_login', 'login_count', 'total_sessions']
    
    def get_user_info(self, obj):
        try:
            user_info = UserInformation.objects.get(user=obj)
            return {
                'name': user_info.name,
                'email': user_info.email,
                'is_active': user_info.is_active
            }
        except UserInformation.DoesNotExist:
            return None
    
    def get_wallet(self, obj):
        try:
            wallet = Wallet.objects.get(user=obj)
            return {
                'balance': str(wallet.balance),
                'is_active': wallet.is_active,
                'created_at': wallet.created_at,
                'updated_at': wallet.updated_at
            }
        except Wallet.DoesNotExist:
            return None
    
    def get_total_collections(self, obj):
        try:
            # Count all collections for this user (both active and inactive)
            count = Collection.objects.filter(author=obj).count()
            return count
        except Exception as e:
            print(f"Error counting collections for user {obj.id}: {e}")
            return 0
    
    def get_referral_count(self, obj):
        try:
            return ReferralUsage.objects.filter(referrer=obj, is_rewarded=True).count()
        except Exception:
            return 0
    
    def get_total_spent(self, obj):
        """Calculate total spent by user from collections"""
        try:
            from django.db.models import Sum
            from decimal import Decimal
            total = Collection.objects.filter(author=obj).aggregate(
                total=Sum('amount')
            )['total'] or Decimal('0')
            return float(total)
        except Exception:
            return 0
    
    def get_device_info(self, obj):
        """Get device info from tracking app"""
        try:
            if hasattr(obj, 'device_info'):
                if DeviceInfoSerializer:
                    return DeviceInfoSerializer(obj.device_info).data
                else:
                    return {
                        'device_type': obj.device_info.device_type,
                        'platform': obj.device_info.platform,
                        'app_version': obj.device_info.app_version,
                        'os_version': obj.device_info.os_version,
                        'device_model': obj.device_info.device_model,
                        'last_device_used': obj.device_info.last_device_used,
                        'last_seen': obj.device_info.last_seen,
                    }
        except Exception:
            return None
    
    def get_supplier_info(self, obj):
        """Get supplier/dairy information"""
        try:
            dairy_info = DairyInformation.objects.filter(
                author=obj,
                is_active=True
            ).order_by('-created_at').first()
            
            if dairy_info:
                return {
                    'dairy_name': dairy_info.dairy_name,
                    'dairy_address': dairy_info.dairy_address,
                    'rate_type': dairy_info.rate_type,
                    'is_active': dairy_info.is_active,
                    'created_at': dairy_info.created_at,
                    'updated_at': dairy_info.updated_at,
                }
        except Exception:
            pass
        return None
    
    def get_collections_this_month(self, obj):
        """Calculate collections for current month"""
        try:
            from django.utils import timezone
            current_month_start = timezone.now().date().replace(day=1)
            count = Collection.objects.filter(
                author=obj,
                is_active=True,
                collection_date__gte=current_month_start
            ).count()
            return count
        except Exception:
            return 0
    
    def get_revenue_this_month(self, obj):
        """Calculate revenue for current month"""
        try:
            from django.utils import timezone
            from django.db.models import Sum
            from decimal import Decimal
            current_month_start = timezone.now().date().replace(day=1)
            total = Collection.objects.filter(
                author=obj,
                is_active=True,
                collection_date__gte=current_month_start
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
            return float(total)
        except Exception:
            return 0
    
    def get_premium_purchases(self, obj):
        """Fetch premium purchases from wallet transactions"""
        try:
            # Get wallet for this user
            wallet = Wallet.objects.get(user=obj)
            # Fetch premium-related transactions (DEBIT transactions with 'premium' in description)
            premium_transactions = WalletTransaction.objects.filter(
                wallet=wallet,
                transaction_type='DEBIT',
                description__icontains='premium',
                status='SUCCESS'
            ).order_by('-created_at')
            
            purchases = []
            for transaction in premium_transactions:
                purchases.append({
                    'plan_name': 'Premium Plan',
                    'amount': float(transaction.amount),
                    'start_date': transaction.created_at.date(),
                    'end_date': None,  # Would need a separate model to track end dates
                    'status': 'active',
                    'features': transaction.description
                })
            
            return purchases
        except Wallet.DoesNotExist:
            return []
        except Exception:
            return []


class AdminWalletSerializer(serializers.ModelSerializer):
    """Serializer for wallet management"""
    user_phone = serializers.CharField(source='user.phone_number', read_only=True)
    user_id = serializers.IntegerField(source='user.id', read_only=True)
    
    class Meta:
        model = Wallet
        fields = [
            'id', 'user_id', 'user_phone', 'balance', 'is_active', 'is_deleted',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'user_id', 'user_phone', 'created_at', 'updated_at']


class AdminWalletTransactionSerializer(serializers.ModelSerializer):
    """Serializer for wallet transactions"""
    user_phone = serializers.CharField(source='wallet.user.phone_number', read_only=True)
    wallet_id = serializers.IntegerField(source='wallet.id', read_only=True)
    
    class Meta:
        model = WalletTransaction
        fields = [
            'id', 'wallet_id', 'user_phone', 'amount', 'transaction_type', 'status',
            'razorpay_order_id', 'razorpay_payment_id', 'description',
            'created_at', 'updated_at', 'is_deleted'
        ]
        read_only_fields = ['id', 'wallet_id', 'user_phone', 'created_at', 'updated_at']


class AdminCollectionSerializer(serializers.ModelSerializer):
    """Serializer for collection management"""
    author_phone = serializers.CharField(source='author.phone_number', read_only=True)
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    
    class Meta:
        model = Collection
        fields = [
            'id', 'author_phone', 'customer_name', 'collection_date', 'collection_time',
            'milk_type', 'measured', 'liters', 'kg', 'fat_percentage', 'snf_percentage',
            'amount', 'milk_rate', 'is_active', 'created_at', 'updated_at', 'edit_count'
        ]
        read_only_fields = ['id', 'author_phone', 'customer_name', 'created_at', 'updated_at']


class AdminCustomerSerializer(serializers.ModelSerializer):
    """Serializer for customer management"""
    author_phone = serializers.CharField(source='author.phone_number', read_only=True)
    total_collections = serializers.SerializerMethodField()
    
    class Meta:
        model = Customer
        fields = [
            'id', 'author_phone', 'customer_id', 'name', 'father_name', 'phone',
            'village', 'address', 'is_active', 'created_at', 'updated_at',
            'total_collections'
        ]
        read_only_fields = ['id', 'author_phone', 'customer_id', 'created_at', 'updated_at']
    
    def get_total_collections(self, obj):
        return Collection.objects.filter(customer=obj, is_active=True).count()


class AdminDashboardStatsSerializer(serializers.Serializer):
    """Serializer for dashboard statistics"""
    total_users = serializers.IntegerField()
    active_users = serializers.IntegerField()
    total_wallet_balance = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_transactions = serializers.IntegerField()
    total_collections = serializers.IntegerField()
    new_collections_this_month = serializers.IntegerField()
    new_users_this_month = serializers.IntegerField()
    total_customers = serializers.IntegerField()
    pending_transactions = serializers.IntegerField()
    failed_transactions = serializers.IntegerField()
    referral_count = serializers.IntegerField()
    total_amount_earned = serializers.DecimalField(max_digits=15, decimal_places=2)


class AdminLogSerializer(serializers.ModelSerializer):
    """Serializer for admin logs"""
    admin_phone = serializers.CharField(source='admin_user.phone_number', read_only=True)
    
    class Meta:
        model = AdminLog
        fields = [
            'id', 'admin_phone', 'action', 'model_name', 'object_id', 'object_repr',
            'changes', 'ip_address', 'created_at'
        ]
        read_only_fields = ['id', 'admin_phone', 'created_at']


class AdminNotificationSerializer(serializers.ModelSerializer):
    """Serializer for admin notifications"""
    
    class Meta:
        model = AdminNotification
        fields = [
            'id', 'title', 'message', 'priority', 'is_read', 'related_model',
            'related_object_id', 'created_at', 'read_at'
        ]
        read_only_fields = ['id', 'created_at', 'read_at']


class AdminReportSerializer(serializers.ModelSerializer):
    """Serializer for admin reports"""
    admin_phone = serializers.CharField(source='admin_user.phone_number', read_only=True)
    
    class Meta:
        model = AdminReport
        fields = [
            'id', 'admin_phone', 'report_type', 'title', 'description', 'data',
            'filters', 'created_at'
        ]
        read_only_fields = ['id', 'admin_phone', 'created_at']


class BulkWalletAdjustmentSerializer(serializers.Serializer):
    """Serializer for bulk wallet adjustments"""
    user_ids = serializers.ListField(child=serializers.IntegerField())
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    transaction_type = serializers.ChoiceField(choices=['CREDIT', 'DEBIT'])
    description = serializers.CharField(max_length=255)
    
    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than 0")
        return value


class UserStatusUpdateSerializer(serializers.Serializer):
    """Serializer for updating user status"""
    user_id = serializers.IntegerField()
    is_active = serializers.BooleanField()
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True)


class AdminReferralReportSerializer(serializers.ModelSerializer):
    """Serializer for referral reports"""
    referrer_phone = serializers.CharField(source='referrer.phone_number', read_only=True)
    referred_user_phone = serializers.CharField(source='referred_user.phone_number', read_only=True)
    
    class Meta:
        model = ReferralUsage
        fields = [
            'id', 'referrer_phone', 'referred_user_phone', 'created_at', 'is_rewarded'
        ]
        read_only_fields = ['id', 'referrer_phone', 'referred_user_phone', 'created_at']


class AdminRawCollectionSerializer(serializers.ModelSerializer):
    """Serializer for raw collection management"""
    author_phone = serializers.CharField(source='author.phone_number', read_only=True)
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    
    class Meta:
        model = RawCollection
        fields = [
            'id', 'author_phone', 'customer_name', 'collection_date', 'collection_time',
            'milk_type', 'measured', 'liters', 'kg', 'fat_percentage', 'snf_percentage',
            'amount', 'milk_rate', 'is_milk_rate', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'author_phone', 'customer_name', 'created_at', 'updated_at']


class AdminDairyInformationSerializer(serializers.ModelSerializer):
    """Serializer for dairy information management"""
    author_phone = serializers.CharField(source='author.phone_number', read_only=True)
    
    class Meta:
        model = DairyInformation
        fields = [
            'id', 'author_phone', 'dairy_name', 'dairy_address', 'rate_type',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'author_phone', 'created_at', 'updated_at']


class AdminProfileSerializer(serializers.ModelSerializer):
    """Serializer for admin profile management"""
    user_info = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'phone_number', 'is_active', 'date_joined', 'user_info'
        ]
        read_only_fields = ['id', 'phone_number', 'is_active', 'date_joined']
    
    def get_user_info(self, obj):
        try:
            user_info = UserInformation.objects.get(user=obj)
            return {
                'name': user_info.name,
                'email': user_info.email,
            }
        except UserInformation.DoesNotExist:
            return {'name': '', 'email': ''}
    
    def update(self, instance, validated_data):
        try:
            user_info = UserInformation.objects.get(user=instance)
            user_info.name = validated_data.get('name', user_info.name)
            user_info.email = validated_data.get('email', user_info.email)
            user_info.save()
        except UserInformation.DoesNotExist:
            UserInformation.objects.create(
                user=instance,
                name=validated_data.get('name', ''),
                email=validated_data.get('email', '')
            )
        return instance
