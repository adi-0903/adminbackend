from __future__ import annotations

from rest_framework import serializers
from django.db import transaction
from typing import Any, Dict, Optional, List, Union
from decimal import Decimal
from django.http import HttpRequest
from rest_framework.request import Request
from django.utils import timezone

from .models import Collection, Customer, MarketMilkPrice, DairyInformation, RawCollection

class BaseModelSerializer(serializers.ModelSerializer):
    def create(self, validated_data: Dict[str, Any]) -> Any:
        validated_data['author'] = self.context['request'].user
        return super().create(validated_data)

    class Meta:
        abstract = True
        read_only_fields = ['id', 'is_active', 'created_at', 'updated_at']

class MarketMilkPriceSerializer(BaseModelSerializer):
    class Meta(BaseModelSerializer.Meta):
        model = MarketMilkPrice
        fields = ['id', 'price', 'is_active', 'created_at', 'updated_at']

    def validate_price(self, value: Decimal) -> Decimal:
        if value <= 0:
            raise serializers.ValidationError("Price must be greater than 0")
        return value

class CustomerSerializer(BaseModelSerializer):
    class Meta(BaseModelSerializer.Meta):
        model = Customer
        fields = ['id', 'customer_id', 'name', 'father_name', 'phone', 'village', 'address', 'is_active']

    def validate_phone(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return value
            
        # Remove any existing '+' or leading zeros
        cleaned_phone = value.lstrip('+0')
        
        # Check if the phone number contains only digits
        if not cleaned_phone.isdigit():
            raise serializers.ValidationError("Phone number must contain only digits")
            
        # Check if the length is valid (10 digits for Indian numbers)
        if len(cleaned_phone) != 10:
            raise serializers.ValidationError("Phone number must be exactly 10 digits")
            
        return cleaned_phone  # Return cleaned number, model's save() will add +91

    def validate_name(self, value: str) -> str:
        if not value or not value.strip():
            raise serializers.ValidationError("Name cannot be empty")
        return value.strip()

    @transaction.atomic
    def update(self, instance: Customer, validated_data: Dict[str, Any]) -> Customer:
        # Handle phone number update
        if 'phone' in validated_data:
            phone = validated_data['phone']
            if phone and not phone.startswith('+91'):
                # Remove any existing '+' or leading zeros
                cleaned_phone = phone.lstrip('+0')
                # Add +91 prefix
                validated_data['phone'] = f'+91{cleaned_phone}'

        return super().update(instance, validated_data)

class CollectionListSerializer(BaseModelSerializer):
    customer_id: serializers.PrimaryKeyRelatedField = serializers.PrimaryKeyRelatedField(source='customer.customer_id', read_only=True, required=False)
    customer_name: serializers.CharField = serializers.CharField(source='customer.name', read_only=True)

    class Meta(BaseModelSerializer.Meta):
        model = Collection
        fields = [
            'id', 'collection_time', 'milk_type', 'customer_id', 'customer_name',
            'collection_date', 'measured', 'liters', 'kg',
            'fat_percentage', 'fat_kg', 'clr', 'snf_percentage', 'snf_kg',
            'fat_rate', 'snf_rate', 'milk_rate', 'amount', 'solid_weight',
            'base_snf_percentage', 'is_pro_rata', 'is_raw_collection'
        ]

class CollectionDetailSerializer(BaseModelSerializer):
    customer_name: serializers.CharField = serializers.CharField(source='customer.name', read_only=True)
    clr: serializers.DecimalField = serializers.DecimalField(max_digits=6, decimal_places=3,allow_null=True, required=False
    )

    class Meta(BaseModelSerializer.Meta):
        model = Collection
        fields = [
            'id', 'collection_time', 'milk_type', 'customer',
            'customer_name', 'collection_date', 'measured', 'liters', 'kg',
            'fat_percentage', 'fat_kg', 'clr', 'snf_percentage', 'snf_kg',
            'fat_rate', 'snf_rate', 'milk_rate', 'amount', 'solid_weight','is_pro_rata',
            'base_fat_percentage', 'base_snf_percentage', 'is_raw_collection',
            'created_at', 'updated_at', 'is_active'
        ]

    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        # Validate numeric fields
        numeric_fields = ['liters', 'kg', 'fat_percentage', 'fat_kg', 
                         'snf_percentage', 'snf_kg', 'milk_rate', 'amount', 'solid_weight']
        for field in numeric_fields:
            if field in data and data[field] <= 0:
                raise serializers.ValidationError({field: f"{field.replace('_', ' ').title()} must be greater than 0"})

        # Validate percentages
        percentage_fields = ['fat_percentage', 'snf_percentage']
        for field in percentage_fields:
            if field in data and data[field] > 100:
                raise serializers.ValidationError({field: f"{field.replace('_', ' ').title()} cannot be greater than 100"})

        # Ensure is_pro_rata is properly set with a default
        if 'is_pro_rata' not in data:
            data['is_pro_rata'] = False
        
        # Ensure is_raw_collection is properly set with a default
        if 'is_raw_collection' not in data:
            data['is_raw_collection'] = False

        return data

    def validate_customer(self, value: Customer) -> Customer:
        request = self.context.get('request')
        if not request:
            raise serializers.ValidationError("No request found in context")
        
        if not Customer.objects.filter(id=value.id, author=request.user, is_active=True).exists():
            raise serializers.ValidationError(
                "Invalid customer. Please select an active customer that belongs to your account."
            )
        return value

    @transaction.atomic
    def create(self, validated_data: Dict[str, Any]) -> Collection:
        validated_data['author'] = self.context['request'].user
        return super().create(validated_data)

    @transaction.atomic
    def update(self, instance: Collection, validated_data: Dict[str, Any]) -> Collection:
        return super().update(instance, validated_data)

class DairyInformationSerializer(BaseModelSerializer):
    class Meta(BaseModelSerializer.Meta):
        model = DairyInformation
        fields = ['id', 'dairy_name', 'dairy_address', 'rate_type', 'is_active', 'created_at', 'updated_at']

    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        # Validate required fields
        if not data.get('dairy_name'):
            raise serializers.ValidationError({"dairy_name": "Dairy name is required"})
        
        if not data.get('rate_type'):
            raise serializers.ValidationError({"rate_type": "Rate type is required"})
            
        # Validate rate_type choices
        valid_rate_types = [choice[0] for choice in DairyInformation.RATE_TYPE_CHOICES]
        if data.get('rate_type') and data['rate_type'] not in valid_rate_types:
            raise serializers.ValidationError({
                "rate_type": f"Invalid rate type. Must be one of: {', '.join(valid_rate_types)}"
            })
        
        return data

    def validate_dairy_name(self, value: str) -> str:
        if not value or not value.strip():
            raise serializers.ValidationError("Dairy name cannot be empty")

        request = self.context.get('request')
        if not request:
            raise serializers.ValidationError("No request found in context")

        # Check for duplicate dairy names for the same user
        if DairyInformation.objects.filter(
            dairy_name__iexact=value.strip(),
            author=request.user,
            is_active=True
        ).exclude(id=getattr(self.instance, 'id', None)).exists():
            raise serializers.ValidationError("A dairy with this name already exists")
            
        return value.strip()

    def validate_dairy_address(self, value: Optional[str]) -> Optional[str]:
        if value:
            return value.strip()
        return value 

class RawCollectionListSerializer(BaseModelSerializer):
    customer_id: serializers.PrimaryKeyRelatedField = serializers.PrimaryKeyRelatedField(source='customer.customer_id', read_only=True, required=False)
    customer_name: serializers.CharField = serializers.CharField(source='customer.name', read_only=True)

    class Meta(BaseModelSerializer.Meta):
        model = RawCollection
        fields = [
            'id', 'collection_time', 'milk_type', 'customer_id', 'customer_name',
            'collection_date', 'measured', 'liters', 'kg',
            'fat_percentage', 'fat_kg', 'clr', 'snf_percentage', 'snf_kg',
            'base_snf_percentage', 'is_milk_rate'
        ]

class RawCollectionDetailSerializer(BaseModelSerializer):
    customer_name: serializers.CharField = serializers.CharField(source='customer.name', read_only=True)
    clr: serializers.DecimalField = serializers.DecimalField(max_digits=6, decimal_places=3, allow_null=True, required=False)

    class Meta(BaseModelSerializer.Meta):
        model = RawCollection
        fields = [
            'id', 'collection_time', 'milk_type', 'customer',
            'customer_name', 'collection_date', 'measured', 'liters', 'kg',
            'fat_percentage', 'fat_kg', 'clr', 'snf_percentage', 'snf_kg',
            'fat_rate', 'snf_rate', 'milk_rate', 'amount', 'solid_weight',
            'base_fat_percentage', 'base_snf_percentage',
            'created_at', 'updated_at', 'is_active'
        ]

    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        # Validate numeric fields
        numeric_fields = ['liters', 'kg', 'fat_percentage', 'fat_kg', 'snf_percentage', 'snf_kg']
        for field in numeric_fields:
            if field in data and data[field] <= 0:
                raise serializers.ValidationError({field: f"{field.replace('_', ' ').title()} must be greater than 0"})

        # Validate percentages
        percentage_fields = ['fat_percentage', 'snf_percentage']
        for field in percentage_fields:
            if field in data and data[field] > 100:
                raise serializers.ValidationError({field: f"{field.replace('_', ' ').title()} cannot be greater than 100"})

        return data

    def validate_customer(self, value: Customer) -> Customer:
        request = self.context.get('request')
        if not request:
            raise serializers.ValidationError("No request found in context")
        
        if not Customer.objects.filter(id=value.id, author=request.user, is_active=True).exists():
            raise serializers.ValidationError(
                "Invalid customer. Please select an active customer that belongs to your account."
            )
        return value

    @transaction.atomic
    def create(self, validated_data: Dict[str, Any]) -> RawCollection:
        validated_data['author'] = self.context['request'].user
        
        # Set is_milk_rate to True if milk_rate is provided and greater than 0
        if 'milk_rate' in validated_data and validated_data['milk_rate'] > 0:
            validated_data['is_milk_rate'] = True
            
            # Copy data to Collection model if is_milk_rate is True
            collection_data = {
                'author': validated_data['author'],
                'collection_time': validated_data['collection_time'],
                'milk_type': validated_data['milk_type'],
                'customer': validated_data['customer'],
                'collection_date': validated_data['collection_date'],
                'base_fat_percentage': validated_data.get('base_fat_percentage', 6.5),
                'base_snf_percentage': validated_data.get('base_snf_percentage', 9.0),
                'measured': validated_data['measured'],
                'liters': validated_data['liters'],
                'kg': validated_data['kg'],
                'fat_percentage': validated_data['fat_percentage'],
                'fat_kg': validated_data['fat_kg'],
                'clr': validated_data.get('clr'),
                'snf_percentage': validated_data['snf_percentage'],
                'snf_kg': validated_data['snf_kg'],
                'fat_rate': validated_data.get('fat_rate', 0),
                'snf_rate': validated_data.get('snf_rate', 0),
                'milk_rate': validated_data['milk_rate'],
                'solid_weight': validated_data.get('solid_weight', 0),
                'amount': validated_data.get('amount', 0),
                'is_pro_rata': validated_data.get('is_pro_rata', False),
                'is_raw_collection': False,
            }
            
            # Create new Collection
            from .models import Collection
            Collection.objects.create(**collection_data)
        else:
            validated_data['is_milk_rate'] = False
            
        return super().create(validated_data)

    @transaction.atomic
    def update(self, instance: RawCollection, validated_data: Dict[str, Any]) -> RawCollection:
        # Check if milk_rate is being updated and is greater than 0
        if 'milk_rate' in validated_data and validated_data['milk_rate'] > 0:
            validated_data['is_milk_rate'] = True
            
            # If not already marked as having milk rate, copy to Collection
            if not instance.is_milk_rate:
                collection_data = {
                    'author': instance.author,
                    'collection_time': instance.collection_time,
                    'milk_type': instance.milk_type,
                    'customer': instance.customer,
                    'collection_date': instance.collection_date,
                    'base_fat_percentage': instance.base_fat_percentage,
                    'base_snf_percentage': instance.base_snf_percentage,
                    'measured': instance.measured,
                    'liters': instance.liters,
                    'kg': instance.kg,
                    'fat_percentage': instance.fat_percentage,
                    'fat_kg': validated_data.get('fat_kg', instance.fat_kg),
                    'clr': instance.clr,
                    'snf_percentage': instance.snf_percentage or Decimal('0'),
                    'snf_kg': validated_data.get('snf_kg', instance.snf_kg or Decimal('0')),
                    'fat_rate': validated_data.get('fat_rate', instance.fat_rate or Decimal('0')),
                    'snf_rate': validated_data.get('snf_rate', instance.snf_rate or Decimal('0')),
                    'milk_rate': validated_data['milk_rate'],
                    'solid_weight': validated_data.get('solid_weight', instance.solid_weight or Decimal('0')),
                    'amount': validated_data.get('amount', instance.amount or Decimal('0')),
                    'is_pro_rata': validated_data.get('is_pro_rata', False),
                    'is_raw_collection': False,
                }
                
                # Create new Collection
                from .models import Collection
                Collection.objects.create(**collection_data)
        
        # Update last_edited_at timestamp
        validated_data['last_edited_at'] = timezone.now()
        
        return super().update(instance, validated_data)

class RawCollectionMilkRateSerializer(RawCollectionDetailSerializer):
    """Serializer for adding milk rate to RawCollection and copying to Collection"""
    
    class Meta(RawCollectionDetailSerializer.Meta):
        model = RawCollection
        fields = RawCollectionDetailSerializer.Meta.fields
    
    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        data = super().validate(data)
        
        # Validate milk rate fields if provided
        if 'milk_rate' in data and data['milk_rate'] <= 0:
            raise serializers.ValidationError({'milk_rate': 'Milk rate must be greater than 0'})
        
        if 'amount' in data and data['amount'] <= 0:
            raise serializers.ValidationError({'amount': 'Amount must be greater than 0'})
        
        return data
    
    @transaction.atomic
    def update(self, instance: RawCollection, validated_data: Dict[str, Any]) -> RawCollection:
        # Make sure milk_rate is present and > 0
        if 'milk_rate' not in validated_data or validated_data['milk_rate'] <= 0:
            raise serializers.ValidationError({'milk_rate': 'A valid milk rate greater than 0 is required'})
        
        # Update RawCollection instance with milk rate info
        instance = super().update(instance, validated_data)
        
        return instance 