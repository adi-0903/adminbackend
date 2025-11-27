from django.test import TestCase, Client
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from django.contrib.auth import get_user_model
from .models import User, ReferralUsage
from wallet.models import Wallet, WalletTransaction
from decimal import Decimal
from django.core import mail
from django.core.cache import cache
from django.utils import timezone
import json

User = get_user_model()

class BaseAPITest(APITestCase):
    """Base test class with common setup and teardown"""
    def setUp(self):
        cache.clear()  # Clear cache at the start of each test
        self.client = APIClient()

    def tearDown(self):
        cache.clear()  # Clear cache after each test

    def remove_authentication(self):
        """Helper method to remove authentication"""
        self.client.force_authenticate(user=None)
        self.client.credentials(HTTP_AUTHORIZATION='')

class UserModelTests(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.user_data = {
            'phone_number': '9876543210',
            'password': 'testpass123'
        }
        self.user = User.objects.create_user(**self.user_data)

    def test_user_creation(self):
        """Test user creation with valid data"""
        self.assertEqual(self.user.phone_number, f"+91{self.user_data['phone_number']}")
        self.assertTrue(self.user.check_password(self.user_data['password']))
        self.assertTrue(self.user.is_active)
        self.assertFalse(self.user.is_staff)
        self.assertIsNotNone(self.user.referral_code)
        self.assertEqual(len(self.user.referral_code), 5)

    def test_user_str_representation(self):
        """Test string representation of user"""
        expected_str = f"{self.user.username} ({self.user.phone_number})"
        self.assertEqual(str(self.user), expected_str)

    def test_wallet_creation(self):
        """Test wallet is automatically created for new user"""
        self.assertIsNotNone(self.user.wallet)
        # Initial wallet balance is 1000
        self.assertEqual(self.user.wallet.balance, Decimal('1000'))

    def test_unique_referral_code_generation(self):
        """Test unique referral code generation"""
        user2_data = {
            'username': 'testuser2',
            'phone_number': '9876543211',  # Remove +91 prefix
            'email': 'test2@example.com',
            'password': 'testpass123'
        }
        user2 = User.objects.create_user(**user2_data)
        self.assertNotEqual(self.user.referral_code, user2.referral_code)

    def test_soft_delete(self):
        """Test soft deletion of user"""
        self.user.soft_delete()
        self.assertFalse(self.user.is_active)
        self.assertFalse(User.objects.filter(username=self.user.username).exists())
        self.assertTrue(User.all_objects.filter(username=self.user.username).exists())

    def test_create_superuser(self):
        """Test superuser creation"""
        superuser = User.objects.create_superuser(
            username='admin',
            phone_number='9876543212',
            password='adminpass123'
        )
        self.assertTrue(superuser.is_staff)
        self.assertTrue(superuser.is_superuser)
        self.assertTrue(superuser.is_active)

    def test_invalid_superuser_creation(self):
        """Test invalid superuser creation"""
        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                username='admin',
                phone_number='9876543212',
                password='adminpass123',
                is_staff=False
            )

        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                username='admin',
                phone_number='9876543212',
                password='adminpass123',
                is_superuser=False
            )

    def test_auto_username_generation(self):
        """Test automatic username generation from phone number"""
        user = User.objects.create_user(
            username='',
            phone_number='9876543213',
            password='testpass123'
        )
        self.assertTrue(user.username.startswith('user_543213'))

    def test_reset_password_token(self):
        """Test reset password token creation and verification"""
        # Create token
        token = self.user.create_reset_password_token()
        self.assertEqual(len(token), 6)
        self.assertTrue(token.isdigit())
        self.assertIsNotNone(self.user.reset_password_token_created_at)

        # Verify valid token
        self.assertTrue(self.user.verify_reset_password_token(token))

        # Verify invalid token
        self.assertFalse(self.user.verify_reset_password_token('123456'))

        # Verify expired token
        self.user.reset_password_token_created_at = timezone.now() - timezone.timedelta(minutes=11)
        self.user.save()
        self.assertFalse(self.user.verify_reset_password_token(token))

class UserRegistrationTests(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.register_url = reverse('user-register')
        self.login_url = reverse('user-login')
        
        # Create referrer for referral tests
        self.referrer = User.objects.create_user(
            username='referrer',
            phone_number='9876543210',
            email='referrer@example.com',
            password='testpass123'
        )

    def test_registration(self):
        """Test user registration with valid data"""
        data = {
            'phone_number': '9876543211',
            'password': 'testpass123',
            'confirm_password': 'testpass123',
            'terms_accepted': True
        }
        response = self.client.post(self.register_url, data, format='json')
        
        if response.status_code != status.HTTP_201_CREATED:
            print(f"Registration failed with response: {response.data}")
            
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(phone_number=f"+91{data['phone_number']}").exists())

    def test_registration_with_referral(self):
        """Test user registration with referral code"""
        data = {
            'username': 'newuser',
            'phone_number': '9876543212',
            'email': 'newuser@test.com',
            'password': 'testpass123',
            'confirm_password': 'testpass123',
            'terms_accepted': True,
            'first_name': 'New',
            'last_name': 'User',
            'referral_code': self.referrer.referral_code
        }
        response = self.client.post(self.register_url, data, format='json')
        
        if response.status_code != status.HTTP_201_CREATED:
            print(f"Registration with referral failed with response: {response.data}")
            
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(email=data['email']).exists())
        
        # Verify referral was applied
        new_user = User.objects.get(email=data['email'])
        referral_usage = ReferralUsage.objects.filter(
            referrer=self.referrer,
            referred_user=new_user
        ).first()
        self.assertIsNotNone(referral_usage, "No referral usage record found")
        
        # Verify wallet bonuses (initial balance 1000 + referral bonus)
        referrer_wallet = Wallet.objects.get(user=self.referrer)
        new_user_wallet = Wallet.objects.get(user=new_user)
        self.assertEqual(referrer_wallet.balance, Decimal('1050.00'))
        self.assertEqual(new_user_wallet.balance, Decimal('1030.00'))

    def test_invalid_registration_data(self):
        """Test registration with invalid data"""
        # Test missing required fields
        invalid_data = {
            'email': 'test@example.com',
            'password': 'testpass123',
            'confirm_password': 'testpass123',
            'terms_accepted': True,
            'first_name': 'Test',
            'last_name': 'User'
        }
        response = self.client.post(self.register_url, invalid_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('username', response.data)
        
        # Test invalid phone number
        invalid_data = {
            'username': 'testuser',
            'phone_number': '123',  # Invalid phone number
            'email': 'test@example.com',
            'password': 'testpass123',
            'confirm_password': 'testpass123',
            'terms_accepted': True,
            'first_name': 'Test',
            'last_name': 'User'
        }
        response = self.client.post(self.register_url, invalid_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('phone_number', response.data)
        
        # Test duplicate username
        # First create a user
        valid_data = {
            'username': 'testuser',
            'phone_number': '9876543212',
            'email': 'test@example.com',
            'password': 'testpass123',
            'confirm_password': 'testpass123',
            'terms_accepted': True,
            'first_name': 'Test',
            'last_name': 'User'
        }
        response = self.client.post(self.register_url, valid_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Try to create another user with same username
        duplicate_data = valid_data.copy()
        duplicate_data['phone_number'] = '9876543213'  # Different phone
        duplicate_data['email'] = 'test2@example.com'  # Different email
        response = self.client.post(self.register_url, duplicate_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('username', response.data)

    def test_registration_with_invalid_referral(self):
        """Test registration with invalid referral code"""
        data = {
            'username': 'newuser',
            'phone_number': '9876543212',
            'email': 'newuser@test.com',
            'password': 'testpass123',
            'confirm_password': 'testpass123',
            'terms_accepted': True,
            'first_name': 'New',
            'last_name': 'User',
            'referral_code': 'INVALID'
        }
        response = self.client.post(self.register_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

class UserLoginTests(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.login_url = reverse('user-login')
        self.user_data = {
            'phone_number': '9876543210',
            'password': 'testpass123'
        }
        self.user = User.objects.create_user(**self.user_data)
        cache.clear()

    def test_login_with_phone(self):
        """Test login with phone number"""
        cache.clear()
        data = {
            'phone_number': self.user_data['phone_number']
        }
        response = self.client.post(self.login_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('verificationId', response.data)

    def test_failed_login_attempts(self):
        """Test failed login attempts and rate limiting"""
        # Clear cache and set up throttle key
        cache.clear()
        data = {
            'login_field': self.user_data['username'],
            'password': 'wrongpassword'
        }
        
        # Make 5 failed attempts
        for _ in range(5):
            response = self.client.post(self.login_url, data, format='json')
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        
        # Next attempt should be rate limited
        response = self.client.post(self.login_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn('lockout_minutes', response.data)

    def test_login_with_inactive_user(self):
        """Test login with inactive user"""
        self.user.is_active = False
        self.user.save()
        
        data = {
            'login_field': self.user_data['username'],
            'password': self.user_data['password']
        }
        response = self.client.post(self.login_url, data, format='json')
        # The API returns 401 for inactive users instead of 403
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('error', response.data)

class UserInfoTests(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.user_data = {
            'username': 'testuser',
            'phone_number': '9876543210',
            'email': 'test@example.com',
            'password': 'testpass123'
        }
        self.user = User.objects.create_user(**self.user_data)
        self.client.force_authenticate(user=self.user)
        self.info_url = reverse('user-info')

    def test_get_user_info(self):
        """Test getting authenticated user info"""
        response = self.client.get(self.info_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # The API returns user info in a nested 'user' object
        self.assertEqual(response.data['user']['username'], self.user_data['username'])
        self.assertEqual(response.data['user']['email'], self.user_data['email'])
        self.assertEqual(response.data['user']['phone_number'], f"+91{self.user_data['phone_number']}")

    def test_unauthenticated_access(self):
        """Test accessing user info without authentication"""
        self.remove_authentication()
        response = self.client.get(self.info_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

class ReferralTests(BaseAPITest):
    def setUp(self):
        super().setUp()
        # Create referrer
        self.referrer_data = {
            'username': 'referrer',
            'phone_number': '9876543210',
            'email': 'referrer@example.com',
            'password': 'testpass123'
        }
        self.referrer = User.objects.create_user(**self.referrer_data)
        
        # Create user to apply referral
        self.user_data = {
            'username': 'testuser',
            'phone_number': '9876543211',
            'email': 'test@example.com',
            'password': 'testpass123'
        }
        self.user = User.objects.create_user(**self.user_data)
        
        self.client.force_authenticate(user=self.user)
        self.apply_referral_url = reverse('apply-referral')

    def test_apply_valid_referral(self):
        """Test applying a valid referral code"""
        data = {'referral_code': self.referrer.referral_code}
        response = self.client.post(self.apply_referral_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify referral was recorded
        self.assertTrue(
            ReferralUsage.objects.filter(
                referrer=self.referrer,
                referred_user=self.user
            ).exists()
        )
        
        # Verify wallet bonuses (initial balance 1000 + referral bonus)
        referrer_wallet = Wallet.objects.get(user=self.referrer)
        user_wallet = Wallet.objects.get(user=self.user)
        self.assertEqual(referrer_wallet.balance, Decimal('1050.00'))
        self.assertEqual(user_wallet.balance, Decimal('1030.00'))

    def test_apply_invalid_referral(self):
        """Test applying an invalid referral code"""
        data = {'referral_code': 'INVALID'}
        response = self.client.post(self.apply_referral_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_apply_own_referral(self):
        """Test applying own referral code"""
        data = {'referral_code': self.user.referral_code}
        response = self.client.post(self.apply_referral_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_apply_referral_twice(self):
        """Test applying referral code twice"""
        data = {'referral_code': self.referrer.referral_code}
        
        # First application
        response = self.client.post(self.apply_referral_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Second application
        response = self.client.post(self.apply_referral_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

class PasswordResetTests(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.user_data = {
            'username': 'testuser',
            'phone_number': '9876543210',
            'email': 'test@example.com',
            'password': 'testpass123'
        }
        self.user = User.objects.create_user(**self.user_data)
        self.forgot_password_url = reverse('forgot-password')
        self.reset_password_url = reverse('reset-password')

    def test_forgot_password_request(self):
        """Test requesting password reset"""
        data = {'email': self.user_data['email']}
        response = self.client.post(self.forgot_password_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.user_data['email'], mail.outbox[0].to)

    def test_reset_password_with_otp(self):
        """Test resetting password with OTP"""
        # First request password reset
        data = {'email': self.user_data['email']}
        response = self.client.post(self.forgot_password_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Get OTP from user object
        self.user.refresh_from_db()
        otp = self.user.reset_password_token
        
        # Reset password with OTP
        reset_data = {
            'email': self.user_data['email'],
            'otp': otp,  # API expects 'otp' instead of 'token'
            'new_password': 'newpass123'
        }
        response = self.client.post(self.reset_password_url, reset_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify new password works
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('newpass123'))

    def test_reset_password_with_invalid_otp(self):
        """Test resetting password with invalid OTP"""
        reset_data = {
            'email': self.user_data['email'],
            'otp': '123456',  # API expects 'otp' instead of 'token'
            'new_password': 'newpass123'
        }
        response = self.client.post(self.reset_password_url, reset_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reset_password_rate_limiting(self):
        """Test rate limiting for password reset requests"""
        data = {'email': self.user_data['email']}
        
        # Make multiple requests
        for _ in range(3):
            response = self.client.post(self.forgot_password_url, data, format='json')
            self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Next request should be rate limited
        response = self.client.post(self.forgot_password_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
