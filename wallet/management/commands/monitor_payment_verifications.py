import time
import logging
from django.core.management.base import BaseCommand
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta
from wallet.models import WalletTransaction
import redis
from django.conf import settings
from celery.result import AsyncResult
import json

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Monitor and clean up stale payment verification tasks'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            dest='dry_run',
            help='Show what would be done without actually doing it',
        )
        parser.add_argument(
            '--reset-stuck',
            action='store_true',
            dest='reset_stuck',
            help='Reset stuck payment verifications to FAILED status',
        )
        parser.add_argument(
            '--hours',
            type=int,
            default=24,
            help='Hours to look back for stuck transactions (default: 24)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        reset_stuck = options['reset_stuck']
        hours = options['hours']
        
        self.stdout.write(self.style.SUCCESS('Starting payment verification monitoring'))
        
        # Connect to Redis
        r = redis.from_url(settings.REDIS_URL)
        
        # Get current time
        now = timezone.now()
        cutoff_time = now - timedelta(hours=hours)
        
        # Find all pending transactions
        pending_transactions = WalletTransaction.objects.filter(
            status='PENDING',
            razorpay_order_id__isnull=False,
            created_at__lt=cutoff_time
        ).order_by('created_at')
        
        self.stdout.write(f'Found {pending_transactions.count()} pending transactions older than {hours} hours')
        
        # Check each transaction
        stuck_transactions = []
        for transaction in pending_transactions:
            # Check if there's a lock for this transaction
            lock_key = f'payment_verification_{transaction.razorpay_order_id}'
            lock_exists = r.exists(lock_key)
            
            # Check if there's a Celery task for this transaction
            task_key = f'celery-task-meta-{transaction.razorpay_order_id}'
            task_exists = r.exists(task_key)
            
            # Get task result if it exists
            task_result = None
            if task_exists:
                try:
                    task_data = r.get(task_key)
                    if task_data:
                        task_result = json.loads(task_data)
                except Exception as e:
                    logger.error(f'Error reading task data for {transaction.razorpay_order_id}: {str(e)}')
            
            # Determine transaction status
            status = 'unknown'
            if lock_exists:
                status = 'locked'
            elif task_exists and task_result:
                status = task_result.get('status', 'unknown')
            
            # Log transaction details
            self.stdout.write(
                f'Transaction {transaction.id}: '
                f'Created: {transaction.created_at}, '
                f'Status: {status}, '
                f'Lock: {"Yes" if lock_exists else "No"}, '
                f'Task: {"Yes" if task_exists else "No"}'
            )
            
            # Consider transaction stuck if:
            # 1. It's been pending for more than the cutoff time
            # 2. Either has a stale lock or a failed task
            if (lock_exists and r.ttl(lock_key) < 0) or \
               (task_exists and task_result and task_result.get('status') == 'FAILURE'):
                stuck_transactions.append(transaction)
        
        self.stdout.write(f'Found {len(stuck_transactions)} potentially stuck transactions')
        
        # Reset stuck transactions if requested
        if reset_stuck and stuck_transactions:
            if not dry_run:
                for transaction in stuck_transactions:
                    # Clear any existing locks
                    lock_key = f'payment_verification_{transaction.razorpay_order_id}'
                    r.delete(lock_key)
                    
                    # Update transaction status
                    transaction.status = 'FAILED'
                    transaction.save(update_fields=['status', 'updated_at'])
                    
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'Reset transaction {transaction.id} to FAILED status'
                        )
                    )
            else:
                for transaction in stuck_transactions:
                    self.stdout.write(
                        f'Would reset transaction {transaction.id} to FAILED status'
                    )
        
        # Generate summary
        summary = {
            'total_pending': pending_transactions.count(),
            'stuck_transactions': len(stuck_transactions),
            'hours_looked_back': hours,
            'timestamp': now.isoformat(),
        }
        
        self.stdout.write('\nSummary:')
        self.stdout.write(json.dumps(summary, indent=2))
        
        self.stdout.write(self.style.SUCCESS('Payment verification monitoring completed')) 