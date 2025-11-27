from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from decimal import Decimal
from django.conf import settings
from .models import Collection
from wallet.models import Wallet, WalletTransaction

@receiver(post_save, sender=Collection)
def handle_collection_wallet_deduction(sender, instance, created, **kwargs):
    if created:  # Only for new collections
        # Get collection fee settings
        collection_fee = getattr(settings, 'COLLECTION_FEE', {})
        
        # Skip if collection fee is disabled
        if not collection_fee.get('ENABLED', False):
            return
            
        try:
            wallet = Wallet.objects.get(user=instance.author)
            
            # Calculate deduction amount based on kg
            per_kg_rate = Decimal(str(collection_fee.get('PER_KG_RATE', 0.02)))
            kg_amount = Decimal(str(instance.kg))
            deduction_amount = (per_kg_rate * kg_amount).quantize(Decimal('0.001'))
            
            # Skip if deduction amount is zero
            if deduction_amount <= 0:
                return
            
            # Check if wallet has sufficient balance
            if wallet.balance >= deduction_amount:
                # Deduct amount from wallet
                wallet.subtract_balance(deduction_amount)
                
                # Create transaction record
                description = f'Collection fee for {kg_amount} kg for customer {instance.customer.name} on {instance.collection_date}'
                
                WalletTransaction.objects.create(
                    wallet=wallet,
                    amount=deduction_amount,
                    transaction_type='DEBIT',
                    status='SUCCESS',
                    description=description
                )
        except Wallet.DoesNotExist:
            # Handle case where user doesn't have a wallet
            pass 