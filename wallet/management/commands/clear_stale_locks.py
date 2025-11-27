import time
import logging
from django.core.management.base import BaseCommand
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta
from wallet.models import WalletTransaction
import redis
from django.conf import settings

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Clear stale locks and reset stuck payment transactions'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            dest='dry_run',
            help='Show what would be done without actually doing it',
        )
        parser.add_argument(
            '--reset-old',
            action='store_true',
            dest='reset_old',
            help='Reset very old pending payments to FAILED status',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        reset_old = options['reset_old']
        
        self.stdout.write(self.style.SUCCESS('Starting stale lock cleanup process'))
        
        # Connect to Redis directly to find and clear locks
        r = redis.from_url(settings.REDIS_URL)
        
        # Find payment verification locks
        payment_locks = r.keys('payment_verification_*')
        self.stdout.write(f'Found {len(payment_locks)} payment verification locks')
        
        # Check for duplicated transactions (multiple locks for same payment)
        payment_ids = [lock.decode('utf-8').replace('payment_verification_', '') 
                     for lock in payment_locks]
        
        # Find old locks (created more than 2 minutes ago - well beyond lock timeout)
        stale_locks = []
        for lock in payment_locks:
            # Check when lock was created by checking its TTL
            ttl = r.ttl(lock)
            # If TTL is < 0, key doesn't exist or has no timeout
            if 0 <= ttl <= 30:  # Only 30 seconds left on a 60 second lock (half-expired)
                stale_locks.append(lock)
                
        self.stdout.write(f'Found {len(stale_locks)} stale locks to clear')
        
        # Clear stale locks
        if not dry_run:
            for lock in stale_locks:
                r.delete(lock)
                self.stdout.write(f'Cleared lock: {lock.decode("utf-8")}')
        else:
            for lock in stale_locks:
                self.stdout.write(f'Would clear lock: {lock.decode("utf-8")}')
                
        # Find other misc locks that might be stale
        other_locks = r.keys('*_lock*')
        other_stale_locks = []
        for lock in other_locks:
            ttl = r.ttl(lock)
            if 0 <= ttl <= 10:  # Very close to expiration
                other_stale_locks.append(lock)
                
        self.stdout.write(f'Found {len(other_stale_locks)} other stale locks to clear')
        
        # Clear other stale locks
        if not dry_run:
            for lock in other_stale_locks:
                r.delete(lock)
                self.stdout.write(f'Cleared other lock: {lock.decode("utf-8")}')
        else:
            for lock in other_stale_locks:
                self.stdout.write(f'Would clear other lock: {lock.decode("utf-8")}')
        
        # Find and reset very old pending payments if requested
        if reset_old:
            # Find transactions that have been pending for more than 24 hours
            cutoff_time = timezone.now() - timedelta(hours=24)
            old_pending = WalletTransaction.objects.filter(
                status='PENDING',
                created_at__lt=cutoff_time,
                razorpay_order_id__isnull=False
            )
            
            self.stdout.write(f'Found {old_pending.count()} very old pending transactions')
            
            if not dry_run:
                updated = old_pending.update(
                    status='FAILED', 
                    updated_at=timezone.now()
                )
                self.stdout.write(self.style.SUCCESS(f'Reset {updated} old pending transactions to FAILED'))
            else:
                for tx in old_pending:
                    self.stdout.write(f'Would reset transaction {tx.id} from {tx.created_at.isoformat()} to FAILED')
        
        self.stdout.write(self.style.SUCCESS('Stale lock cleanup completed')) 