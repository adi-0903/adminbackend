from django.contrib import admin
from .models import UserSegment, DailyMetrics, SystemMetrics, AnalyticsQuery


@admin.register(UserSegment)
class UserSegmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'segment_type', 'user_count', 'is_active', 'created_at')
    list_filter = ('segment_type', 'is_active', 'created_at')
    search_fields = ('name', 'description')
    readonly_fields = ('user_count', 'created_at', 'updated_at')


@admin.register(DailyMetrics)
class DailyMetricsAdmin(admin.ModelAdmin):
    list_display = ('date', 'total_users', 'active_users', 'new_users', 'total_collections', 'total_revenue')
    list_filter = ('date',)
    readonly_fields = ('created_at',)
    date_hierarchy = 'date'


@admin.register(SystemMetrics)
class SystemMetricsAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'cpu_usage', 'memory_usage', 'disk_usage', 'response_time', 'error_rate')
    list_filter = ('timestamp',)
    readonly_fields = ('timestamp',)
    date_hierarchy = 'timestamp'


@admin.register(AnalyticsQuery)
class AnalyticsQueryAdmin(admin.ModelAdmin):
    list_display = ('name', 'query_type', 'created_by', 'is_public', 'created_at', 'last_used')
    list_filter = ('query_type', 'is_public', 'created_at')
    search_fields = ('name', 'description')
    readonly_fields = ('created_by', 'created_at', 'last_used')
