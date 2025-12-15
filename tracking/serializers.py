from rest_framework import serializers
from .models import DeviceInfo, UserSession, UserActivity


class DeviceInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceInfo
        fields = [
            'device_type',
            'platform',
            'app_version',
            'os_version',
            'device_model',
            'last_device_used',
            'last_seen',
        ]


class UserSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSession
        fields = [
            'session_start',
            'session_end',
            'duration_minutes',
            'is_active',
        ]


class UserActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = UserActivity
        fields = [
            'activity_type',
            'feature_name',
            'description',
            'timestamp',
        ]
