from __future__ import annotations

from django.db import models
from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal
from django.utils import timezone
from django.db.models import QuerySet
from typing import Any, Optional, List, Tuple, Dict, Union

User = get_user_model()

class ActiveManager(models.Manager):
    def get_queryset(self) -> QuerySet:
        return super().get_queryset().filter(is_active=True)

class BaseModel(models.Model):
    author: models.ForeignKey = models.ForeignKey(User, on_delete=models.CASCADE, db_index=True)
    is_active: models.BooleanField = models.BooleanField(default=True, db_index=True)
    created_at: models.DateTimeField = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True)

    objects: ActiveManager = ActiveManager()
    all_objects: models.Manager = models.Manager()

    class Meta:
        abstract = True

    def soft_delete(self) -> None:
        self.is_active = False
        self.save(update_fields=['is_active', 'updated_at'])

class MarketMilkPrice(BaseModel):
    price: models.DecimalField = models.DecimalField(max_digits=100, decimal_places=2, db_index=True)

    def __str__(self) -> str:
        return f"{self.price}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        # Deactivate all other active records for this author
        if self.is_active:
            qs = MarketMilkPrice.objects.filter(author=self.author, is_active=True)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            qs.update(is_active=False)
        super().save(*args, **kwargs)

    class Meta:
        indexes = [
            models.Index(fields=['price', 'created_at']),
            models.Index(fields=['author', 'is_active', 'created_at'])
        ]

class Collection(BaseModel):
    MEASURE_CHOICES: List[Tuple[str, str]] = [
        ('liters', 'Liters'),
        ('kg', 'Kg')
    ]

    TIME_CHOICES: List[Tuple[str, str]] = [
        ('morning', 'Morning'),
        ('evening', 'Evening')
    ]

    MILK_TYPE_CHOICES: List[Tuple[str, str]] = [
        ('cow', 'Cow'),
        ('buffalo', 'Buffalo'),
        ('cow_buffalo', 'Cow + Buffalo')
    ]

    collection_time: models.CharField = models.CharField(max_length=10, choices=TIME_CHOICES, db_index=True)
    milk_type: models.CharField = models.CharField(max_length=20, choices=MILK_TYPE_CHOICES, db_index=True)
    customer: models.ForeignKey = models.ForeignKey('Customer', on_delete=models.CASCADE, db_index=True)
    collection_date: models.DateField = models.DateField(db_index=True)

    base_fat_percentage: models.DecimalField = models.DecimalField(max_digits=4, decimal_places=3, default=6.5)
    base_snf_percentage: models.DecimalField = models.DecimalField(
        max_digits=4,
        decimal_places=3,
        default=9.0,
        validators=[
            MinValueValidator(Decimal('8.0'), message="Base SNF percentage cannot be less than 8.0"),
            MaxValueValidator(Decimal('9.5'), message="Base SNF percentage cannot be more than 9.5")
        ]
    )

    measured: models.CharField = models.CharField(max_length=10, choices=MEASURE_CHOICES)
    liters: models.DecimalField = models.DecimalField(max_digits=8, decimal_places=3, default=0)
    kg: models.DecimalField = models.DecimalField(max_digits=8, decimal_places=3, default=0)
    fat_percentage: models.DecimalField = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    fat_kg: models.DecimalField = models.DecimalField(max_digits=8, decimal_places=3, default=0)
    clr: models.DecimalField = models.DecimalField(max_digits=6, decimal_places=3,default=0, null=True, blank=True)
    snf_percentage: models.DecimalField = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    snf_kg: models.DecimalField = models.DecimalField(max_digits=8, decimal_places=3, default=0)

    fat_rate: models.DecimalField = models.DecimalField(max_digits=8, decimal_places=3, default=0)
    snf_rate: models.DecimalField = models.DecimalField(max_digits=8, decimal_places=3, default=0)
    milk_rate: models.DecimalField = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    solid_weight: models.DecimalField = models.DecimalField(max_digits=8, decimal_places=3, default=0)
    amount: models.DecimalField = models.DecimalField(max_digits=15, decimal_places=3, default=0)

    # Fields for tracking edits
    edit_count: models.IntegerField = models.IntegerField(default=0, help_text="Number of times this collection has been edited")
    last_edited_at: models.DateTimeField = models.DateTimeField(null=True, blank=True, help_text="When this collection was last edited")
    is_pro_rata: models.BooleanField = models.BooleanField(default=False, null=True, blank=True)
    is_raw_collection: models.BooleanField = models.BooleanField(default=False, help_text="Whether this collection was created from a raw collection")
    
    def __str__(self) -> str:
        return f"{self.customer.name} - {self.collection_date} {self.collection_time}"

    def can_edit(self) -> bool:
        """Check if this collection can be edited based on settings"""
        from django.conf import settings
        from django.utils import timezone

        # Get edit settings
        edit_settings = getattr(settings, 'COLLECTION_EDIT', {})

        # If edit limitations are disabled, always allow edits
        if not edit_settings.get('ENABLED', True):
            return True

        # Check edit count
        max_edits = edit_settings.get('MAX_EDIT_COUNT', 1)
        if self.edit_count >= max_edits:
            return False

        # Check days limit
        max_days = edit_settings.get('MAX_EDIT_DAYS', 7)
        days_since_creation = (timezone.now() - self.created_at).days
        if days_since_creation > max_days:
            return False

        return True

    def is_duplicate(self) -> bool:
        """Check if an identical collection already exists"""
        if not self.pk:  # Only check for new collections
            # Fields to check for duplicates
            duplicate_query = Collection.objects.filter(
                author=self.author,
                customer=self.customer,
                collection_date=self.collection_date,
                collection_time=self.collection_time,
                milk_type=self.milk_type,
                measured=self.measured,
                liters=self.liters,
                kg=self.kg,
                fat_percentage=self.fat_percentage,
                fat_kg=self.fat_kg,
                clr=self.clr,
                snf_percentage=self.snf_percentage,
                snf_kg=self.snf_kg,
                fat_rate=self.fat_rate,
                snf_rate=self.snf_rate,
                milk_rate=self.milk_rate,
                solid_weight=self.solid_weight,
                amount=self.amount,
                base_fat_percentage=self.base_fat_percentage,
                base_snf_percentage=self.base_snf_percentage,
                is_active=True
            )
            return duplicate_query.exists()
        return False

    def save(self, *args: Any, **kwargs: Any) -> None:
        # Check for duplicates before saving
        if self.is_duplicate():
            from django.core.exceptions import ValidationError
            raise ValidationError(
                'Duplicate collection found. An identical collection already exists for this customer '
                f'on {self.collection_date} ({self.collection_time}) with the exact same measurements.'
            )

        # If this is an update (not a new creation)
        if self.pk:
            # Get the original instance from database
            original = Collection.objects.get(pk=self.pk)

            # If any field has changed (except last_edited_at and edit_count)
            fields_to_check = [
                'collection_time', 'milk_type', 'customer_id', 'collection_date',
                'measured', 'liters', 'kg', 'fat_percentage', 'fat_kg', 'clr',
                'snf_percentage', 'snf_kg', 'fat_rate', 'snf_rate', 'milk_rate',
                'solid_weight', 'amount', 'base_fat_percentage', 'base_snf_percentage'
            ]

            if any(getattr(self, field) != getattr(original, field) for field in fields_to_check):
                self.edit_count += 1
                self.last_edited_at = timezone.now()

        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-collection_date', '-created_at']
        indexes = [
            models.Index(fields=['collection_date', 'collection_time']),
            models.Index(fields=['customer', 'collection_date']),
            models.Index(fields=['author', 'is_active', 'collection_date']),
            models.Index(fields=['milk_type', 'collection_date']),
            models.Index(fields=['milk_rate', 'amount']),
            models.Index(fields=['edit_count', 'last_edited_at'])  # Add index for edit tracking fields
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(base_snf_percentage__gte=Decimal('8.0')) &
                    models.Q(base_snf_percentage__lte=Decimal('9.5'))
                ),
                name='collection_base_snf_between_8_0_9_5'
            )
        ]

class Customer(BaseModel):
    name: models.CharField = models.CharField(max_length=100, db_index=True)
    father_name: models.CharField = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    phone: models.CharField = models.CharField(max_length=15, blank=True, db_index=True)
    village: models.CharField = models.CharField(max_length=100, blank=True, db_index=True)
    address: models.TextField = models.TextField(blank=True, db_index=True)
    customer_id: models.PositiveIntegerField = models.PositiveIntegerField(default=0, db_index=True, help_text="Sequential customer number")

    def __str__(self) -> str:
        return f"{self.customer_id} - {self.name}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        # Add +91 prefix to phone number if it doesn't exist
        if self.phone:
            # Remove any existing '+' or leading zeros
            cleaned_phone = self.phone.lstrip('+0')
            # Remove '91' prefix if it exists
            if cleaned_phone.startswith('91'):
                cleaned_phone = cleaned_phone[2:]
            # Add +91 prefix
            self.phone = f'+91{cleaned_phone}'

        # Handle customer_id assignment for new customers
        if not self.pk:  # Only for new customers being created
            # Get the maximum customer_id for this author
            max_id = Customer.objects.filter(author=self.author).aggregate(models.Max('customer_id'))['customer_id__max'] or 0
            # Set the new customer_id to max + 1
            self.customer_id = max_id + 1

        super().save(*args, **kwargs)

    class Meta:
        indexes = [
            models.Index(fields=['name', 'phone']),
            models.Index(fields=['author', 'is_active']),
            models.Index(fields=['customer_id']),  # Add index for customer_id
        ]
        ordering = ['name', '-created_at']

class DairyInformation(BaseModel):
    RATE_TYPE_CHOICES: List[Tuple[str, str]] = [
        ('kg_only', 'Kg Only'),
        ('liters_only', 'Liters Only'),
        ('fat_only', 'Fat Only'),
        ('fat_snf', 'Fat + SNF'),
        ('fat_clr', 'Fat + CLR')
    ]

    BASE_SNF_CHOICES: List[Tuple[Decimal, str]] = [
        (Decimal('8.5'), '8.5'),
        (Decimal('9.0'), '9.0')
    ]

    FAT_SNF_RATIO_CHOICES: List[Tuple[str, str]] = [
        ('60/40', '60/40'),
        ('52/48', '52/48')
    ]

    CLR_CONVERSION_FACTOR: List[Tuple[Decimal, str]] = [
        (Decimal('0.14'), '0.14'),
        (Decimal('0.50'), '0.50')
    ]

    dairy_name: models.CharField = models.CharField(max_length=255, db_index=True)
    dairy_address: models.TextField = models.TextField(blank=True, null=True)
    rate_type: models.CharField = models.CharField(max_length=20, choices=RATE_TYPE_CHOICES,blank=True, null=True, db_index=True)
    base_snf: models.DecimalField = models.DecimalField(
        max_digits=4,
        decimal_places=3,
        default=Decimal('9.0'),
        choices=BASE_SNF_CHOICES,
        db_index=True
    )
    fat_snf_ratio: models.CharField = models.CharField(max_length=10, choices=FAT_SNF_RATIO_CHOICES, default='60/40', db_index=True)
    clr_conversion_factor: models.DecimalField = models.DecimalField(
        max_digits=4,
        decimal_places=3,
        default=Decimal('0.14'),
        choices=CLR_CONVERSION_FACTOR,
        db_index=True
    )


    def __str__(self) -> str:
        return self.dairy_name

    def save(self, *args: Any, **kwargs: Any) -> None:
        # Deactivate all other active records for this author
        if self.is_active:
            qs = DairyInformation.objects.filter(author=self.author, is_active=True)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            qs.update(is_active=False)
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Dairy Information'
        verbose_name_plural = 'Dairy Information'
        indexes = [
            models.Index(fields=['dairy_name', 'rate_type', 'base_snf', 'fat_snf_ratio', 'clr_conversion_factor']),
            models.Index(fields=['author', 'is_active', 'created_at'])
        ]



class ProRataRateChart(BaseModel):
    
    def __str__(self) -> str:
        return f"Pro Rata Rate Chart ({self.created_at.date()})"

    def save(self, *args: Any, **kwargs: Any) -> None:
        # Deactivate all other active records for this author
        if self.is_active:
            ProRataRateChart.objects.filter(author=self.author, is_active=True).update(is_active=False)
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = 'Pro Rata Rate Chart'
        verbose_name_plural = 'Pro Rata Rate Charts'
        indexes = [
            models.Index(fields=['author', 'is_active'])
        ]

class FatStepUpRate(BaseModel):
    chart: models.ForeignKey = models.ForeignKey(ProRataRateChart, on_delete=models.CASCADE, related_name='fat_step_up_rates', db_index=True)
    step: models.DecimalField = models.DecimalField(max_digits=5, decimal_places=2)
    rate: models.DecimalField = models.DecimalField(max_digits=8, decimal_places=3)

    def __str__(self) -> str:
        return f"Fat Step Up - {self.step}"

    class Meta:
        verbose_name = 'Fat Step Up Rate'
        verbose_name_plural = 'Fat Step Up Rates'
        indexes = [
            models.Index(fields=['chart', 'step']),
        ]
        ordering = ['chart', 'step']

class SnfStepDownRate(BaseModel):
    chart: models.ForeignKey = models.ForeignKey(ProRataRateChart, on_delete=models.CASCADE, related_name='snf_step_down_rates', db_index=True)
    step: models.DecimalField = models.DecimalField(max_digits=5, decimal_places=2)
    rate: models.DecimalField = models.DecimalField(max_digits=8, decimal_places=3)

    def __str__(self) -> str:
        return f"SNF Step Down - {self.step}"

    class Meta:
        verbose_name = 'SNF Step Down Rate'
        verbose_name_plural = 'SNF Step Down Rates'
        indexes = [
            models.Index(fields=['chart', 'step']),
        ]
        ordering = ['chart', 'step']

#------------------- Raw collection model without Milk rate -------------------
class RawCollection(BaseModel):
    MEASURE_CHOICES: List[Tuple[str, str]] = [
        ('liters', 'Liters'),
        ('kg', 'Kg')
    ]

    TIME_CHOICES: List[Tuple[str, str]] = [
        ('morning', 'Morning'),
        ('evening', 'Evening')
    ]

    MILK_TYPE_CHOICES: List[Tuple[str, str]] = [
        ('cow', 'Cow'),
        ('buffalo', 'Buffalo'),
        ('cow_buffalo', 'Cow + Buffalo')
    ]

    collection_time: models.CharField = models.CharField(max_length=10, choices=TIME_CHOICES, db_index=True)
    milk_type: models.CharField = models.CharField(max_length=20, choices=MILK_TYPE_CHOICES, db_index=True)
    customer: models.ForeignKey = models.ForeignKey('Customer', on_delete=models.CASCADE, db_index=True)
    collection_date: models.DateField = models.DateField(db_index=True)

    base_fat_percentage: models.DecimalField = models.DecimalField(max_digits=4, decimal_places=3, default=6.5)
    base_snf_percentage: models.DecimalField = models.DecimalField(
        max_digits=4,
        decimal_places=3,
        default=9.0,
        validators=[
            MinValueValidator(Decimal('8.0'), message="Base SNF percentage cannot be less than 8.0"),
            MaxValueValidator(Decimal('9.5'), message="Base SNF percentage cannot be more than 9.5")
        ]
    )

    measured: models.CharField = models.CharField(max_length=10, choices=MEASURE_CHOICES)
    liters: models.DecimalField = models.DecimalField(max_digits=8, decimal_places=3, default=0)
    kg: models.DecimalField = models.DecimalField(max_digits=8, decimal_places=3, default=0)
    fat_percentage: models.DecimalField = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    fat_kg: models.DecimalField = models.DecimalField(max_digits=8, decimal_places=3, default=0)
    clr: models.DecimalField = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)
    snf_percentage: models.DecimalField = models.DecimalField(max_digits=5, decimal_places=2, default=0, null=True, blank=True)
    snf_kg: models.DecimalField = models.DecimalField(max_digits=8, decimal_places=3, default=0, null=True, blank=True)

    fat_rate: models.DecimalField = models.DecimalField(max_digits=8, decimal_places=3, default=0, null=True, blank=True)
    snf_rate: models.DecimalField = models.DecimalField(max_digits=8, decimal_places=3, default=0, null=True, blank=True)
    milk_rate: models.DecimalField = models.DecimalField(max_digits=8, decimal_places=2, default=0, null=True, blank=True)
    solid_weight: models.DecimalField = models.DecimalField(max_digits=8, decimal_places=3, default=0, null=True, blank=True)
    amount: models.DecimalField = models.DecimalField(max_digits=15, decimal_places=3, default=0, null=True, blank=True)

    is_milk_rate: models.BooleanField = models.BooleanField(default=False)
    last_edited_at: models.DateTimeField = models.DateTimeField(null=True, blank=True, help_text="When this collection was last edited")

    def __str__(self) -> str:
        return f"{self.customer.name} - {self.collection_date} {self.collection_time}"

    class Meta:
        ordering = ['-collection_date', '-created_at']
        indexes = [
            models.Index(fields=['collection_date', 'collection_time']),
            models.Index(fields=['customer', 'collection_date']),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(base_snf_percentage__gte=Decimal('8.0')) &
                    models.Q(base_snf_percentage__lte=Decimal('9.5'))
                ),
                name='rawcollection_base_snf_between_8_0_9_5'
            )
        ]
    