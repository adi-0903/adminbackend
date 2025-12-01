from django.contrib import admin
from .models import AdminLog, AdminNotification, AdminReport


@admin.register(AdminLog)
class AdminLogAdmin(admin.ModelAdmin):
    list_display = ('admin_user', 'action', 'model_name', 'object_repr', 'created_at')
    list_filter = ('action', 'model_name', 'created_at')
    search_fields = ('admin_user__phone_number', 'object_repr', 'object_id')
    readonly_fields = ('admin_user', 'action', 'model_name', 'object_id', 'object_repr', 'changes', 'ip_address', 'user_agent', 'created_at')
    
    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AdminNotification)
class AdminNotificationAdmin(admin.ModelAdmin):
    list_display = ('admin_user', 'title', 'priority', 'is_read', 'created_at')
    list_filter = ('priority', 'is_read', 'created_at')
    search_fields = ('admin_user__phone_number', 'title', 'message')
    readonly_fields = ('created_at', 'read_at')
    
    def has_add_permission(self, request):
        return False


@admin.register(AdminReport)
class AdminReportAdmin(admin.ModelAdmin):
    list_display = ('admin_user', 'report_type', 'title', 'created_at')
    list_filter = ('report_type', 'created_at')
    search_fields = ('admin_user__phone_number', 'title', 'description')
    readonly_fields = ('admin_user', 'created_at')
    
    def has_add_permission(self, request):
        return False
