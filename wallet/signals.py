from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.db import transaction
from .models import Wallet

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