from django.contrib import admin
from .models import DeviceInfo, UserSession, UserActivity


@admin.register(DeviceInfo)
class DeviceInfoAdmin(admin.ModelAdmin):
    list_display = ['user', 'device_type', 'platform', 'device_model', 'last_seen']
    list_filter = ['device_type', 'platform', 'created_at']
    search_fields = ['user__username', 'device_model']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = ['user', 'session_start', 'session_end', 'duration_minutes', 'is_active']
    list_filter = ['is_active', 'session_start']
    search_fields = ['user__username']
    readonly_fields = ['session_start']


@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
    list_display = ['user', 'activity_type', 'feature_name', 'timestamp']
    list_filter = ['activity_type', 'timestamp']
    search_fields = ['user__username', 'feature_name']
    readonly_fields = ['timestamp']
