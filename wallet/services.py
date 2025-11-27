from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import WalletTransaction, Wallet

logger = logging.getLogger(__name__)


def _increment_wallet_balance(wallet: Wallet, amount: Decimal) -> None:
    """Increment wallet balance safely using F expressions."""
    if amount <= 0:
        return
    Wallet.objects.filter(pk=wallet.pk).update(
        balance=F('balance') + amount,
        updated_at=timezone.now()
    )
    wallet.refresh_from_db(fields=['balance', 'updated_at'])


@transaction.atomic
def complete_transaction_success(
    order_id: str,
    payment_id: str,
    captured_amount: Optional[Decimal] = None,
) -> Optional[WalletTransaction]:
    """Mark the wallet transaction for order as successful and credit wallet."""
    try:
        wallet_transaction = (
            WalletTransaction.objects
            .select_for_update()
            .select_related('wallet')
            .get(razorpay_order_id=order_id)
        )
    except WalletTransaction.DoesNotExist:
        logger.error("No wallet transaction found for order %s", order_id)
        return None

    if wallet_transaction.status == 'SUCCESS':
        return wallet_transaction

    expected_amount = wallet_transaction.amount
    if captured_amount is not None:
        if captured_amount <= 0:
            logger.error("Captured amount must be positive for order %s", order_id)
            return wallet_transaction
        if captured_amount != expected_amount:
            logger.warning(
                "Captured amount %s does not match expected %s for order %s",
                captured_amount,
                expected_amount,
                order_id,
            )

    wallet_transaction.status = 'SUCCESS'
    wallet_transaction.razorpay_payment_id = payment_id
    wallet_transaction.updated_at = timezone.now()
    wallet_transaction.save(update_fields=['status', 'razorpay_payment_id', 'updated_at'])

    wallet = wallet_transaction.wallet
    _increment_wallet_balance(wallet, wallet_transaction.amount)

    # Process pending bonus transactions linked to this recharge
    bonus_transactions = list(
        WalletTransaction.objects
        .select_for_update()
        .filter(parent_transaction=wallet_transaction, status='PENDING')
    )

    for bonus_txn in bonus_transactions:
        bonus_txn.status = 'SUCCESS'
        bonus_txn.updated_at = timezone.now()
        bonus_txn.save(update_fields=['status', 'updated_at'])
        _increment_wallet_balance(wallet, bonus_txn.amount)

    return wallet_transaction


@transaction.atomic
def mark_transaction_failed(order_id: str, reason: Optional[str] = None) -> Optional[WalletTransaction]:
    """Mark the wallet transaction as failed and fail any bonus transactions."""
    try:
        wallet_transaction = (
            WalletTransaction.objects
            .select_for_update()
            .get(razorpay_order_id=order_id)
        )
    except WalletTransaction.DoesNotExist:
        logger.warning("Attempted to mark missing transaction %s as failed", order_id)
        return None

    if wallet_transaction.status in ['FAILED', 'SUCCESS']:
        return wallet_transaction

    wallet_transaction.status = 'FAILED'
    if reason:
        description = wallet_transaction.description or ''
        wallet_transaction.description = f"{description} | {reason}".strip()
    wallet_transaction.updated_at = timezone.now()
    wallet_transaction.save(update_fields=['status', 'description', 'updated_at'])

    WalletTransaction.objects.filter(
        parent_transaction=wallet_transaction,
        status='PENDING'
    ).update(status='FAILED', updated_at=timezone.now())

    return wallet_transaction
