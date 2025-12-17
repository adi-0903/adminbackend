from django.contrib import admin
from .models import UserSegment, DailyMetrics, SystemMetrics, AnalyticsQuery
from .crm_models import InactiveUserTask, TaskComment


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


@admin.register(InactiveUserTask)
class InactiveUserTaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'status', 'priority', 'assigned_to', 'created_at', 'due_date')
    list_filter = ('status', 'priority', 'created_at', 'due_date')
    search_fields = ('title', 'description', 'user__phone_number')
    readonly_fields = ('created_at', 'updated_at', 'completed_at')
    raw_id_fields = ('user', 'assigned_to', 'created_by')
    date_hierarchy = 'created_at'


@admin.register(TaskComment)
class TaskCommentAdmin(admin.ModelAdmin):
    list_display = ('task', 'author', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('comment', 'task__title')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('task', 'author')
