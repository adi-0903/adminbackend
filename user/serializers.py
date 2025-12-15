from __future__ import annotations

from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from typing import Any, Dict
from .models import ReferralUsage, User, UserInformation
from django.conf import settings

User = get_user_model()

# Import tracking serializer for device info
try:
    from tracking.serializers import DeviceInfoSerializer
except ImportError:
    DeviceInfoSerializer = None

class UserLoginSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=10)

    class Meta:
        model = User
        fields = ['phone_number']

    def validate_phone_number(self, value):
        if not value.isdigit() or len(value) != 10:
            raise serializers.ValidationError("Phone number must be a 10-digit number.")
        
        # Remove +91 prefix if present
        if value.startswith('+91'):
            value = value[3:]
        return value
    
class VerifyOTPSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=10)
    verificationId = serializers.CharField()
    otp = serializers.CharField(max_length=6)

    def validate_phone_number(self, value):
        if not value.isdigit() or len(value) != 10:
            raise serializers.ValidationError("Phone number must be a 10-digit number.")
        return value

class ApplyReferralCodeSerializer(serializers.Serializer):
    referral_code: serializers.CharField = serializers.CharField(max_length=5)

    def validate_referral_code(self, value: str) -> str:
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("User must be authenticated")

        try:
            # Just check if the referral code exists
            User.objects.get(referral_code=value)
            return value
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid referral code")

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['phone_number', 'referral_code'] 

class UserInformationSerializer(serializers.ModelSerializer):
    phone_number = serializers.CharField(source='user.phone_number', required=False)
    referral_code = serializers.CharField(source='user.referral_code', read_only=True)
    
    class Meta:
        model = UserInformation
        fields = ['id', 'name', 'email', 'phone_number', 'referral_code']

    def validate_phone_number(self, value):
        if not value:
            return value
            
        # Remove +91 prefix if present
        if value.startswith('+91'):
            value = value[3:]
            
        if not value.isdigit() or len(value) != 10:
            raise serializers.ValidationError("Phone number must be a 10-digit number.")

        # Check if phone number already exists
        formatted_phone = f'+91{value}'
        user = self.context['request'].user
        if User.objects.exclude(id=user.id).filter(phone_number=formatted_phone).exists():
            raise serializers.ValidationError("This phone number is already registered.")
            
        return value

    def create(self, validated_data):
        user = self.context['request'].user
        validated_data.pop('user', None)
        user_info = UserInformation.objects.create(user=user, **validated_data)
        return user_info

    def update(self, instance, validated_data):
        try:
            user_data = validated_data.pop('user', {})
            
            # Update phone number if provided
            if 'phone_number' in user_data:
                phone_number = user_data['phone_number']
                if not phone_number.startswith('+91'):
                    phone_number = f'+91{phone_number}'
                instance.user.phone_number = phone_number
                instance.user.save()

            # Update other fields
            instance.name = validated_data.get('name', instance.name)
            instance.email = validated_data.get('email', instance.email)
            instance.save()
            
            return instance
            
        except Exception as e:
            raise serializers.ValidationError(f"Failed to update user information: {str(e)}")


class UserDetailSerializer(serializers.ModelSerializer):
    """
    Detailed user serializer with device info for admin dashboard
    """
    user_info = serializers.SerializerMethodField()
    device_info = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id',
            'phone_number',
            'referral_code',
            'is_active',
            'date_joined',
            'last_login',
            'last_active',
            'login_count',
            'total_sessions',
            'user_info',
            'device_info',
        ]
    
    def get_user_info(self, obj):
        """Get user information"""
        try:
            user_info = obj.user_info
            return {
                'name': user_info.name if hasattr(user_info, 'name') else 'Unknown',
                'email': user_info.email if hasattr(user_info, 'email') else '',
            }
        except:
            return {
                'name': 'Unknown',
                'email': '',
            }
    
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
        except:
            return None
