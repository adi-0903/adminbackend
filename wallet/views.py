from __future__ import annotations

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.conf import settings
from django.db import transaction
from django.db.models import F, QuerySet
from django.http import HttpRequest, HttpResponse
import razorpay
from decimal import Decimal, InvalidOperation
import logging
from rest_framework.pagination import PageNumberPagination
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
from django.core.cache import cache
import hashlib
import hmac
import uuid
from typing import Any, Dict, Optional, Tuple, Union, List
from rest_framework.throttling import UserRateThrottle
from django.utils import timezone
from datetime import timedelta
from rest_framework.views import APIView

from .models import Wallet, WalletTransaction
from .serializers import (
    WalletSerializer, 
    WalletTransactionSerializer,
    AddMoneySerializer,
    PaymentVerificationSerializer
)
from .services import complete_transaction_success, mark_transaction_failed


def _verify_razorpay_signature(payload: bytes, signature: str, secret: str) -> bool:
    generated_signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(generated_signature, signature)

# Configure logging
logger = logging.getLogger(__name__)

class AddMoneyRateThrottle(UserRateThrottle):
    rate = '100/minute'  # Limit to 10 requests per minute per user

def calculate_bonus_amount(amount: Union[Decimal, float, str, int]) -> Tuple[Decimal, Optional[str]]:
    """Calculate bonus amount based on the recharge amount."""
    amount = Decimal(str(amount))
    
    if amount >= Decimal('1000'):
        bonus_percentage = Decimal('0.10')  # 10% bonus
        bonus_description = "10% bonus on recharge above ₹1000"
    elif amount >= Decimal('500'):
        bonus_percentage = Decimal('0.05')  # 5% bonus
        bonus_description = "5% bonus on recharge between ₹500-₹999"
    else:
        return Decimal('0'), None
    
    bonus_amount = amount * bonus_percentage
    return bonus_amount, bonus_description

class StandardResultsSetPagination(PageNumberPagination):
    page_size: int = 50
    page_size_query_param: str = 'page_size'
    max_page_size: int = 1000

class WalletViewSet(viewsets.ModelViewSet):
    serializer_class = WalletSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post']
    pagination_class = StandardResultsSetPagination
    throttle_classes = [AddMoneyRateThrottle]  # Apply rate limiting

    def get_queryset(self) -> QuerySet:
        return Wallet.objects.filter(user=self.request.user).order_by('-created_at')

    def get_object(self) -> Optional[Wallet]:
        return self.get_queryset().first()

    def list(self, request: HttpRequest, *args: Any, **kwargs: Any) -> Response:
        wallet = self.get_object()
        serializer = self.get_serializer(wallet)
        return Response(serializer.data)

    def partial_update(self, request: HttpRequest, *args: Any, **kwargs: Any) -> Response:
        wallet = self.get_object()
        try:
            new_balance = Decimal(request.data.get('balance', 0))
            wallet.set_balance(new_balance)
            return Response(self.get_serializer(wallet).data)
        except (ValueError, TypeError) as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def _get_razorpay_client(self) -> razorpay.Client:
        """Create a Razorpay client with improved retry configuration"""
        retry_strategy = Retry(
            total=5,  # Increased retries
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504, 429],  # Added 429 for rate limiting
            allowed_methods=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"],
            respect_retry_after_header=True
        )

        session = requests.Session()
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
        session.mount("https://", adapter)

        return razorpay.Client(
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET),
            requests_session=session,
            timeout=30  # Set explicit timeout
        )

    @action(detail=False, methods=['post'])
    def add_money(self, request: HttpRequest) -> Response:
        """Create a Razorpay order for wallet top-up"""
        try:
            serializer = AddMoneySerializer(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            amount: Decimal = serializer.validated_data['amount']
            client = self._get_razorpay_client()

            with transaction.atomic():
                wallet = Wallet.objects.select_for_update().get(user=request.user)

                recent_pending = WalletTransaction.objects.filter(
                    wallet=wallet,
                    status='PENDING',
                    created_at__gte=timezone.now() - timedelta(minutes=30)
                ).count()

                if recent_pending >= 3:
                    return Response(
                        {'error': 'You have too many pending transactions. Please complete them first.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                receipt = f"wallet_{wallet.id}_{uuid.uuid4().hex[:8]}"
                order = client.order.create({
                    'amount': int(amount * 100),
                    'currency': 'INR',
                    'payment_capture': 1,
                    'receipt': receipt
                })

                logger.info(f"Created Razorpay order: id={order['id']} receipt={receipt}")

                bonus_amount, bonus_description = calculate_bonus_amount(amount)

                transaction_obj = WalletTransaction.objects.create(
                    wallet=wallet,
                    amount=amount,
                    transaction_type='CREDIT',
                    status='PENDING',
                    razorpay_order_id=order['id'],
                    description='Wallet Recharge'
                )

                if bonus_amount > 0:
                    WalletTransaction.objects.create(
                        wallet=wallet,
                        amount=bonus_amount,
                        transaction_type='CREDIT',
                        status='PENDING',
                        description=bonus_description,
                        parent_transaction=transaction_obj
                    )

            return Response({
                'order_id': order['id'],
                'amount': str(amount),
                'currency': order['currency'],
                'key_id': settings.RAZORPAY_KEY_ID
            })

        except razorpay.errors.BadRequestError as e:
            logger.warning(f"Razorpay error: {str(e)}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Wallet.DoesNotExist:
            return Response({'error': 'Wallet not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error in add_money: {str(e)}")
            return Response(
                {'error': 'Failed to create order. Please try again later.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'])
    def transactions(self, request: HttpRequest) -> Response:
        """Get paginated list of user's wallet transactions"""
        wallet = self.get_object()
        if not wallet:
            return Response({'error': 'Wallet not found'}, status=status.HTTP_404_NOT_FOUND)
            
        transactions = WalletTransaction.objects.filter(wallet=wallet).order_by('-created_at')
        page = self.paginate_queryset(transactions)
        
        if page is not None:
            serializer = WalletTransactionSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
            
        serializer = WalletTransactionSerializer(transactions, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def verify_payment(self, request: HttpRequest) -> Response:
        """Verify Razorpay order signature from mobile client"""
        serializer = PaymentVerificationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        order_id = serializer.validated_data['order_id']
        payment_id = serializer.validated_data['payment_id']
        signature = serializer.validated_data['signature']

        generated_signature = hmac.new(
            settings.RAZORPAY_KEY_SECRET.encode(),
            f"{order_id}|{payment_id}".encode(),
            hashlib.sha256
        ).hexdigest()

        if generated_signature != signature:
            logger.warning("Invalid Razorpay signature for order %s", order_id)
            mark_transaction_failed(order_id, reason='Signature verification failed')
            return Response({'error': 'Invalid signature'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            amount = serializer.validated_data.get('amount')
            captured_amount = Decimal(str(amount)) if amount is not None else Decimal('0.0')
        except (TypeError, ValueError, InvalidOperation):
            captured_amount = Decimal('0.0')

        wallet_transaction = complete_transaction_success(order_id, payment_id, captured_amount)
        if not wallet_transaction:
            return Response({'error': 'Transaction not found'}, status=status.HTTP_404_NOT_FOUND)

        return Response(WalletTransactionSerializer(wallet_transaction).data)

class WalletTransactionViewSet(viewsets.ModelViewSet):
    serializer_class = WalletTransactionSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post']
    pagination_class = StandardResultsSetPagination

    def get_queryset(self) -> QuerySet:
        """Get transactions for the authenticated user's wallet"""
        return WalletTransaction.objects.filter(
            wallet__user=self.request.user
        ).order_by('-created_at')

    @transaction.atomic
    def create(self, request: HttpRequest, *args: Any, **kwargs: Any) -> Response:
        """Create a new wallet transaction"""
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            wallet = Wallet.objects.select_for_update().get(user=request.user)
            amount = serializer.validated_data['amount']
            transaction_type = serializer.validated_data['transaction_type']

            if transaction_type == 'DEBIT':
                if wallet.balance < amount:
                    return Response(
                        {'error': 'Insufficient balance'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                wallet.balance = F('balance') - amount
            else:  # CREDIT
                wallet.balance = F('balance') + amount

            wallet.save(update_fields=['balance', 'updated_at'])
            transaction = serializer.save(wallet=wallet, status='SUCCESS')

            return Response(
                self.get_serializer(transaction).data,
                status=status.HTTP_201_CREATED
            )

        except Wallet.DoesNotExist:
            return Response(
                {'error': 'Wallet not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    def partial_update(self, request: HttpRequest, *args: Any, **kwargs: Any) -> Response:
        """Update transaction status"""
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        serializer.save()
        return Response(serializer.data)


class RazorpayWebhookView(APIView):
    permission_classes = [AllowAny]

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        payload = request.body
        signature = request.META.get('HTTP_X_RAZORPAY_SIGNATURE', '')
        secret = getattr(settings, 'RAZORPAY_WEBHOOK_SECRET', settings.RAZORPAY_KEY_SECRET)

        if not signature:
            logger.warning("Missing Razorpay webhook signature")
            return HttpResponse(status=status.HTTP_400_BAD_REQUEST)

        if not _verify_razorpay_signature(payload, signature, secret):
            logger.warning("Invalid Razorpay webhook signature")
            return HttpResponse(status=status.HTTP_400_BAD_REQUEST)

        data = request.data
        event = data.get('event')
        payload_entity = data.get('payload', {})
        payment_entity = payload_entity.get('payment', {}).get('entity', {})

        order_id = payment_entity.get('order_id')
        payment_id = payment_entity.get('id')
        status_value = payment_entity.get('status')
        captured_amount = payment_entity.get('amount')

        if not order_id or not payment_id:
            logger.warning("Webhook missing order_id or payment_id")
            return HttpResponse(status=status.HTTP_200_OK)

        amount_decimal: Optional[Decimal] = None
        if captured_amount is not None:
            try:
                amount_decimal = Decimal(str(captured_amount)) / Decimal('100')
            except (InvalidOperation, TypeError, ValueError):
                amount_decimal = None

        if event == 'payment.captured' or status_value == 'captured':
            complete_transaction_success(order_id, payment_id, amount_decimal)
        elif status_value in {'failed', 'cancelled'}:
            mark_transaction_failed(order_id, reason=status_value)

        return HttpResponse(status=status.HTTP_200_OK)