from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.db import transaction
from .models import Wallet, WalletTransaction
from user.models import UserActivity

User = get_user_model()

@receiver(post_save, sender=User)
def create_user_wallet(sender, instance, created, **kwargs):
    """Create a wallet when a user is created"""
    if created:
        # Use transaction.on_commit to ensure the user is fully saved before creating the wallet
        transaction.on_commit(lambda: create_wallet_for_user(instance))

def create_wallet_for_user(user_instance):
    """Helper function to create a wallet for a user after the transaction is committed"""
    try:
        Wallet.create_wallet_with_welcome_bonus(user_instance)
    except Exception as e:
        # Log the error but don't fail the user creation
        print(f"Error creating wallet for user {user_instance.id}: {str(e)}")


@receiver(post_save, sender=WalletTransaction)
def log_wallet_transaction_activity(sender, instance, created, **kwargs):
    """Log wallet transactions as user activities"""
    if created:
        try:
            activity_type = 'wallet_credit' if instance.transaction_type == 'CREDIT' else 'wallet_debit'
            UserActivity.objects.create(
                user=instance.wallet.user,
                activity_type=activity_type,
                metadata={
                    'amount': float(instance.amount),
                    'transaction_type': instance.transaction_type,
                    'description': instance.description,
                    'status': instance.status
                }
            )
        except Exception as e:
            pass