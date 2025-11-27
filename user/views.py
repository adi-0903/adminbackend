from __future__ import annotations

from django.shortcuts import render
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import authenticate, get_user_model
from django.db.models import Q, Prefetch, QuerySet
from django.http import HttpRequest
from typing import Optional, Any, Dict, Union, cast
from .serializers import (
    UserLoginSerializer, 
    ApplyReferralCodeSerializer,
    VerifyOTPSerializer,
    UserSerializer,
    UserInformationSerializer
)
from django.core.cache import cache
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from django.core.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.db import transaction
from .models import User, ReferralUsage, UserInformation
from wallet.models import Wallet, WalletTransaction
from decimal import Decimal
import logging
from rest_framework.decorators import api_view, permission_classes
from django.conf import settings
from rest_framework.exceptions import Throttled, NotAuthenticated
import time
from rest_framework import generics, permissions
from .otp_system import send_otp, verify_otp
from django.db import IntegrityError
import requests
from .utils import apply_referral_code

logger = logging.getLogger('user')
User = get_user_model()

class CustomAnonRateThrottle(AnonRateThrottle):
    rate = '100/minute'

    def throttle_failure(self) -> None:
        """Custom throttle failure handling with detailed response"""
        wait = self.wait()
        raise Throttled(detail={
            'error': 'Request was throttled',
            'wait_seconds': int(wait)
        })

class BaseAPIView(APIView):
    """Base class for common API functionality"""
    
    def handle_exception(self, exc: Exception) -> Response:
        """Centralized exception handling"""
        if isinstance(exc, ValidationError):
            logger.warning(f"Validation error: {str(exc)}")
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        
        if isinstance(exc, NotAuthenticated):
            return Response(
                {'detail': 'Authentication credentials were not provided.'}, 
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        logger.error(f"Unexpected error: {str(exc)}", exc_info=True)
        return Response(
            {'error': 'An unexpected error occurred'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

class UserLoginView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = UserLoginSerializer

    def post(self, request: HttpRequest) -> Response:
        try:
            serializer = self.get_serializer(data=request.data)
            if serializer.is_valid():
                phone_number = serializer.validated_data['phone_number']
                user = User.objects.filter(phone_number=f"+91{phone_number}").first()

                if settings.USE_OTP_FOR_LOGIN:
                    if user:
                        otp_response = send_otp(phone_number)
                        if otp_response is None or "error" in otp_response:
                            error_msg = otp_response.get("error", "Failed to send OTP. Please try again later.") if otp_response else "Failed to send OTP. Please try again later."
                            
                            # Special case for timeout - OTP might still be delivered
                            if "timed out" in error_msg.lower():
                                logger.warning(f"OTP request timed out for {phone_number}, but OTP might still be delivered")
                                return Response(
                                    {
                                        "message": "OTP request timed out but the OTP might still be delivered. If you receive the OTP, please use it to login.",
                                        "possible_otp_sent": True
                                    },
                                    status=status.HTTP_202_ACCEPTED
                                )
                                
                            logger.error(f"OTP send failure for {phone_number}: {error_msg}")
                            return Response(
                                {
                                    "error": error_msg
                                },
                                status=status.HTTP_503_SERVICE_UNAVAILABLE
                            )
                        return Response(
                            {
                                "message": "OTP sent to the phone number.",
                                "verificationId": otp_response['data']['verificationId'],
                                "mobileNumber": phone_number
                            }, 
                            status=status.HTTP_200_OK
                        )
                    else:
                        new_user = User(phone_number=f"+91{phone_number}")
                        new_user.save()

                        otp_response = send_otp(phone_number)
                        if otp_response is None or "error" in otp_response:
                            error_msg = otp_response.get("error", "Failed to send OTP. Please try again later.") if otp_response else "Failed to send OTP. Please try again later."
                            
                            # Special case for timeout - OTP might still be delivered
                            if "timed out" in error_msg.lower():
                                logger.warning(f"OTP request timed out for new user {phone_number}, but OTP might still be delivered")
                                return Response(
                                    {
                                        "message": "OTP request timed out but the OTP might still be delivered. If you receive the OTP, please use it to login.",
                                        "possible_otp_sent": True
                                    },
                                    status=status.HTTP_202_ACCEPTED
                                )
                                
                            logger.error(f"OTP send failure for new user {phone_number}: {error_msg}")
                            return Response(
                                {
                                    "error": error_msg
                                },
                                status=status.HTTP_503_SERVICE_UNAVAILABLE
                            )
                        return Response(
                            {
                                "message": "OTP sent to the phone number.",
                                "verificationId": otp_response['data']['verificationId'],
                                "mobileNumber": phone_number
                            }, 
                            status=status.HTTP_200_OK
                        )
                else:
                    if user:
                        token = AccessToken.for_user(user)
                        return Response({
                            'token': str(token),
                            'message': 'Login successful',
                            'user': {
                                'id': user.id,
                                'phone_number': user.phone_number
                            }
                        }, status=status.HTTP_200_OK)
                    else:
                        return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except IntegrityError as e:
            logger.error(f"Database integrity error: {str(e)}")
            return Response({'error': 'Database Error', 'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Unexpected error in login: {str(e)}", exc_info=True)
            return Response({'error': 'An unexpected error occurred. Please try again later.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class VerifyOTPView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = VerifyOTPSerializer

    def post(self, request: HttpRequest) -> Response:
        try:
            serializer = self.get_serializer(data=request.data)
            if serializer.is_valid():
                phone_number = serializer.validated_data['phone_number']
                verificationId = serializer.validated_data['verificationId']
                otp = serializer.validated_data['otp']
                
                if settings.USE_OTP_FOR_LOGIN:
                    verification_response = verify_otp(str(phone_number), str(verificationId), str(otp))

                    if "error" in verification_response:
                        error_msg = verification_response.get('error', 'OTP verification failed')
                        
                        # Special case for timeout - allow the user to retry
                        if "timed out" in error_msg.lower():
                            logger.warning(f"OTP verification request timed out for {phone_number}")
                            return Response(
                                {
                                    "message": "OTP verification request timed out. Your OTP might still be valid. Please try again.",
                                    "verification_timeout": True
                                },
                                status=status.HTTP_202_ACCEPTED
                            )
                        
                        logger.error(f"OTP verification failure for {phone_number}: {error_msg}")
                        return Response(
                            {
                                "error": error_msg
                            },
                            status=status.HTTP_400_BAD_REQUEST
                        )

                    # Get or create user after successful OTP verification
                    try:
                        user = User.objects.get(phone_number=f"+91{phone_number}")
                    except User.DoesNotExist:
                        user = User.objects.create(
                            phone_number=f"+91{phone_number}",
                            is_active=True
                        )

                    token = AccessToken.for_user(user)
                    
                    return Response({
                        'token': str(token),
                        'message': 'Login successful',
                        'user': {
                            'id': user.id,  # Include user ID in response
                            'phone_number': user.phone_number
                        }
                    }, status=status.HTTP_200_OK)
                else:
                    user = User.objects.get(phone_number=f"+91{phone_number}")
                    token = AccessToken.for_user(user)
                    
                    return Response({
                        'token': str(token),
                        'message': 'Login successful',
                        'user': {
                            'id': user.id,  # Include user ID in response
                            'phone_number': user.phone_number
                        }
                    }, status=status.HTTP_200_OK)
                    
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Unexpected error in verify OTP: {str(e)}", exc_info=True)
            return Response({'error': 'An unexpected error occurred. Please try again later.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
class ApplyReferralCodeView(BaseAPIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [CustomAnonRateThrottle]

    def post(self, request: HttpRequest) -> Response:
        try:
            if not request.user.is_authenticated:
                return Response({
                    'error': 'Authentication required'
                }, status=status.HTTP_401_UNAUTHORIZED)
            
            serializer = ApplyReferralCodeSerializer(data=request.data, context={'request': request})
            if serializer.is_valid():
                referral_code: str = serializer.validated_data['referral_code']
                
                try:
                    referrer = User.objects.select_related('wallet').get(referral_code=referral_code)
                    user = cast(User, request.user)
                    
                    # Apply referral code and get result
                    success, result = apply_referral_code(referrer, user)
                    
                    if success:
                        return Response({
                            'message': result['message'],
                            'bonus_earned': result['referee_bonus']
                        }, status=status.HTTP_200_OK)
                    else:
                        return Response({
                            'error': result['error']
                        }, status=status.HTTP_400_BAD_REQUEST)
                        
                except User.DoesNotExist:
                    return Response({
                        'error': 'Invalid referral code'
                    }, status=status.HTTP_400_BAD_REQUEST)
                except ValidationError as e:
                    return Response({
                        'error': str(e)
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as exc:
            return self.handle_exception(exc)

class UserInformationView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request: HttpRequest) -> Response:
        try:
            user_info = UserInformation.objects.get(user=request.user)
            serializer = UserInformationSerializer(user_info, context={'request': request})
            return Response(serializer.data)
        except UserInformation.DoesNotExist:
            # Create a response with available user information
            user = request.user
            response_data = {
                "name": None,
                "email": None,
                "phone_number": user.phone_number,
                "referral_code": user.referral_code
            }
            return Response(response_data)
    
    def put(self, request: HttpRequest) -> Response:
        try:
            user_info, created = UserInformation.objects.get_or_create(user=request.user)
            serializer = UserInformationSerializer(
                user_info, 
                data=request.data, 
                partial=True,
                context={'request': request}
            )
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
