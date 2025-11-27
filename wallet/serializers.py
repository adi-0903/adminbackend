from __future__ import annotations

from rest_framework import serializers
from decimal import Decimal
from django.core.validators import MinValueValidator
from typing import Any, Dict, Union, Optional

from .models import Wallet, WalletTransaction

class WalletSerializer(serializers.ModelSerializer):
    phone_number = serializers.CharField(source='user.phone_number', read_only=True)
    balance = serializers.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        validators=[MinValueValidator(Decimal('0.00'))]
    )

    class Meta:
        model = Wallet
        fields = ['id', 'phone_number', 'balance', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'phone_number', 'created_at', 'updated_at']

    def validate_balance(self, value: Decimal) -> Decimal:
        if value < 0:
            raise serializers.ValidationError("Balance cannot be negative")
        return value

class WalletTransactionSerializer(serializers.ModelSerializer):
    phone_number = serializers.CharField(source='wallet.user.phone_number', read_only=True)
    amount = serializers.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    transaction_type = serializers.ChoiceField(choices=WalletTransaction.TRANSACTION_TYPE_CHOICES)
    status = serializers.ChoiceField(choices=WalletTransaction.TRANSACTION_STATUS_CHOICES)

    class Meta:
        model = WalletTransaction
        fields = [
            'id', 'phone_number', 'wallet', 'amount', 'transaction_type', 
            'status', 'description', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'phone_number', 'created_at', 'updated_at']

    def validate_amount(self, value: Decimal) -> Decimal:
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than 0")
        return value

    def validate_transaction_type(self, value: str) -> str:
        if value.upper() not in dict(WalletTransaction.TRANSACTION_TYPE_CHOICES):
            raise serializers.ValidationError("Invalid transaction type")
        return value.upper()

    def validate_status(self, value: str) -> str:
        if value.upper() not in dict(WalletTransaction.TRANSACTION_STATUS_CHOICES):
            raise serializers.ValidationError("Invalid status")
        return value.upper()

class AddMoneySerializer(serializers.Serializer):
    amount: serializers.DecimalField = serializers.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])

    def validate_amount(self, value: Decimal) -> Decimal:
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than 0")
        return value 


class PaymentVerificationSerializer(serializers.Serializer):
    order_id = serializers.CharField(max_length=100)
    payment_id = serializers.CharField(max_length=100)
    signature = serializers.CharField(max_length=255)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, validators=[MinValueValidator(Decimal('0.01'))])

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        amount = attrs.get('amount')
        if amount is not None and amount <= 0:
            raise serializers.ValidationError({"amount": "Amount must be greater than 0"})
        return attrs
