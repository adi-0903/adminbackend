from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.core.validators import RegexValidator, MinLengthValidator
from django.utils import timezone
from django.db.models import QuerySet
from typing import Optional, Any, Dict, Union, Tuple
import random
import string
import logging

logger = logging.getLogger('user')

class ActiveManager(models.Manager):
    def get_queryset(self) -> QuerySet:
        return super().get_queryset().filter(is_active=True)

class CustomUserManager(BaseUserManager):
    def get_queryset(self) -> QuerySet:
        # By default, filter to only active users
        return super().get_queryset().filter(is_active=True)

    def get_all(self) -> QuerySet:
        # Method to get all users including inactive ones
        return super().get_queryset()

    def filter(self, *args: Any, **kwargs: Any) -> QuerySet:
        # For direct filtering, use the active users queryset
        return self.get_queryset().filter(*args, **kwargs)

    def create_user(
        self, 
        phone_number: str,  
        password: Optional[str] = None, 
        **extra_fields: Any
    ) -> User:
        if not phone_number:
            raise ValueError('Phone number must be set')
        
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        
        user = self.model(
            phone_number=phone_number,
            **extra_fields
        )
        user.set_password(password)  # Set the password
        user.save(using=self._db)
        return user

    def create_superuser(
        self, 
        phone_number: str, 
        password: Optional[str] = None, 
        **extra_fields: Any
    ) -> User:
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        
        return self.create_user(phone_number, password, **extra_fields)

class User(AbstractBaseUser, PermissionsMixin):
    phone_regex = RegexValidator(
        regex=r'^(\+91)?[1-9]\d{9}$',
        message="Phone number must be a 10-digit number."
    )
    phone_number = models.CharField(
        validators=[phone_regex],
        max_length=13,  # +91 + 10 digits
        unique=True,
        db_index=True
    )
    
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)
    referral_code = models.CharField(
        max_length=5,
        unique=True,
        blank=True,
        null=True,
        db_index=True
    )

    objects = CustomUserManager()
    all_objects = models.Manager()

    USERNAME_FIELD = 'phone_number'
    REQUIRED_FIELDS = []  # No required fields since we are using phone number only

    class Meta:
        indexes = [
            models.Index(fields=['phone_number']),
            models.Index(fields=['referral_code']),
            models.Index(fields=['is_active']),
        ]
        verbose_name = 'user'
        verbose_name_plural = 'users'

    def __str__(self) -> str:
        return self.phone_number

    def save(self, *args: Any, **kwargs: Any) -> None:
        # Format phone number to include +91
        if self.phone_number and not self.phone_number.startswith('+91'):
            self.phone_number = f'+91{self.phone_number}'
        
        if not self.referral_code:
            self.referral_code = self.generate_unique_referral_code()
        super().save(*args, **kwargs)

    @staticmethod
    def generate_unique_referral_code() -> str:
        """Generate a unique 5 character referral code"""
        attempts = 0
        max_attempts = 5
        
        while attempts < max_attempts:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
            if not User.objects.filter(referral_code=code).exists():
                return code
            attempts += 1
            
        # If we couldn't generate a unique code after max attempts,
        # generating a longer one as fallback
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

    def soft_delete(self) -> None:
        """Soft delete the user"""
        self.is_active = False
        self.save(update_fields=['is_active'])
        
    def check_and_apply_referral_code(self, referral_code: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if a referral code can be applied to this user and apply it.
        
        Args:
            referral_code: The referral code to apply
            
        Returns:
            Tuple of (success: bool, result: dict) where result contains either 
            success message or error message.
        """
        from .utils import apply_referral_code
        
        try:
            # Find the referrer by referral code
            referrer = User.objects.get(referral_code=referral_code)
            
            # Apply the referral code using the utility function
            return apply_referral_code(referrer, self)
            
        except User.DoesNotExist:
            return False, {"error": "Invalid referral code"}
        except Exception as e:
            return False, {"error": f"Error applying referral code: {str(e)}"}

class ReferralUsage(models.Model):
    """
    Records usage of referral codes between users.
    
    The referral system can be configured through settings.REFERRAL_SETTINGS with:
    - ENABLED: Toggle to enable/disable the entire referral system
    - REFERRER_CREDIT: Amount credited to the referrer (who shared their code)
    - REFEREE_CREDIT: Amount credited to the referee (who used the code)
    - MAX_REFERRAL_USES: Maximum number of times a single referral code can be used
    - MAX_REFEREE_USES: Maximum number of times a user can use referral codes
    - MAX_REFERRAL_SYSTEM: Toggle for maximum referral limitations (if False, no limits apply)
    - REFERRER_DESCRIPTION: Description for the transaction in referrer's wallet
    - REFEREE_DESCRIPTION: Description for the transaction in referee's wallet
    """
    
    referrer: models.ForeignKey = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='referrals_given',
        db_index=True
    )
    referred_user: models.ForeignKey = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='referral_used',
        db_index=True
    )
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True, db_index=True)
    is_rewarded: models.BooleanField = models.BooleanField(default=False)

    class Meta:
        unique_together = ('referrer', 'referred_user')
        indexes = [
            models.Index(fields=['referrer', 'created_at']),
            models.Index(fields=['referred_user', 'created_at']),
            models.Index(fields=['is_rewarded']),
        ]
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f"{self.referrer.phone_number} referred {self.referred_user.phone_number}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.referrer_id == self.referred_user_id:
            raise ValueError("A user cannot refer themselves")
        super().save(*args, **kwargs)
        
    @classmethod
    def get_referrer_usage_count(cls, referrer: User) -> int:
        """Return the number of times a referrer's code has been used"""
        return cls.objects.filter(referrer=referrer, is_rewarded=True).count()
        
    @classmethod
    def get_referee_usage_count(cls, referee: User) -> int:
        """Return the number of times a user has used referral codes"""
        return cls.objects.filter(referred_user=referee, is_rewarded=True).count()
        
    @classmethod
    def check_referrer_limit(cls, referrer: User) -> bool:
        """Check if referrer has reached the maximum number of referrals
        Returns True if limit not reached, False if limit reached"""
        from django.conf import settings
        
        # If MAX_REFERRAL_SYSTEM is False, then no maximum limitations apply
        if not settings.REFERRAL_SETTINGS.get('MAX_REFERRAL_SYSTEM', True):
            return True
            
        max_uses = settings.REFERRAL_SETTINGS.get('MAX_REFERRAL_USES', 10)
        current_uses = cls.get_referrer_usage_count(referrer)
        return current_uses < max_uses
        
    @classmethod
    def check_referee_limit(cls, referee: User) -> bool:
        """Check if referee has reached the maximum number of referral uses
        Returns True if limit not reached, False if limit reached"""
        from django.conf import settings
        
        # If MAX_REFERRAL_SYSTEM is False, then no maximum limitations apply
        if not settings.REFERRAL_SETTINGS.get('MAX_REFERRAL_SYSTEM', True):
            return True
            
        max_uses = settings.REFERRAL_SETTINGS.get('MAX_REFEREE_USES', 1)
        current_uses = cls.get_referee_usage_count(referee)
        return current_uses < max_uses

class UserInformation(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=255, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    active = ActiveManager()

    def __str__(self):
        return self.name or str(self.user)
        
    def delete(self, *args, **kwargs):
        self.is_active = False
        self.deleted_at = timezone.now()
        self.save()

    def hard_delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
