from django.contrib.auth import get_user_model
from django.db.models import Sum, Count, Q
from django.utils import timezone
from wallet.models import Wallet, WalletTransaction
from collector.models import Collection, Customer, RawCollection
from user.models import ReferralUsage
from decimal import Decimal
from typing import Dict, Any, List
from datetime import timedelta
import logging

User = get_user_model()
logger = logging.getLogger('admin')


def get_dashboard_stats() -> Dict[str, Any]:
    """Get comprehensive dashboard statistics"""
    
    # User statistics
    total_users = User.objects.all().count()
    active_users = User.objects.filter(is_active=True).count()
    inactive_users = User.objects.filter(is_active=False).count()
    
    # Wallet statistics
    wallets = Wallet.objects.filter(is_deleted=False)
    total_wallet_balance = wallets.aggregate(
        total=Sum('balance')
    )['total'] or Decimal('0.00')
    
    # Transaction statistics
    transactions = WalletTransaction.objects.filter(is_deleted=False)
    total_transactions = transactions.count()
    pending_transactions = transactions.filter(status='PENDING').count()
    failed_transactions = transactions.filter(status='FAILED').count()
    
    # Collection statistics
    total_collections = Collection.objects.filter(is_active=True).count()
    
    # Customer statistics
    total_customers = Customer.objects.filter(is_active=True).count()
    
    # Referral statistics
    referral_count = ReferralUsage.objects.filter(is_rewarded=True).count()
    
    return {
        'total_users': total_users,
        'active_users': active_users,
        'inactive_users': inactive_users,
        'total_wallet_balance': total_wallet_balance,
        'total_transactions': total_transactions,
        'total_collections': total_collections,
        'total_customers': total_customers,
        'pending_transactions': pending_transactions,
        'failed_transactions': failed_transactions,
        'referral_count': referral_count,
    }


def get_enhanced_dashboard_stats(days: int = 30) -> Dict[str, Any]:
    """Get enhanced dashboard statistics with detailed user and collection data"""
    
    start_date = timezone.now() - timedelta(days=days)
    
    # Enhanced User Statistics
    total_users = User.objects.all().count()
    active_users = User.objects.filter(is_active=True).count()
    inactive_users = User.objects.filter(is_active=False).count()
    
    # User details for dashboard
    users_data = User.objects.all().values(
        'id', 'phone_number', 'is_active', 'date_joined', 'is_staff'
    ).order_by('-date_joined')
    
    # Enhanced Collection Statistics (type-wise)
    collections = Collection.objects.filter(is_active=True)
    
    # Total collection by milk type
    collection_by_type = collections.values('milk_type').annotate(
        count=Count('id'),
        total_amount=Sum('amount'),
        total_liters=Sum('liters'),
        total_kg=Sum('kg')
    ).order_by('-total_amount')
    
    # Collection by time (morning/evening)
    collection_by_time = collections.values('collection_time').annotate(
        count=Count('id'),
        total_amount=Sum('amount'),
        total_liters=Sum('liters'),
        total_kg=Sum('kg')
    ).order_by('-total_amount')
    
    # Day-wise collection data for graph (last 30 days)
    day_wise_collections = collections.filter(
        collection_date__gte=start_date
    ).values('collection_date').annotate(
        total_amount=Sum('amount'),
        total_collections=Count('id'),
        total_liters=Sum('liters'),
        total_kg=Sum('kg')
    ).order_by('collection_date')
    
    # Day-wise collection by milk type for graph
    day_wise_by_type = collections.filter(
        collection_date__gte=start_date
    ).values('collection_date', 'milk_type').annotate(
        total_amount=Sum('amount'),
        total_collections=Count('id'),
        total_liters=Sum('liters'),
        total_kg=Sum('kg')
    ).order_by('collection_date', 'milk_type')
    
    # Recent collections
    recent_collections = collections.select_related('customer', 'author').order_by('-collection_date', '-created_at')[:10]
    
    # Summary statistics
    total_collection_amount = collections.aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0.00')
    
    total_collection_liters = collections.aggregate(
        total=Sum('liters')
    )['total'] or Decimal('0.00')
    
    total_collection_kg = collections.aggregate(
        total=Sum('kg')
    )['total'] or Decimal('0.00')
    
    # Collections in the last N days
    recent_collections_count = collections.filter(
        collection_date__gte=start_date
    ).count()
    
    recent_collections_amount = collections.filter(
        collection_date__gte=start_date
    ).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0.00')
    
    return {
        # User statistics
        'users': {
            'total': total_users,
            'active': active_users,
            'inactive': inactive_users,
            'data': list(users_data)
        },
        
        # Collection statistics
        'collections': {
            'total_amount': total_collection_amount,
            'total_liters': total_collection_liters,
            'total_kg': total_collection_kg,
            'total_count': collections.count(),
            'recent_count': recent_collections_count,
            'recent_amount': recent_collections_amount,
            'by_type': list(collection_by_type),
            'by_time': list(collection_by_time),
            'day_wise': list(day_wise_collections),
            'day_wise_by_type': list(day_wise_by_type),
            'recent': [
                {
                    'id': c.id,
                    'customer_name': c.customer.name,
                    'collection_date': c.collection_date,
                    'collection_time': c.collection_time,
                    'milk_type': c.milk_type,
                    'liters': c.liters,
                    'kg': c.kg,
                    'amount': c.amount,
                    'author_phone': c.author.phone_number
                } for c in recent_collections
            ]
        },
        
        # General statistics
        'total_customers': Customer.objects.filter(is_active=True).count(),
        'total_wallet_balance': Wallet.objects.filter(is_deleted=False).aggregate(
            total=Sum('balance')
        )['total'] or Decimal('0.00'),
        
        # Period info
        'period_days': days,
        'start_date': start_date.date(),
        'end_date': timezone.now().date()
    }


def get_user_statistics(days: int = 30) -> Dict[str, Any]:
    """Get user statistics for the last N days"""
    
    start_date = timezone.now() - timedelta(days=days)
    
    new_users = User.objects.filter(
        date_joined__gte=start_date,
        is_active=True
    ).count()
    
    inactive_users = User.objects.filter(is_active=False).count()
    
    users_with_wallet = User.objects.filter(
        is_active=True,
        wallet__isnull=False
    ).distinct().count()
    
    users_with_collections = User.objects.filter(
        is_active=True,
        collection__isnull=False
    ).distinct().count()
    
    return {
        'new_users_last_n_days': new_users,
        'inactive_users': inactive_users,
        'users_with_wallet': users_with_wallet,
        'users_with_collections': users_with_collections,
    }


def get_wallet_statistics(days: int = 30) -> Dict[str, Any]:
    """Get wallet and transaction statistics"""
    
    start_date = timezone.now() - timedelta(days=days)
    
    # Transaction statistics
    transactions = WalletTransaction.objects.filter(
        created_at__gte=start_date,
        is_deleted=False
    )
    
    total_credited = transactions.filter(
        transaction_type='CREDIT',
        status='SUCCESS'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    total_debited = transactions.filter(
        transaction_type='DEBIT',
        status='SUCCESS'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    successful_transactions = transactions.filter(status='SUCCESS').count()
    failed_transactions = transactions.filter(status='FAILED').count()
    
    # Wallet statistics
    wallets_with_balance = Wallet.objects.filter(
        is_deleted=False,
        balance__gt=0
    ).count()
    
    zero_balance_wallets = Wallet.objects.filter(
        is_deleted=False,
        balance=0
    ).count()
    
    return {
        'total_credited': total_credited,
        'total_debited': total_debited,
        'successful_transactions': successful_transactions,
        'failed_transactions': failed_transactions,
        'wallets_with_balance': wallets_with_balance,
        'zero_balance_wallets': zero_balance_wallets,
    }


def get_collection_statistics(days: int = 30) -> Dict[str, Any]:
    """Get collection statistics"""
    
    start_date = timezone.now() - timedelta(days=days)
    
    collections = Collection.objects.filter(
        created_at__gte=start_date,
        is_active=True
    )
    
    total_collections = collections.count()
    
    total_amount = collections.aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0.00')
    
    by_milk_type = collections.values('milk_type').annotate(
        count=Count('id'),
        total_amount=Sum('amount')
    )
    
    by_time = collections.values('collection_time').annotate(
        count=Count('id'),
        total_amount=Sum('amount')
    )
    
    edited_collections = collections.filter(edit_count__gt=0).count()
    
    return {
        'total_collections': total_collections,
        'total_amount': total_amount,
        'by_milk_type': list(by_milk_type),
        'by_time': list(by_time),
        'edited_collections': edited_collections,
    }


def get_referral_statistics() -> Dict[str, Any]:
    """Get referral system statistics"""
    
    total_referrals = ReferralUsage.objects.filter(is_rewarded=True).count()
    
    top_referrers = ReferralUsage.objects.filter(
        is_rewarded=True
    ).values('referrer__phone_number').annotate(
        count=Count('id')
    ).order_by('-count')[:10]
    
    return {
        'total_referrals': total_referrals,
        'top_referrers': list(top_referrers),
    }


def get_raw_collection_statistics(days: int = 30) -> Dict[str, Any]:
    """Get raw collection statistics"""
    
    start_date = timezone.now() - timedelta(days=days)
    
    raw_collections = RawCollection.objects.filter(
        created_at__gte=start_date
    )
    
    total_raw_collections = raw_collections.count()
    
    total_amount = raw_collections.filter(
        amount__isnull=False
    ).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0.00')
    
    by_milk_type = raw_collections.values('milk_type').annotate(
        count=Count('id'),
        total_amount=Sum('amount')
    )
    
    by_time = raw_collections.values('collection_time').annotate(
        count=Count('id'),
        total_amount=Sum('amount')
    )
    
    with_milk_rate = raw_collections.filter(is_milk_rate=True).count()
    without_milk_rate = raw_collections.filter(is_milk_rate=False).count()
    
    return {
        'total_raw_collections': total_raw_collections,
        'total_amount': total_amount,
        'by_milk_type': list(by_milk_type),
        'by_time': list(by_time),
        'with_milk_rate': with_milk_rate,
        'without_milk_rate': without_milk_rate,
    }


def get_dairy_information_statistics() -> Dict[str, Any]:
    """Get dairy information statistics"""
    from collector.models import DairyInformation
    
    total_dairies = DairyInformation.objects.filter(is_active=True).count()
    
    by_rate_type = DairyInformation.objects.filter(
        is_active=True
    ).values('rate_type').annotate(
        count=Count('id')
    )
    
    dairies_by_author = DairyInformation.objects.filter(
        is_active=True
    ).values('author__phone_number').annotate(
        count=Count('id')
    )
    
    return {
        'total_dairies': total_dairies,
        'by_rate_type': list(by_rate_type),
        'dairies_by_author': list(dairies_by_author),
    }


def log_admin_action(
    admin_user: User,
    action: str,
    model_name: str,
    object_id: str,
    object_repr: str = '',
    changes: Dict[str, Any] = None,
    request=None
) -> None:
    """Log admin actions for audit trail"""
    
    from .models import AdminLog
    
    ip_address = None
    user_agent = ''
    
    if request:
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        ip_address = x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')
        user_agent = request.META.get('HTTP_USER_AGENT', '')
    
    AdminLog.objects.create(
        admin_user=admin_user,
        action=action,
        model_name=model_name,
        object_id=object_id,
        object_repr=object_repr,
        changes=changes or {},
        ip_address=ip_address,
        user_agent=user_agent
    )
    
    logger.info(
        f"Admin action: {action} on {model_name} (ID: {object_id}) by {admin_user.phone_number}"
    )


def create_admin_notification(
    admin_user: User,
    title: str,
    message: str,
    priority: str = 'MEDIUM',
    related_model: str = '',
    related_object_id: str = ''
) -> None:
    """Create admin notification"""
    
    from .models import AdminNotification
    
    AdminNotification.objects.create(
        admin_user=admin_user,
        title=title,
        message=message,
        priority=priority,
        related_model=related_model,
        related_object_id=related_object_id
    )


def adjust_wallet_balance(
    user: User,
    amount: Decimal,
    transaction_type: str,
    description: str,
    admin_user: User = None
) -> bool:
    """Adjust wallet balance with transaction record"""
    
    try:
        wallet = Wallet.objects.get(user=user)
        
        if transaction_type == 'CREDIT':
            wallet.add_balance(amount)
        elif transaction_type == 'DEBIT':
            wallet.subtract_balance(amount)
        else:
            return False
        
        # Create transaction record
        WalletTransaction.objects.create(
            wallet=wallet,
            amount=amount,
            transaction_type=transaction_type,
            status='SUCCESS',
            description=description
        )
        
        # Log admin action
        if admin_user:
            log_admin_action(
                admin_user=admin_user,
                action='WALLET_ADJUST',
                model_name='Wallet',
                object_id=str(wallet.id),
                object_repr=f"Wallet for {user.phone_number}",
                changes={
                    'amount': str(amount),
                    'type': transaction_type,
                    'description': description
                }
            )
        
        return True
    
    except Wallet.DoesNotExist:
        logger.error(f"Wallet not found for user {user.phone_number}")
        return False
    except Exception as e:
        logger.error(f"Error adjusting wallet balance: {str(e)}")
        return False


def bulk_adjust_wallets(
    user_ids: List[int],
    amount: Decimal,
    transaction_type: str,
    description: str,
    admin_user: User
) -> Dict[str, Any]:
    """Adjust wallets for multiple users"""
    
    results = {
        'success': 0,
        'failed': 0,
        'errors': []
    }
    
    for user_id in user_ids:
        try:
            user = User.objects.get(id=user_id)
            if adjust_wallet_balance(user, amount, transaction_type, description, admin_user):
                results['success'] += 1
            else:
                results['failed'] += 1
                results['errors'].append(f"Failed to adjust wallet for user {user_id}")
        except User.DoesNotExist:
            results['failed'] += 1
            results['errors'].append(f"User {user_id} not found")
        except Exception as e:
            results['failed'] += 1
            results['errors'].append(f"Error for user {user_id}: {str(e)}")
    
    return results


def suspend_user(user: User, admin_user: User, reason: str = '') -> bool:
    """Suspend a user account"""
    
    try:
        user.is_active = False
        user.save(update_fields=['is_active'])
        
        # Soft delete wallet if exists
        try:
            wallet = Wallet.objects.get(user=user)
            wallet.is_active = False
            wallet.save(update_fields=['is_active'])
        except Wallet.DoesNotExist:
            pass
        
        # Log action
        log_admin_action(
            admin_user=admin_user,
            action='USER_SUSPEND',
            model_name='User',
            object_id=str(user.id),
            object_repr=user.phone_number,
            changes={'reason': reason}
        )
        
        # Create notification
        create_admin_notification(
            admin_user=admin_user,
            title='User Suspended',
            message=f"User {user.phone_number} has been suspended. Reason: {reason}",
            priority='HIGH',
            related_model='User',
            related_object_id=str(user.id)
        )
        
        return True
    
    except Exception as e:
        logger.error(f"Error suspending user: {str(e)}")
        return False


def activate_user(user: User, admin_user: User) -> bool:
    """Activate a suspended user account"""
    
    try:
        user.is_active = True
        user.save(update_fields=['is_active'])
        
        # Activate wallet if exists
        try:
            wallet = Wallet.objects.get(user=user)
            wallet.is_active = True
            wallet.save(update_fields=['is_active'])
        except Wallet.DoesNotExist:
            pass
        
        # Log action
        log_admin_action(
            admin_user=admin_user,
            action='USER_ACTIVATE',
            model_name='User',
            object_id=str(user.id),
            object_repr=user.phone_number
        )
        
        return True
    
    except Exception as e:
        logger.error(f"Error activating user: {str(e)}")
        return False
