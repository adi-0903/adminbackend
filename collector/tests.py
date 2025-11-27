from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from datetime import timedelta
from collector.serializers import CollectionListSerializer
from django.core.exceptions import ValidationError
from django.core.cache import cache

from .models import (
    Customer,
    MarketMilkPrice,
    DairyInformation,
    Collection
)
from wallet.models import Wallet
from .serializers import (
    CustomerSerializer,
    CollectionDetailSerializer,
    MarketMilkPriceSerializer,
    DairyInformationSerializer
)

User = get_user_model()

class BaseTestCase(APITestCase):
    def setUp(self):
        # Create a unique test user for each test using a counter
        timestamp = timezone.now().strftime('%H%M%S')
        last_4_digits = timestamp[-4:]  # Take only the last 4 digits
        try:
            self.user = User.objects.create_user(
                username=f'testuser_{timestamp}',
                password='testpass123',
                phone_number=f'987654{last_4_digits}'  # This will be exactly 10 digits
            )
            self.client = APIClient()
            self.client.force_authenticate(user=self.user)
            
            # Delete any existing wallet for this user (shouldn't exist, but just in case)
            Wallet.objects.filter(user=self.user).delete()
            
            # Create wallet with error handling
            self.wallet = Wallet.objects.create(
                user=self.user,
                balance=Decimal('10000.00')
            )
            
            self.customer = Customer.objects.create(
                name='Test Customer',
                phone=f'987654{last_4_digits}',  # Changed from phone_number to phone
                author=self.user
            )
            
            self.market_milk_price = MarketMilkPrice.objects.create(
                author=self.user,
                price=Decimal('50.00')  # Changed to use only the price field
            )
            
            self.dairy_information = DairyInformation.objects.create(
                author=self.user,
                dairy_name='Test Dairy',
                dairy_address='Test Dairy Address',
                rate_type='fat_snf',  # Added required field
                is_active=True
            )
        except Exception as e:
            # Clean up if any creation fails
            self.tearDown()
            raise
        
    def tearDown(self):
        try:
            if hasattr(self, 'user'):
                # Delete all related objects first
                Collection.objects.filter(author=self.user).delete()
                DairyInformation.objects.filter(author=self.user).delete()
                MarketMilkPrice.objects.filter(author=self.user).delete()
                Customer.objects.filter(author=self.user).delete()
                
                # Delete wallet before user
                if hasattr(self, 'wallet'):
                    self.wallet.delete()
                else:
                    # Just in case wallet exists but isn't attached to self
                    Wallet.objects.filter(user=self.user).delete()
                
                # Delete user last
                self.user.delete()
                
                # Clear instance attributes
                if hasattr(self, 'wallet'):
                    delattr(self, 'wallet')
                delattr(self, 'user')
        except Exception as e:
            print(f"Error in tearDown: {e}")

class ModelTests(BaseTestCase):
    def test_customer_model(self):
        customer = Customer.objects.create(
            author=self.user,
            name='New Customer',
            phone='9876543211'
        )
        self.assertEqual(customer.phone, '+919876543211')
        self.assertTrue(customer.is_active)
        self.assertEqual(str(customer), 'New Customer')

    def test_customer_phone_formatting(self):
        # Test with different phone number formats
        test_cases = [
            ('9876543211', '+919876543211'),  # Regular number
            ('09876543211', '+919876543211'),  # With leading zero
            ('+919876543211', '+919876543211'),  # Already has +91
            ('919876543211', '+919876543211'),  # Has 91 prefix without +
        ]
        for input_phone, expected_phone in test_cases:
            with self.subTest(input_phone=input_phone):
                customer = Customer.objects.create(
                    author=self.user,
                    name='Phone Test Customer',
                    phone=input_phone
                )
                self.assertEqual(customer.phone, expected_phone)
                customer.delete()

    def test_market_milk_price_model(self):
        price = MarketMilkPrice.objects.create(
            author=self.user,
            price=Decimal('55.50')
        )
        self.assertEqual(str(price), '55.50')
        self.assertTrue(price.is_active)
        
        # Test single active price policy
        new_price = MarketMilkPrice.objects.create(
            author=self.user,
            price=Decimal('60.00')
        )
        price.refresh_from_db()
        self.assertFalse(price.is_active)
        self.assertTrue(new_price.is_active)

    def test_dairy_information_model(self):
        dairy = DairyInformation.objects.create(
            author=self.user,
            dairy_name='New Dairy',
            dairy_address='New Address',
            rate_type='fat_only'
        )
        self.assertEqual(str(dairy), 'New Dairy')
        self.assertTrue(dairy.is_active)
        
        # Test single active dairy info policy
        new_dairy = DairyInformation.objects.create(
            author=self.user,
            dairy_name='Another Dairy',
            dairy_address='Another Address',
            rate_type='fat_snf'
        )
        dairy.refresh_from_db()
        self.assertFalse(dairy.is_active)
        self.assertTrue(new_dairy.is_active)

    def test_collection_model(self):
        collection = Collection.objects.create(
            author=self.user,
            collection_time='morning',
            milk_type='cow',
            customer=self.customer,
            collection_date=timezone.now().date(),
            measured='liters',
            liters=Decimal('10.00'),
            kg=Decimal('10.30'),
            fat_percentage=Decimal('4.5'),
            fat_kg=Decimal('0.45'),
            clr=Decimal('27.0'),
            snf_percentage=Decimal('9.0'),
            snf_kg=Decimal('0.90'),
            milk_rate=Decimal('50.00'),
            amount=Decimal('500.00')
        )
        self.assertTrue(collection.is_active)
        self.assertEqual(
            str(collection),
            f"{self.customer.name} - {collection.collection_date} morning"
        )

    def test_soft_deletion(self):
        # Test soft deletion for all models
        self.customer.soft_delete()
        self.assertFalse(Customer.objects.filter(id=self.customer.id).exists())
        self.assertTrue(Customer.all_objects.filter(id=self.customer.id).exists())
        
        self.market_milk_price.soft_delete()
        self.assertFalse(MarketMilkPrice.objects.filter(id=self.market_milk_price.id).exists())
        self.assertTrue(MarketMilkPrice.all_objects.filter(id=self.market_milk_price.id).exists())
        
        self.dairy_information.soft_delete()
        self.assertFalse(DairyInformation.objects.filter(id=self.dairy_information.id).exists())
        self.assertTrue(DairyInformation.all_objects.filter(id=self.dairy_information.id).exists())

class APITests(BaseTestCase):
    def test_customer_list(self):
        url = reverse('customer-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        
        # Test search
        response = self.client.get(f"{url}?search=Test")
        self.assertEqual(len(response.data['results']), 1)
        response = self.client.get(f"{url}?search=NonExistent")
        self.assertEqual(len(response.data['results']), 0)

    def test_customer_create(self):
        url = reverse('customer-list')
        data = {
            'name': 'New Customer',
            'father_name': 'New Customer',
            'phone': '9876543211',
            'village': 'New Village',
            'address': 'New Address'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['phone'], '+919876543211')
        
        # Test duplicate phone
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Test invalid phone
        data['phone'] = '123'
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        # Test empty name
        data['name'] = ''
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_customer_update(self):
        url = reverse('customer-detail', args=[self.customer.id])
        data = {
            'name': 'Updated Customer',
            'father_name': 'Updated Customer',
            'phone': '9876543212',
            'village': 'Updated Village',
            'address': 'Updated Address'
        }
        response = self.client.put(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Updated Customer')
        self.assertEqual(response.data['phone'], '+919876543212')
        
        # Test partial update
        response = self.client.patch(url, {'name': 'Partially Updated'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Partially Updated')

    def test_market_milk_price_list(self):
        url = reverse('market-milk-price-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(response.data['price']), Decimal('50.00'))

    def test_market_milk_price_create(self):
        url = reverse('market-milk-price-list')
        data = {
            'price': '55.50'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Decimal(response.data['price']), Decimal('55.50'))
        
        # Verify previous price is inactive
        self.market_milk_price.refresh_from_db()
        self.assertFalse(self.market_milk_price.is_active)
        
        # Test invalid price
        data['price'] = '-1.00'
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_dairy_information_list(self):
        url = reverse('dairy-information-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['dairy_name'], 'Test Dairy')

    def test_dairy_information_create(self):
        url = reverse('dairy-information-list')
        data = {
            'dairy_name': 'New Dairy',
            'dairy_address': 'New Address',
            'rate_type': 'fat_only'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['dairy_name'], 'New Dairy')
        
        # Test duplicate name - should be allowed but deactivate old dairy
        old_dairy = DairyInformation.objects.get(dairy_name='New Dairy')
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['dairy_name'], 'New Dairy')
        
        # Verify old dairy is now inactive
        old_dairy.refresh_from_db()
        self.assertFalse(old_dairy.is_active)
        
        # Test invalid rate type
        data['rate_type'] = 'invalid'
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

class CollectionAPITests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.collection_data = {
            'collection_time': 'morning',
            'milk_type': 'cow',
            'customer': self.customer.id,
            'collection_date': timezone.now().date().isoformat(),
            'measured': 'liters',
            'liters': '10.00',
            'kg': '10.30',
            'fat_percentage': '4.5',
            'fat_kg': '0.45',
            'clr': '27.0',
            'snf_percentage': '9.0',
            'snf_kg': '0.90',
            'milk_rate': '50.00',
            'amount': '500.00',
            'base_snf_percentage': '9.0'
        }

    def _create_test_collection(self):
        """Helper method to create a test collection"""
        return Collection.objects.create(
            author=self.user,
            collection_time='morning',
            milk_type='cow',
            customer=self.customer,
            collection_date=timezone.now().date(),
            measured='liters',
            liters=Decimal('10.000'),
            kg=Decimal('10.300'),
            fat_percentage=Decimal('4.500'),
            fat_kg=Decimal('0.450'),
            clr=Decimal('27.000'),
            snf_percentage=Decimal('9.000'),
            snf_kg=Decimal('0.900'),
            milk_rate=Decimal('50.000'),
            amount=Decimal('500.000')
        )

    def test_collection_create(self):
        url = reverse('collection-list')
        self.collection_data = {
            'collection_time': 'morning',
            'milk_type': 'cow',
            'customer': self.customer.id,
            'collection_date': timezone.now().date().isoformat(),
            'measured': 'liters',
            'liters': '10.00',
            'kg': '10.30',
            'fat_percentage': '4.5',
            'fat_kg': '0.45',
            'clr': '27.0',
            'snf_percentage': '9.0',
            'snf_kg': '0.90',
            'milk_rate': '50.00',
            'amount': '500.00',
            'base_fat_percentage': '6.5',
            'base_snf_percentage': '9.0'
        }
        
        response = self.client.post(url, self.collection_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Collection.objects.count(), 1)
        collection = Collection.objects.first()
        self.assertEqual(collection.customer, self.customer)
        self.assertEqual(collection.author, self.user)
        self.assertEqual(str(collection.amount), '500.000')  # Expect 3 decimal places
        
        # Test custom SNF percentage
        self.collection_data['base_snf_percentage'] = '9.5'
        response = self.client.post(url, self.collection_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Test invalid SNF percentage
        self.collection_data['base_snf_percentage'] = '9.6'
        response = self.client.post(url, self.collection_data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_collection_list_and_filter(self):
        # Create test collections
        Collection.objects.create(
            author=self.user,
            collection_time='morning',
            milk_type='cow',
            customer=self.customer,
            collection_date=timezone.now().date(),
            measured='liters',
            liters=Decimal('10.00'),
            kg=Decimal('10.30'),
            fat_percentage=Decimal('4.5'),
            fat_kg=Decimal('0.45'),
            clr=Decimal('27.0'),
            snf_percentage=Decimal('9.0'),
            snf_kg=Decimal('0.90'),
            milk_rate=Decimal('50.00'),
            amount=Decimal('500.00')
        )
        
        url = reverse('collection-list')
        
        # Test basic list
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        
        # Test date filter
        today = timezone.now().date()
        response = self.client.get(f"{url}?date_from={today}&date_to={today}")
        self.assertEqual(len(response.data['results']), 1)
        
        # Test collection time filter
        response = self.client.get(f"{url}?collection_time=morning")
        self.assertEqual(len(response.data['results']), 1)
        response = self.client.get(f"{url}?collection_time=evening")
        self.assertEqual(len(response.data['results']), 0)
        
        # Test milk type filter
        response = self.client.get(f"{url}?milk_type=cow")
        self.assertEqual(len(response.data['results']), 1)
        response = self.client.get(f"{url}?milk_type=buffalo")
        self.assertEqual(len(response.data['results']), 0)
        
        # Test customer filter
        response = self.client.get(f"{url}?customer={self.customer.id}")
        self.assertEqual(len(response.data['results']), 1)
        
        # Test amount range filter
        response = self.client.get(f"{url}?min_amount=400&max_amount=600")
        self.assertEqual(len(response.data['results']), 1)
        response = self.client.get(f"{url}?min_amount=600")
        self.assertEqual(len(response.data['results']), 0)

    def test_collection_create_insufficient_balance(self):
        # Enable collection fee in settings for this test
        with self.settings(COLLECTION_FEE={'ENABLED': True, 'PER_KG_RATE': 0.02}):
            # Calculate expected deduction for the collection
            expected_deduction = Decimal('10.30') * Decimal('0.02')  # kg * rate
            
            # Set wallet balance slightly below what's needed
            self.wallet.balance = expected_deduction - Decimal('0.01')
            self.wallet.save()

            url = reverse('collection-list')
            response = self.client.post(url, self.collection_data)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('Insufficient wallet balance', response.data['error'])
            
            # Now set sufficient balance and verify it works
            self.wallet.balance = expected_deduction
            self.wallet.save()
            response = self.client.post(url, self.collection_data)
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            
            # Test with higher rate
            with self.settings(COLLECTION_FEE={'ENABLED': True, 'PER_KG_RATE': 0.05}):
                # New collection with different kg
                new_data = self.collection_data.copy()
                new_data['kg'] = '20.00'
                expected_deduction = Decimal('20.00') * Decimal('0.05')  # kg * rate
                
                # Set wallet balance slightly below what's needed
                self.wallet.balance = expected_deduction - Decimal('0.01')
                self.wallet.save()
                
                response = self.client.post(url, new_data)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn('Insufficient wallet balance', response.data['error'])

    def test_collection_update(self):
        # Create a collection first
        collection = Collection.objects.create(
            author=self.user,
            collection_time='morning',
            milk_type='cow',
            customer=self.customer,
            collection_date=timezone.now().date(),
            measured='liters',
            liters=Decimal('10.00'),
            kg=Decimal('10.30'),
            fat_percentage=Decimal('4.5'),
            fat_kg=Decimal('0.45'),
            clr=Decimal('27.0'),
            snf_percentage=Decimal('9.0'),
            snf_kg=Decimal('0.90'),
            milk_rate=Decimal('50.00'),
            amount=Decimal('500.00'),
            base_fat_percentage=Decimal('6.5'),
            base_snf_percentage=Decimal('9.0')
        )
        
        url = reverse('collection-detail', args=[collection.id])
        update_data = self.collection_data.copy()
        update_data['amount'] = '600.00'
        
        # Test full update
        response = self.client.put(url, update_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(response.data['amount']), Decimal('600.00'))
        
        # Test partial update
        response = self.client.patch(url, {'amount': '700.00'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(response.data['amount']), Decimal('700.00'))

    def test_generate_report(self):
        """Test report generation endpoint"""
        # Test with missing parameters
        response = self.client.get(reverse('collection-generate-purchase-report'))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['error'], 'start_date and end_date are required query parameters')

        # Test with invalid date format
        future_date = timezone.now().date() + timezone.timedelta(days=1)
        response = self.client.get(
            reverse('collection-generate-purchase-report') + 
            f'?start_date=invalid&end_date={future_date.strftime("%d-%m-%Y")}'
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['error'], 'Invalid date format. Use DD-MM-YYYY')

        # Test with no collections
        yesterday = timezone.now().date() - timezone.timedelta(days=1)
        response = self.client.get(
            reverse('collection-generate-purchase-report') + 
            f'?start_date={yesterday.strftime("%d-%m-%Y")}&end_date={future_date.strftime("%d-%m-%Y")}'
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data['error'], 'No collections found for the specified date range')

        # Test successful report generation
        collection = self._create_test_collection()
        response = self.client.get(
            reverse('collection-generate-purchase-report') + 
            f'?start_date={yesterday.strftime("%d-%m-%Y")}&end_date={future_date.strftime("%d-%m-%Y")}'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn(f'attachment; filename="milk_purchase_report_{yesterday.strftime("%d-%m-%Y")}_to_{future_date.strftime("%d-%m-%Y")}.pdf"', 
                     response['Content-Disposition'])

    def test_generate_customer_report(self):
        # Create test collections
        today = timezone.now().date()
        yesterday = today - timedelta(days=1)
        
        Collection.objects.create(
            author=self.user,
            collection_time='morning',
            milk_type='cow',
            customer=self.customer,
            collection_date=today,
            measured='liters',
            liters=Decimal('10.000'),
            kg=Decimal('10.300'),
            fat_percentage=Decimal('4.500'),
            fat_kg=Decimal('0.463'),
            clr=Decimal('27.000'),
            snf_percentage=Decimal('9.000'),
            snf_kg=Decimal('0.927'),
            milk_rate=Decimal('50.000'),
            amount=Decimal('500.000')
        )
        
        url = reverse('collection-generate-customer-report')
        
        # Test valid request with DD-MM-YYYY format
        response = self.client.get(
            f"{url}?start_date={today.strftime('%d-%m-%Y')}&end_date={today.strftime('%d-%m-%Y')}&customer_ids={self.customer.id}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        
        # Verify PDF was generated with content
        self.assertTrue(len(response.content) > 0)
        self.assertTrue(response.content.startswith(b'%PDF'))
        
        # Test invalid customer ID
        response = self.client.get(
            f"{url}?start_date={today.strftime('%d-%m-%Y')}&end_date={today.strftime('%d-%m-%Y')}&customer_ids=999"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)  # Changed to 404 since customer not found
        
        # Test missing parameters
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_collection_validation(self):
        """Test collection validation rules"""
        # Test invalid base SNF percentage
        invalid_data = self.collection_data.copy()
        invalid_data['customer'] = self.customer  # Use actual customer object instead of ID
        invalid_data['base_snf_percentage'] = Decimal('8.500')  # Below minimum
        collection = Collection(author=self.user, **invalid_data)
        with self.assertRaises(ValidationError):
            collection.full_clean()

        invalid_data['base_snf_percentage'] = Decimal('9.600')  # Above maximum
        collection = Collection(author=self.user, **invalid_data)
        with self.assertRaises(ValidationError):
            collection.full_clean()

    def test_collection_create_with_disabled_fee(self):
        # Disable collection fee in settings for this test
        with self.settings(COLLECTION_FEE={'ENABLED': False, 'PER_KG_RATE': 0.02}):
            # Set wallet balance to 0
            self.wallet.balance = Decimal('0.00')
            self.wallet.save()

            url = reverse('collection-list')
            response = self.client.post(url, self.collection_data)
            # Should succeed even with zero balance since fee is disabled
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

class SerializerTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        # Create a mock request with user
        self.request = type('Request', (), {'user': self.user})
        self.serializer_context = {'request': self.request}

    def test_customer_serializer(self):
        data = {
            'name': 'Test Customer',
            'phone': '9876543210'
        }
        serializer = CustomerSerializer(data=data, context=self.serializer_context)
        self.assertTrue(serializer.is_valid())
        customer = serializer.save()
        self.assertEqual(customer.phone, '+919876543210')

    def test_customer_serializer_validation(self):
        # Test invalid phone number
        data = {
            'name': 'Test Customer',
            'phone': '123'
        }
        serializer = CustomerSerializer(data=data, context=self.serializer_context)
        self.assertFalse(serializer.is_valid())
        self.assertIn('phone', serializer.errors)
        
        # Test empty name
        data = {
            'name': '',
            'phone': '9876543210'
        }
        serializer = CustomerSerializer(data=data, context=self.serializer_context)
        self.assertFalse(serializer.is_valid())
        self.assertIn('name', serializer.errors)

    def test_collection_serializers(self):
        collection = Collection.objects.create(
            author=self.user,
            collection_time='morning',
            milk_type='cow',
            customer=self.customer,
            collection_date=timezone.now().date(),
            measured='liters',
            liters=Decimal('10.00'),
            kg=Decimal('10.30'),
            fat_percentage=Decimal('4.5'),
            fat_kg=Decimal('0.45'),
            clr=Decimal('27.0'),
            snf_percentage=Decimal('9.0'),
            snf_kg=Decimal('0.90'),
            milk_rate=Decimal('50.00'),
            amount=Decimal('500.00')
        )
        
        # Test list serializer
        list_serializer = CollectionListSerializer(collection, context=self.serializer_context)
        self.assertEqual(list_serializer.data['customer_name'], 'Test Customer')
        
        # Test detail serializer
        detail_serializer = CollectionDetailSerializer(collection, context=self.serializer_context)
        self.assertEqual(detail_serializer.data['customer'], self.customer.id)
        self.assertEqual(detail_serializer.data['customer_name'], 'Test Customer')

    def test_collection_serializer_validation(self):
        data = {
            'collection_time': 'invalid',
            'milk_type': 'cow',
            'customer': self.customer.id,
            'collection_date': timezone.now().date(),
            'measured': 'liters',
            'liters': '10.00',
            'kg': '10.30',
            'fat_percentage': '4.5',
            'fat_kg': '0.45',
            'clr': '27.0',
            'snf_percentage': '9.0',
            'snf_kg': '0.90',
            'milk_rate': '50.00',
            'amount': '500.00'
        }
        serializer = CollectionDetailSerializer(data=data, context=self.serializer_context)
        self.assertFalse(serializer.is_valid())
        self.assertIn('collection_time', serializer.errors)
        
        # Test invalid numeric values
        data['collection_time'] = 'morning'
        data['liters'] = '-1'
        serializer = CollectionDetailSerializer(data=data, context=self.serializer_context)
        self.assertFalse(serializer.is_valid())
        self.assertIn('liters', serializer.errors)
        
        # Test invalid percentage
        data['liters'] = '10.00'
        data['fat_percentage'] = '101'
        serializer = CollectionDetailSerializer(data=data, context=self.serializer_context)
        self.assertFalse(serializer.is_valid())
        self.assertIn('fat_percentage', serializer.errors)

    def test_market_price_serializer(self):
        data = {
            'price': '55.50'
        }
        serializer = MarketMilkPriceSerializer(data=data, context=self.serializer_context)
        self.assertTrue(serializer.is_valid())
        price = serializer.save()
        self.assertEqual(price.price, Decimal('55.50'))

    def test_market_price_serializer_validation(self):
        # Test negative price
        data = {
            'price': '-1.00'
        }
        serializer = MarketMilkPriceSerializer(data=data, context=self.serializer_context)
        self.assertFalse(serializer.is_valid())
        self.assertIn('price', serializer.errors)
        
        # Test zero price
        data['price'] = '0.00'
        serializer = MarketMilkPriceSerializer(data=data, context=self.serializer_context)
        self.assertFalse(serializer.is_valid())
        self.assertIn('price', serializer.errors)

    def test_dairy_information_serializer(self):
        data = {
            'dairy_name': 'New Test Dairy',  # Changed to avoid duplicate name
            'dairy_address': 'Test Address',
            'rate_type': 'fat_only'
        }
        serializer = DairyInformationSerializer(data=data, context=self.serializer_context)
        self.assertTrue(serializer.is_valid())
        dairy = serializer.save()
        self.assertEqual(dairy.dairy_name, 'New Test Dairy')

    def test_dairy_information_serializer_validation(self):
        # Test invalid rate type
        data = {
            'dairy_name': 'Test Dairy',
            'dairy_address': 'Test Address',
            'rate_type': 'invalid'
        }
        serializer = DairyInformationSerializer(data=data, context=self.serializer_context)
        self.assertFalse(serializer.is_valid())
        self.assertIn('rate_type', serializer.errors)
        
        # Test empty dairy name
        data = {
            'dairy_name': '',
            'dairy_address': 'Test Address',
            'rate_type': 'fat_only'
        }
        serializer = DairyInformationSerializer(data=data, context=self.serializer_context)
        self.assertFalse(serializer.is_valid())
        self.assertIn('dairy_name', serializer.errors)
        
        # Test duplicate dairy name
        data = {
            'dairy_name': 'Test Dairy',
            'dairy_address': 'Another Address',
            'rate_type': 'fat_only'
        }
        serializer = DairyInformationSerializer(data=data, context=self.serializer_context)
        self.assertFalse(serializer.is_valid())
        self.assertIn('dairy_name', serializer.errors)
