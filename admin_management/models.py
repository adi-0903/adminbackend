from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from typing import Any, Optional

User = get_user_model()


class AdminLog(models.Model):
    """Track admin actions for audit purposes"""
    
    ACTION_CHOICES = [
        ('VIEW', 'View'),
        ('CREATE', 'Create'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
        ('SOFT_DELETE', 'Soft Delete'),
        ('RESTORE', 'Restore'),
        ('EXPORT', 'Export'),
        ('IMPORT', 'Import'),
        ('WALLET_ADJUST', 'Wallet Adjustment'),
        ('USER_SUSPEND', 'User Suspend'),
        ('USER_ACTIVATE', 'User Activate'),
    ]
    
    admin_user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='admin_logs')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, db_index=True)
    model_name = models.CharField(max_length=100, db_index=True)
    object_id = models.CharField(max_length=255, db_index=True)
    object_repr = models.CharField(max_length=255, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['admin_user', 'created_at']),
            models.Index(fields=['action', 'created_at']),
            models.Index(fields=['model_name', 'created_at']),
        ]
        verbose_name = 'Admin Log'
        verbose_name_plural = 'Admin Logs'
    
    def __str__(self) -> str:
        return f"{self.admin_user.phone_number} - {self.action} - {self.model_name}"


class AdminNotification(models.Model):
    """Notifications for admin alerts"""
    
    PRIORITY_CHOICES = [
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
        ('CRITICAL', 'Critical'),
    ]
    
    admin_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='admin_notifications')
    title = models.CharField(max_length=255)
    message = models.TextField()
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='MEDIUM')
    is_read = models.BooleanField(default=False, db_index=True)
    related_model = models.CharField(max_length=100, blank=True)
    related_object_id = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['admin_user', 'is_read', 'created_at']),
            models.Index(fields=['priority', 'created_at']),
        ]
        verbose_name = 'Admin Notification'
        verbose_name_plural = 'Admin Notifications'
    
    def __str__(self) -> str:
        return f"{self.title} - {self.priority}"
    
    def mark_as_read(self) -> None:
        """Mark notification as read"""
        self.is_read = True
        self.read_at = timezone.now()
        self.save(update_fields=['is_read', 'read_at'])


class AdminReport(models.Model):
    """Store generated admin reports"""
    
    REPORT_TYPE_CHOICES = [
        ('USER_SUMMARY', 'User Summary'),
        ('WALLET_SUMMARY', 'Wallet Summary'),
        ('COLLECTION_SUMMARY', 'Collection Summary'),
        ('TRANSACTION_REPORT', 'Transaction Report'),
        ('REFERRAL_REPORT', 'Referral Report'),
        ('CUSTOM', 'Custom Report'),
    ]
    
    admin_user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='admin_reports')
    report_type = models.CharField(max_length=50, choices=REPORT_TYPE_CHOICES, db_index=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    data = models.JSONField(default=dict)
    filters = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['report_type', 'created_at']),
            models.Index(fields=['admin_user', 'created_at']),
        ]
        verbose_name = 'Admin Report'
        verbose_name_plural = 'Admin Reports'
    
    def __str__(self) -> str:
        return f"{self.title} - {self.report_type}"
