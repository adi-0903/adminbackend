from rest_framework import serializers
from .models import UserSegment, DailyMetrics, SystemMetrics, AnalyticsQuery
from user.models import User
from django.utils import timezone
from datetime import timedelta


class UserSegmentSerializer(serializers.ModelSerializer):
    user_count = serializers.ReadOnlyField()
    
    class Meta:
        model = UserSegment
        fields = ['id', 'name', 'segment_type', 'description', 'criteria', 'user_count', 'created_at', 'updated_at', 'is_active']
        read_only_fields = ['user_count', 'created_at', 'updated_at']


class InactiveUserSerializer(serializers.Serializer):
    """Serializer for inactive users data"""
    id = serializers.IntegerField()
    phone_number = serializers.CharField()
    name = serializers.CharField(allow_null=True)
    email = serializers.EmailField(allow_null=True)
    date_joined = serializers.DateTimeField()
    last_login = serializers.DateTimeField(allow_null=True)
    last_active = serializers.DateTimeField(allow_null=True)
    login_count = serializers.IntegerField()
    total_sessions = serializers.IntegerField()
    days_inactive = serializers.IntegerField()
    reason = serializers.CharField()


class UserAnalyticsSerializer(serializers.Serializer):
    """Serializer for user analytics data"""
    total_users = serializers.IntegerField()
    active_users = serializers.IntegerField()
    inactive_users = serializers.IntegerField()
    new_users_today = serializers.IntegerField()
    new_users_week = serializers.IntegerField()
    new_users_month = serializers.IntegerField()
    churn_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    retention_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    avg_session_duration = serializers.DecimalField(max_digits=8, decimal_places=2)
    top_active_users = serializers.ListField(
        child=serializers.DictField()
    )


class DailyMetricsSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyMetrics
        fields = ['id', 'date', 'total_users', 'active_users', 'new_users', 'inactive_users', 
                 'total_collections', 'total_revenue', 'avg_session_duration', 'created_at']


class SystemMetricsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemMetrics
        fields = ['id', 'timestamp', 'cpu_usage', 'memory_usage', 'disk_usage', 
                 'active_connections', 'response_time', 'error_rate']


class LiveMetricsSerializer(serializers.Serializer):
    """Serializer for live dashboard metrics"""
    current_online_users = serializers.IntegerField()
    today_collections = serializers.IntegerField()
    today_revenue = serializers.FloatField()
    active_sessions = serializers.IntegerField()
    system_health = serializers.DictField()
    recent_activities = serializers.ListField(
        child=serializers.DictField()
    )


class CollectionAnalyticsSerializer(serializers.Serializer):
    """Serializer for collection analytics"""
    total_collections_today = serializers.IntegerField()
    total_collections_week = serializers.IntegerField()
    total_collections_month = serializers.IntegerField()
    avg_collection_per_user = serializers.DecimalField(max_digits=8, decimal_places=2)
    peak_collection_hours = serializers.ListField(
        child=serializers.IntegerField()
    )
    collection_trends = serializers.ListField(
        child=serializers.DictField()
    )
    quality_metrics = serializers.DictField()


class FinancialAnalyticsSerializer(serializers.Serializer):
    """Serializer for financial analytics"""
    total_revenue_today = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_revenue_week = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_revenue_month = serializers.DecimalField(max_digits=15, decimal_places=2)
    avg_transaction_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    payment_methods = serializers.DictField()
    revenue_trends = serializers.ListField(
        child=serializers.DictField()
    )
    top_earners = serializers.ListField(
        child=serializers.DictField()
    )


class AnalyticsQuerySerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.phone_number', read_only=True)
    
    class Meta:
        model = AnalyticsQuery
        fields = ['id', 'name', 'description', 'query_type', 'parameters', 'sql_query', 
                 'is_public', 'created_by', 'created_by_name', 'created_at', 'last_used']
        read_only_fields = ['created_by', 'created_at', 'last_used']
