from __future__ import annotations

from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from typing import Optional, Any, Dict, Tuple
import logging
from decimal import Decimal
from django.db import transaction
from .models import User, ReferralUsage
from wallet.models import WalletTransaction

logger = logging.getLogger('user')

def custom_exception_handler(exc: Exception, context: Dict[str, Any]) -> Optional[Response]:
    response = exception_handler(exc, context)
    
    if response is None:
        logger.error(f"Unexpected error: {str(exc)}")
        return Response({
            'error': 'An unexpected error occurred',
            'detail': str(exc) if settings.DEBUG else None
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return response 

def apply_referral_code(referrer: User, referred_user: User) -> Tuple[bool, Dict[str, Any]]:
    """
    Apply a referral code and credit both users' wallets according to settings.
    
    This function uses the following settings from REFERRAL_SETTINGS:
    - ENABLED: Global toggle for referral system
    - REFERRER_CREDIT: Amount credited to the referrer
    - REFEREE_CREDIT: Amount credited to the referee
    - MAX_REFERRAL_USES: Maximum times a referral code can be used (if MAX_REFERRAL_SYSTEM is True)
    - MAX_REFEREE_USES: Maximum times a user can use referral codes (if MAX_REFERRAL_SYSTEM is True)
    - MAX_REFERRAL_SYSTEM: If False, no maximum limitations apply
    - REFERRER_DESCRIPTION: Description for the transaction in referrer's wallet
    - REFEREE_DESCRIPTION: Description for the transaction in referee's wallet
    
    Args:
        referrer: The user who shared their referral code
        referred_user: The user who is using the referral code
        
    Returns:
        Tuple of (success: bool, result: dict) where result contains either:
            - On success: message and bonus amounts
            - On failure: error message
    """
    if not settings.REFERRAL_SETTINGS.get('ENABLED', False):
        return False, {"error": "Referral system is currently disabled"}

    # Check referrer and referee limits
    if not ReferralUsage.check_referrer_limit(referrer):
        return False, {"error": "This referral code has reached its maximum usage limit"}
        
    if not ReferralUsage.check_referee_limit(referred_user):
        max_uses = settings.REFERRAL_SETTINGS.get('MAX_REFEREE_USES', 1)
        return False, {"error": f"You can use at most {max_uses} referral code(s)"}
    
    if referrer.id == referred_user.id:
        return False, {"error": "You cannot use your own referral code"}
    
    # Check if this specific referrer-referee combination already exists
    if ReferralUsage.objects.filter(referrer=referrer, referred_user=referred_user).exists():
        return False, {"error": "You have already used this specific referral code"}
    
    # Only check for existing usage if MAX_REFERRAL_SYSTEM is enabled
    if settings.REFERRAL_SETTINGS.get('MAX_REFERRAL_SYSTEM', True):
        # If existing usage found, return error
        if ReferralUsage.objects.filter(referred_user=referred_user).exists():
            return False, {"error": "You have already used a referral code"}
        
    try:
        with transaction.atomic():
            # Create referral usage record
            ReferralUsage.objects.create(
                referrer=referrer,
                referred_user=referred_user,
                is_rewarded=True
            )
            
            # Add bonus to referrer's wallet
            referrer_wallet = referrer.wallet
            referrer_bonus = Decimal(str(settings.REFERRAL_SETTINGS.get('REFERRER_CREDIT', 50.00)))
            referrer_description = settings.REFERRAL_SETTINGS.get('REFERRER_DESCRIPTION', 'Referral bonus for referring a user')
            
            WalletTransaction.objects.create(
                wallet=referrer_wallet,
                amount=referrer_bonus,
                transaction_type='CREDIT',
                status='SUCCESS',
                description=referrer_description
            )
            referrer_wallet.add_balance(referrer_bonus)
            
            # Add bonus to user's wallet
            user_wallet = referred_user.wallet
            user_bonus = Decimal(str(settings.REFERRAL_SETTINGS.get('REFEREE_CREDIT', 30.00)))
            user_description = settings.REFERRAL_SETTINGS.get('REFEREE_DESCRIPTION', 'Bonus for using referral code')
            
            WalletTransaction.objects.create(
                wallet=user_wallet,
                amount=user_bonus,
                transaction_type='CREDIT',
                status='SUCCESS',
                description=user_description
            )
            user_wallet.add_balance(user_bonus)
            
            return True, {
                "message": "Referral code applied successfully",
                "referrer_bonus": str(referrer_bonus),
                "referee_bonus": str(user_bonus)
            }
    except Exception as e:
        logger.error(f"Error applying referral code: {str(e)}")
        
        # Check if it's a unique constraint violation and provide a clearer message
        if "duplicate key value" in str(e) and "referrer_id, referred_user_id" in str(e):
            return False, {"error": "You have already used this specific referral code"}
            
        return False, {"error": f"Error applying referral code: {str(e)}"} 