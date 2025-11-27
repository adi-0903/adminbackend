from django.test import TransactionTestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from decimal import Decimal
from unittest.mock import patch, MagicMock
import json
from django.utils import timezone
from datetime import timedelta
from django.conf import settings
import razorpay
from rest_framework import serializers

from .models import Wallet, WalletTransaction
from .serializers import WalletSerializer, WalletTransactionSerializer, AddMoneySerializer
from .views import calculate_bonus_amount

User = get_user_model()

class BaseTestCase(TransactionTestCase):
    def setUp(self):
        self.client = APIClient()

class WalletModelTests(TransactionTestCase):
    def test_wallet_creation(self):
        """Test wallet creation and string representation"""
        user = User.objects.create_user(
            username='wallet_creation_test_user',
            password='testpass123',
            phone_number='9876543210'
        )
        # Wallet should be created automatically by signal
        wallet = user.wallet
        self.assertEqual(str(wallet), "wallet_creation_test_user's Wallet - ₹1000")
        self.assertTrue(wallet.is_active)
        self.assertFalse(wallet.is_deleted)

    def test_create_wallet_with_welcome_bonus(self):
        """Test wallet creation with welcome bonus"""
        with self.settings(WALLET_WELCOME_BONUS={
            'ENABLED': True,
            'AMOUNT': 1000,
            'DESCRIPTION': 'Welcome bonus'
        }):
            user = User.objects.create_user(
                username='welcome_bonus_test_user',
                password='testpass123',
                phone_number='9876543211'
            )
            # Wallet should be created automatically with welcome bonus
            wallet = user.wallet
            self.assertEqual(wallet.balance, Decimal('1000.00'))
            
            # Verify transaction was created
            transaction = WalletTransaction.objects.filter(wallet=wallet).first()
            self.assertIsNotNone(transaction)
            self.assertEqual(transaction.amount, Decimal('1000.00'))
            self.assertEqual(transaction.transaction_type, 'CREDIT')
            self.assertEqual(transaction.status, 'SUCCESS')
            self.assertEqual(transaction.description, 'Welcome bonus')

    def test_wallet_balance_operations(self):
        """Test wallet balance operations"""
        user = User.objects.create_user(
            username='balance_operations_test_user',
            password='testpass123',
            phone_number='9876543212'
        )
        wallet = user.wallet
        initial_balance = wallet.balance
        
        # Test add_balance
        wallet.add_balance('500.00')
        self.assertEqual(wallet.balance, initial_balance + Decimal('500.00'))
        
        # Test subtract_balance
        wallet.subtract_balance('300.00')
        self.assertEqual(wallet.balance, initial_balance + Decimal('200.00'))
        
        # Test set_balance
        wallet.set_balance('2000.00')
        self.assertEqual(wallet.balance, Decimal('2000.00'))
        
        # Test invalid operations
        with self.assertRaises(ValueError):
            wallet.add_balance('-100.00')
        
        with self.assertRaises(ValueError):
            wallet.subtract_balance('-100.00')
        
        with self.assertRaises(ValueError):
            wallet.subtract_balance('3000.00')  # Insufficient balance
        
        with self.assertRaises(ValueError):
            wallet.set_balance('-100.00')

    def test_soft_deletion(self):
        """Test soft deletion of wallet"""
        user = User.objects.create_user(
            username='wallet_deletion_test_user',
            password='testpass123',
            phone_number='9876543213'
        )
        wallet = user.wallet
        wallet.soft_delete()
        self.assertFalse(wallet.is_active)
        self.assertTrue(wallet.is_deleted)
        self.assertFalse(Wallet.objects.filter(user=user).exists())
        self.assertTrue(Wallet.all_objects.filter(user=user).exists())

class WalletTransactionModelTests(TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            username='transaction_test_user',
            password='testpass123',
            phone_number='9876543214'
        )
        self.wallet = self.user.wallet

    def test_transaction_creation(self):
        """Test transaction creation and string representation"""
        transaction = WalletTransaction.objects.create(
            wallet=self.wallet,
            amount=Decimal('500.00'),
            transaction_type='CREDIT',
            status='SUCCESS',
            description='Test transaction'
        )
        self.assertEqual(
            str(transaction),
            "transaction_test_user - CREDIT - ₹500.00"
        )
        self.assertFalse(transaction.is_deleted)

    def test_transaction_validation(self):
        """Test transaction validation"""
        # Test invalid amount
        with self.assertRaises(ValueError):
            WalletTransaction.objects.create(
                wallet=self.wallet,
                amount=Decimal('-100.00'),
                transaction_type='CREDIT',
                status='SUCCESS'
            )
        
        # Test invalid transaction type
        with self.assertRaises(ValueError):
            WalletTransaction.objects.create(
                wallet=self.wallet,
                amount=Decimal('100.00'),
                transaction_type='INVALID',
                status='SUCCESS'
            )
        
        # Test invalid status
        with self.assertRaises(ValueError):
            WalletTransaction.objects.create(
                wallet=self.wallet,
                amount=Decimal('100.00'),
                transaction_type='CREDIT',
                status='INVALID'
            )

    def test_soft_deletion(self):
        """Test soft deletion of transaction"""
        transaction = WalletTransaction.objects.create(
            wallet=self.wallet,
            amount=Decimal('500.00'),
            transaction_type='CREDIT',
            status='SUCCESS',
            description='Test transaction'
        )
        transaction.soft_delete()
        self.assertTrue(transaction.is_deleted)
        self.assertFalse(WalletTransaction.objects.filter(id=transaction.id).exists())
        self.assertTrue(WalletTransaction.all_objects.filter(id=transaction.id).exists())

class WalletAPITests(TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            username='api_test_user',
            password='testpass123',
            phone_number='9876543217'
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.wallet = self.user.wallet

    def test_get_wallet_info(self):
        """Test getting wallet information"""
        url = reverse('wallet-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(response.data['balance']), self.wallet.balance)

    @patch('wallet.serializers.AddMoneySerializer.validate_amount')
    @patch('wallet.views.WalletViewSet._get_razorpay_client')
    def test_add_money_validation(self, mock_razorpay, mock_validate_amount):
        """Test add money validation"""
        url = reverse('wallet-add-money')
        
        # Mock Razorpay client
        mock_client = MagicMock()
        mock_razorpay.return_value = mock_client
        
        # Test Razorpay validation error
        mock_validate_amount.return_value = Decimal('500.00')  # Return valid amount
        mock_client.payment_link.create.side_effect = razorpay.errors.BadRequestError('Invalid amount')
        
        response = self.client.post(url, {'amount': '500.00'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertEqual(mock_client.payment_link.create.call_count, 3)  # Should be called 3 times due to retry logic
        
        # Reset mocks for validation tests
        mock_client.payment_link.create.reset_mock()
        
        # Test invalid amount (negative)
        mock_validate_amount.side_effect = serializers.ValidationError('Amount must be positive')
        response = self.client.post(url, {'amount': '-100.00'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('amount', response.data)
        mock_client.payment_link.create.assert_not_called()
        
        # Test amount below minimum
        mock_validate_amount.side_effect = serializers.ValidationError('Amount must be at least ₹10')
        response = self.client.post(url, {'amount': '9.00'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('amount', response.data)
        mock_client.payment_link.create.assert_not_called()
        
        # Test amount above maximum
        mock_validate_amount.side_effect = serializers.ValidationError('Amount cannot exceed ₹100,000')
        response = self.client.post(url, {'amount': '100001.00'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('amount', response.data)
        mock_client.payment_link.create.assert_not_called()

    @patch('wallet.views.WalletViewSet._get_razorpay_client')
    def test_add_money_success(self, mock_razorpay):
        """Test successful money addition"""
        # Mock Razorpay client
        mock_client = MagicMock()
        mock_client.payment_link.create.return_value = {
            'id': 'plink_123',
            'short_url': 'https://rzp.io/i/xyz',
            'amount': 50000,
            'currency': 'INR'
        }
        mock_razorpay.return_value = mock_client
        
        url = reverse('wallet-add-money')
        response = self.client.post(url, {'amount': '500.00'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['payment_link'], 'https://rzp.io/i/xyz')
        self.assertEqual(response.data['amount'], '500.00')

class WalletTransactionAPITests(TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            username='transaction_api_test_user',
            password='testpass123',
            phone_number='9876543220'
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.wallet = self.user.wallet

        # Clear all transactions and reset wallet balance
        WalletTransaction.objects.all().delete()
        self.wallet.set_balance('0.00')

    def test_get_transaction_list(self):
        """Test getting transaction list"""
        # Create some test transactions
        credit_tx = WalletTransaction.objects.create(
            wallet=self.wallet,
            amount=Decimal('500.00'),
            transaction_type='CREDIT',
            status='SUCCESS',
            description='Test credit transaction'
        )
        debit_tx = WalletTransaction.objects.create(
            wallet=self.wallet,
            amount=Decimal('200.00'),
            transaction_type='DEBIT',
            status='SUCCESS',
            description='Test debit transaction'
        )
        
        url = reverse('wallet-transactions')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify response structure
        self.assertIn('results', response.data)
        transactions = response.data['results']
        
        # Verify only our test transactions are returned
        self.assertEqual(len(transactions), 2)
        
        # Transactions should be ordered by created_at descending
        self.assertEqual(transactions[0]['id'], debit_tx.id)
        self.assertEqual(Decimal(transactions[0]['amount']), Decimal('200.00'))
        self.assertEqual(transactions[0]['transaction_type'], 'DEBIT')
        self.assertEqual(transactions[0]['description'], 'Test debit transaction')
        
        self.assertEqual(transactions[1]['id'], credit_tx.id)
        self.assertEqual(Decimal(transactions[1]['amount']), Decimal('500.00'))
        self.assertEqual(transactions[1]['transaction_type'], 'CREDIT')
        self.assertEqual(transactions[1]['description'], 'Test credit transaction')

    def test_get_transaction_detail(self):
        """Test getting transaction detail"""
        transaction = WalletTransaction.objects.create(
            wallet=self.wallet,
            amount=Decimal('500.00'),
            transaction_type='CREDIT',
            status='SUCCESS',
            description='Test transaction'
        )
        
        url = reverse('wallet-transaction-detail', args=[transaction.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(response.data['amount']), Decimal('500.00'))
        self.assertEqual(response.data['transaction_type'], 'CREDIT')

class BonusCalculationTests(TransactionTestCase):
    def test_bonus_calculation(self):
        """Test bonus calculation for different amounts"""
        test_cases = [
            (Decimal('50.00'), (Decimal('0'), None)),  # No bonus for amount < 500
            (Decimal('500.00'), (Decimal('25.0000'), '5% bonus on recharge between ₹500-₹999')),  # 5% bonus for 500 <= amount < 1000
            (Decimal('2000.00'), (Decimal('200.0000'), '10% bonus on recharge above ₹1000')),  # 10% bonus for amount >= 1000
            (Decimal('5000.00'), (Decimal('500.0000'), '10% bonus on recharge above ₹1000'))  # 10% bonus for amount >= 1000
        ]
        
        for amount, expected_result in test_cases:
            with self.subTest(amount=amount):
                result = calculate_bonus_amount(amount)
                self.assertEqual(result, expected_result)

