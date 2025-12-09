from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
from .models import User, UserActivity
from wallet.models import Wallet
import logging

logger = logging.getLogger('user')


@receiver(post_save, sender=User)
def create_user_wallet(sender, instance, created, **kwargs):
    """Create wallet when a new user is created"""
    if created:
        try:
            Wallet.create_wallet_with_welcome_bonus(instance)
            logger.info(f"Wallet created for user {instance.phone_number}")
        except Exception as e:
            logger.error(f"Error creating wallet for user {instance.phone_number}: {str(e)}")


@receiver(post_save, sender=User)
def track_user_login(sender, instance, created, **kwargs):
    """Track user login activity"""
    if not created and instance.last_login:
        # Update last_active timestamp
        instance.last_active = timezone.now()
        instance.login_count += 1
        instance.total_sessions += 1
        instance.is_online = True
        instance.session_start_time = timezone.now()
        instance.save(update_fields=['last_active', 'login_count', 'total_sessions', 'is_online', 'session_start_time'])
        
        # Create activity record
        try:
            UserActivity.objects.create(
                user=instance,
                activity_type='login',
                metadata={'ip_address': getattr(instance, '_ip_address', None)}
            )
            logger.info(f"Login activity recorded for {instance.phone_number}")
        except Exception as e:
            logger.error(f"Error recording login activity: {str(e)}")


def log_user_activity(user, activity_type, metadata=None, ip_address=None, user_agent=None, device_type=None, platform=None):
    """
    Helper function to log user activities
    
    Args:
        user: User instance
        activity_type: Type of activity (from UserActivity.ACTIVITY_TYPES)
        metadata: Additional data as dict
        ip_address: User's IP address
        user_agent: User's browser/app user agent
        device_type: Device type (mobile, tablet, desktop)
        platform: Platform (ios, android, web)
    """
    try:
        UserActivity.objects.create(
            user=user,
            activity_type=activity_type,
            metadata=metadata,
            ip_address=ip_address,
            user_agent=user_agent,
            device_type=device_type,
            platform=platform
        )
        logger.info(f"Activity '{activity_type}' logged for user {user.phone_number}")
    except Exception as e:
        logger.error(f"Error logging activity: {str(e)}")
