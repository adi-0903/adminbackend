from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

User = get_user_model()

class UserSegment(models.Model):
    """Model to store user segments for analytics"""
    SEGMENT_TYPES = [
        ('active', 'Active Users'),
        ('inactive', 'Inactive Users'),
        ('new', 'New Users'),
        ('churned', 'Churned Users'),
        ('high_value', 'High Value Users'),
        ('low_engagement', 'Low Engagement Users'),
    ]
    
    name = models.CharField(max_length=100)
    segment_type = models.CharField(max_length=20, choices=SEGMENT_TYPES)
    description = models.TextField(blank=True)
    criteria = models.JSONField()  # Store segment criteria as JSON
    user_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = 'User Segment'
        verbose_name_plural = 'User Segments'
    
    def __str__(self):
        return self.name
    
    def update_user_count(self):
        """Update the user count for this segment"""
        users = self.get_users()
        self.user_count = users.count()
        self.save()
    
    def get_users(self):
        """Get users based on segment criteria"""
        from user.models import User, UserInformation
        from django.db.models import Q
        
        criteria = self.criteria
        users = User.objects.all()
        
        if self.segment_type == 'active':
            days_inactive = criteria.get('days_inactive', 3)
            cutoff_date = timezone.now() - timedelta(days=days_inactive)
            users = users.filter(last_active__gte=cutoff_date)
            
        elif self.segment_type == 'inactive':
            days_inactive = criteria.get('days_inactive', 3)
            cutoff_date = timezone.now() - timedelta(days=days_inactive)
            users = users.filter(
                Q(last_active__lt=cutoff_date) | Q(last_active__isnull=True)
            )
            
        elif self.segment_type == 'new':
            days_new = criteria.get('days_new', 7)
            cutoff_date = timezone.now() - timedelta(days=days_new)
            users = users.filter(date_joined__gte=cutoff_date)
            
        elif self.segment_type == 'churned':
            days_churned = criteria.get('days_churned', 30)
            cutoff_date = timezone.now() - timedelta(days=days_churned)
            users = users.filter(
                Q(last_active__lt=cutoff_date) | Q(last_active__isnull=True),
                date_joined__lt=cutoff_date
            )
            
        elif self.segment_type == 'high_value':
            min_collections = criteria.get('min_collections', 10)
            min_revenue = criteria.get('min_revenue', 1000)
            # This would need to be implemented based on your business logic
            # users = users.filter(collection_count__gte=min_collections, total_revenue__gte=min_revenue)
            
        elif self.segment_type == 'low_engagement':
            min_sessions = criteria.get('min_sessions', 5)
            users = users.filter(total_sessions__lt=min_sessions)
        
        return users

class DailyMetrics(models.Model):
    """Model to store daily aggregated metrics"""
    date = models.DateField(unique=True, db_index=True)
    total_users = models.PositiveIntegerField(default=0)
    active_users = models.PositiveIntegerField(default=0)
    new_users = models.PositiveIntegerField(default=0)
    inactive_users = models.PositiveIntegerField(default=0)
    total_collections = models.PositiveIntegerField(default=0)
    total_revenue = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    avg_session_duration = models.PositiveIntegerField(default=0)  # in minutes
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Daily Metric'
        verbose_name_plural = 'Daily Metrics'
        ordering = ['-date']
    
    def __str__(self):
        return f"Metrics for {self.date}"

class SystemMetrics(models.Model):
    """Model to store real-time system metrics"""
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    cpu_usage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    memory_usage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    disk_usage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    active_connections = models.PositiveIntegerField(default=0)
    response_time = models.DecimalField(max_digits=8, decimal_places=3, default=Decimal('0.000'))
    error_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    
    class Meta:
        verbose_name = 'System Metric'
        verbose_name_plural = 'System Metrics'
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"System metrics at {self.timestamp}"

class AnalyticsQuery(models.Model):
    """Model to store frequently used analytics queries"""
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    query_type = models.CharField(max_length=50)  # user_analytics, collection_analytics, etc.
    parameters = models.JSONField()  # Query parameters
    sql_query = models.TextField()  # Raw SQL for complex queries
    is_public = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = 'Analytics Query'
        verbose_name_plural = 'Analytics Queries'
    
    def __str__(self):
        return self.name
