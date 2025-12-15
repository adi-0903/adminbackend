from django.db import models
from django.conf import settings
from django.utils import timezone


class DeviceInfo(models.Model):
    DEVICE_TYPE_CHOICES = [
        ('mobile', 'Mobile'),
        ('tablet', 'Tablet'),
        ('web', 'Web'),
        ('unknown', 'Unknown'),
    ]
    
    PLATFORM_CHOICES = [
        ('ios', 'iOS'),
        ('android', 'Android'),
        ('windows', 'Windows'),
        ('macos', 'macOS'),
        ('linux', 'Linux'),
        ('web', 'Web'),
        ('unknown', 'Unknown'),
    ]
    
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='device_info')
    device_type = models.CharField(max_length=20, choices=DEVICE_TYPE_CHOICES, default='unknown')
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES, default='unknown')
    app_version = models.CharField(max_length=50, default='Unknown')
    os_version = models.CharField(max_length=50, default='Unknown')
    device_model = models.CharField(max_length=100, default='Unknown')
    device_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    user_agent = models.TextField(default='Unknown')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    last_device_used = models.CharField(max_length=100, default='Unknown')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_seen = models.DateTimeField(default=timezone.now)
    
    class Meta:
        db_table = 'tracking_device_info'
        verbose_name = 'Device Information'
        verbose_name_plural = 'Device Information'
    
    def __str__(self):
        return f"{self.user.username} - {self.platform} ({self.device_type})"


class UserSession(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='device_sessions')
    device_info = models.ForeignKey(DeviceInfo, on_delete=models.SET_NULL, null=True, blank=True)
    session_start = models.DateTimeField(auto_now_add=True)
    session_end = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.IntegerField(default=0)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(default='Unknown')
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'tracking_user_session'
        verbose_name = 'User Session'
        verbose_name_plural = 'User Sessions'
        ordering = ['-session_start']
    
    def __str__(self):
        return f"{self.user.username} - {self.session_start}"


class UserActivity(models.Model):
    ACTIVITY_TYPE_CHOICES = [
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('feature_access', 'Feature Access'),
        ('transaction', 'Transaction'),
        ('error', 'Error'),
        ('other', 'Other'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='device_activities')
    device_info = models.ForeignKey(DeviceInfo, on_delete=models.SET_NULL, null=True, blank=True)
    activity_type = models.CharField(max_length=20, choices=ACTIVITY_TYPE_CHOICES)
    feature_name = models.CharField(max_length=100, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    class Meta:
        db_table = 'tracking_user_activity'
        verbose_name = 'User Activity'
        verbose_name_plural = 'User Activities'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['activity_type', '-timestamp']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.activity_type} - {self.timestamp}"
