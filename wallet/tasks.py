from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import razorpay
from django.conf import settings
from decimal import Decimal
from django.db import transaction as db_transaction
from django.db.models import F, Q
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from django.db.utils import OperationalError
from typing import Optional, Dict, Any, List, Tuple
from django.core.cache import cache
import socket
from requests.exceptions import RequestException, ConnectionError, Timeout
from celery.exceptions import MaxRetriesExceededError, SoftTimeLimitExceeded
import time
import json
import traceback
import os
import psutil
import contextlib
import functools
import redis

from .models import WalletTransaction, Wallet

logger = logging.getLogger(__name__)

# Circuit breaker implementation for external service calls
class CircuitBreaker:
    """
    Circuit breaker pattern implementation to prevent repeated calls to failing services.
    """
    def __init__(self, name, failure_threshold=5, recovery_timeout=60, 
                 timeout_factor=2, max_timeout=300):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.timeout_factor = timeout_factor
        self.max_timeout = max_timeout
        self.failure_count_key = f"circuit_breaker:{name}:failures"
        self.last_failure_key = f"circuit_breaker:{name}:last_failure"
        self.timeout_key = f"circuit_breaker:{name}:timeout"
    
    @property
    def is_open(self) -> bool:
        """Check if the circuit is open (service should not be called)"""
        failure_count = cache.get(self.failure_count_key, 0)
        last_failure = cache.get(self.last_failure_key, 0)
        timeout = cache.get(self.timeout_key, self.recovery_timeout)
        
        if failure_count >= self.failure_threshold:
            time_since_failure = time.time() - last_failure
            if time_since_failure < timeout:
                logger.warning(f"Circuit {self.name} is OPEN. {time_since_failure:.2f}s since last failure, timeout: {timeout}s")
                return True
            # Allow one request through after timeout
            logger.info(f"Circuit {self.name} allowing test request after {time_since_failure:.2f}s")
        return False
    
    def record_success(self) -> None:
        """Record a successful call to the service"""
        cache.set(self.failure_count_key, 0)
        logger.debug(f"Circuit {self.name} recorded success, reset failure count")
    
    def record_failure(self) -> None:
        """Record a failed call and potentially open the circuit"""
        failure_count = cache.get(self.failure_count_key, 0) + 1
        cache.set(self.failure_count_key, failure_count)
        now = time.time()
        cache.set(self.last_failure_key, now)
        
        if failure_count >= self.failure_threshold:
            current_timeout = cache.get(self.timeout_key, self.recovery_timeout)
            new_timeout = min(current_timeout * self.timeout_factor, self.max_timeout)
            cache.set(self.timeout_key, new_timeout)
            logger.warning(f"Circuit {self.name} opening, failure count: {failure_count}, new timeout: {new_timeout}s")

# Create circuit breaker for Razorpay
razorpay_circuit = CircuitBreaker(name="razorpay", failure_threshold=5, recovery_timeout=30)

def get_razorpay_client():
    """Create a Razorpay client with improved retry configuration"""
    retry_strategy = Retry(
        total=5,  # Increased retries
        backoff_factor=0.5,
        status_forcelist=[500, 502, 503, 504, 429],  # Added 429 for rate limiting
        allowed_methods=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"],
        respect_retry_after_header=True
    )
    
    session = requests.Session()
    adapter = HTTPAdapter(
        max_retries=retry_strategy,
        pool_connections=10,
        pool_maxsize=10
    )
    session.mount("https://", adapter)
    
    return razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET),
        requests_session=session,
        timeout=30  # Set explicit timeout
    )

@contextlib.contextmanager
def timed_operation(operation_name):
    """Context manager to time operations and log if they take too long"""
    start_time = time.time()
    try:
        yield
    finally:
        duration = time.time() - start_time
        if duration > 5:  # Log slow operations (>5s)
            logger.warning(f"Operation {operation_name} took {duration:.2f}s to complete")
        else:
            logger.debug(f"Operation {operation_name} completed in {duration:.2f}s")

def get_transaction_if_pending(payment_link_id: str) -> Optional[WalletTransaction]:
    """
    Get a transaction if it exists and is still pending.
    Returns None if transaction doesn't exist or is not pending.
    """
    try:
        with timed_operation(f"get_transaction_if_pending:{payment_link_id}"):
            return WalletTransaction.objects.get(
                razorpay_order_id=payment_link_id,
                status='PENDING'
            )
    except WalletTransaction.DoesNotExist:
        return None

@shared_task(bind=True, max_retries=8, default_retry_delay=60, 
             soft_time_limit=120, time_limit=180, 
             autoretry_for=(ConnectionError, Timeout, OperationalError),
             retry_backoff=True, retry_backoff_max=300, retry_jitter=True,
             queue='high_priority')
def verify_pending_payment(self, payment_link_id: str) -> dict:
    """
    Verify a specific pending payment with improved error handling and concurrency
    Returns a dict with the result of the verification for better monitoring
    """
    verification_result = {
        'payment_id': payment_link_id,
        'status': 'unknown',
        'success': False,
        'retried': self.request.retries > 0,
        'duration': 0
    }
    
    # Use cache to prevent multiple tasks from processing the same payment simultaneously
    lock_id = f"payment_verification_{payment_link_id}"
    lock_timeout = 60  # 1 minute lock timeout
    
    # Set task start time for performance monitoring
    task_start_time = time.time()
    
    try:
        # Check for circuit breaker - don't even attempt if service is down
        if razorpay_circuit.is_open:
            logger.warning(f"Circuit breaker open, skipping payment verification for {payment_link_id}")
            verification_result['status'] = 'skipped_circuit_open'
            # Retry after the circuit might close
            raise self.retry(countdown=10, exc=None)
        
        # Try to acquire lock
        if not cache.add(lock_id, "1", timeout=lock_timeout):
            logger.debug(f"Another task is already processing payment {payment_link_id}")
            verification_result['status'] = 'concurrent_locked'
            # Retry after a short delay if locked
            raise self.retry(countdown=5, exc=None)

        # First check if transaction exists and is still pending
        transaction = get_transaction_if_pending(payment_link_id)
        if not transaction:
            logger.debug(f"No pending transaction found for payment_link_id: {payment_link_id}")
            verification_result['status'] = 'not_pending'
            return verification_result

        logger.info(f"Starting verification for payment_link_id: {payment_link_id}")
        verification_result['transaction_id'] = transaction.id
        
        # Prevent verification of very old transactions to avoid wasting resources
        if transaction.created_at < timezone.now() - timedelta(days=2):
            logger.warning(f"Transaction {transaction.id} is over 2 days old, marking as failed")
            with db_transaction.atomic():
                transaction.status = 'FAILED'
                transaction.save(update_fields=['status', 'updated_at'])
            verification_result['status'] = 'expired_transaction'
            return verification_result
            
        try:
            client = get_razorpay_client()
            
            try:
                # Try to acquire database lock with timeout handling
                try:
                    with timed_operation(f"db_transaction:{payment_link_id}"):
                        with db_transaction.atomic():
                            # Lock the transaction record
                            wallet_transaction = (WalletTransaction.objects
                                .select_related('wallet')
                                .select_for_update(nowait=True)  # Use nowait to prevent deadlocks
                                .get(id=transaction.id))

                            logger.info(f"Found transaction {wallet_transaction.id} with status: {wallet_transaction.status}")

                            # Double check status hasn't changed
                            if wallet_transaction.status != 'PENDING':
                                logger.info(f"Transaction {wallet_transaction.id} is not pending, current status: {wallet_transaction.status}")
                                verification_result['status'] = wallet_transaction.status.lower()
                                return verification_result

                            # Fetch payment data from Razorpay with circuit breaker pattern
                            try:
                                with timed_operation(f"razorpay_fetch:{payment_link_id}"):
                                    payment_data = client.payment_link.fetch(payment_link_id)
                                    # Record successful API call
                                    razorpay_circuit.record_success()
                            except (razorpay.errors.BadRequestError, RequestException, socket.error) as e:
                                # Record failed API call
                                razorpay_circuit.record_failure()
                                logger.error(f"Error fetching payment data: {str(e)}")
                                verification_result['status'] = 'razorpay_error'
                                verification_result['error'] = str(e)
                                
                                # Determine if we should retry based on the error type
                                if isinstance(e, (RequestException, socket.error)) or (
                                    isinstance(e, razorpay.errors.BadRequestError) and 
                                    "rate limit" in str(e).lower()
                                ):
                                    # Exponential backoff with jitter
                                    retry_seconds = min(60 * (2 ** self.request.retries), 3600)
                                    raise self.retry(exc=e, countdown=retry_seconds)
                                raise

                            logger.info(f"Payment data from Razorpay for {payment_link_id}: {payment_data['status']}")
                            verification_result['razorpay_status'] = payment_data['status']

                            if payment_data['status'] == 'paid':
                                recharge_amount = Decimal(str(payment_data['amount_paid'] / 100))
                                logger.info(f"Payment is successful for {payment_link_id}, amount: {recharge_amount}")
                                verification_result['status'] = 'success'
                                verification_result['amount'] = str(recharge_amount)
                                verification_result['success'] = True
                                
                                # Update main transaction
                                wallet_transaction.status = 'SUCCESS'
                                wallet_transaction.razorpay_payment_id = payment_data['payments'][0]['payment_id']
                                wallet_transaction.save(update_fields=['status', 'razorpay_payment_id', 'updated_at'])

                                # Update wallet balance - with retries on deadlock
                                retry_count = 0
                                max_retries = 3
                                while retry_count < max_retries:
                                    try:
                                        wallet = Wallet.objects.select_for_update(nowait=True).get(id=wallet_transaction.wallet_id)
                                        wallet.balance = F('balance') + recharge_amount
                                        wallet.save(update_fields=['balance', 'updated_at'])
                                        break
                                    except OperationalError as e:
                                        retry_count += 1
                                        if retry_count == max_retries or "deadlock" not in str(e).lower():
                                            raise
                                        logger.warning(f"Deadlock updating wallet balance, retry {retry_count}/{max_retries}")
                                        time.sleep(0.5) 

                                # Process bonus transaction if exists
                                bonus_transaction = (WalletTransaction.objects
                                    .select_for_update(nowait=True)
                                    .filter(parent_transaction=wallet_transaction, status='PENDING')
                                    .first())
                                
                                if bonus_transaction:
                                    logger.info(f"Processing bonus transaction for {payment_link_id}")
                                    bonus_transaction.status = 'SUCCESS'
                                    bonus_transaction.save(update_fields=['status', 'updated_at'])
                                    
                                    # Update wallet with retries on deadlock
                                    retry_count = 0
                                    while retry_count < max_retries:
                                        try:
                                            wallet = Wallet.objects.select_for_update(nowait=True).get(id=wallet_transaction.wallet_id)
                                            wallet.balance = F('balance') + bonus_transaction.amount
                                            wallet.save(update_fields=['balance', 'updated_at'])
                                            break
                                        except OperationalError as e:
                                            retry_count += 1
                                            if retry_count == max_retries or "deadlock" not in str(e).lower():
                                                raise
                                            logger.warning(f"Deadlock updating wallet bonus, retry {retry_count}/{max_retries}")
                                            time.sleep(0.5)

                                    verification_result['bonus_processed'] = True
                                    verification_result['bonus_amount'] = str(bonus_transaction.amount)

                            elif payment_data['status'] in ['cancelled', 'expired'] or (
                                payment_data['status'] == 'created' and 
                                wallet_transaction.created_at < timezone.now() - timedelta(minutes=30)
                            ):
                                logger.info(f"Payment {payment_link_id} is {payment_data['status']} or expired")
                                verification_result['status'] = 'failed'
                                # Mark as failed if cancelled, expired, or pending for > 30 mins
                                wallet_transaction.status = 'FAILED'
                                wallet_transaction.save(update_fields=['status', 'updated_at'])
                                
                                # Also mark any bonus transaction as failed
                                WalletTransaction.objects.filter(
                                    parent_transaction=wallet_transaction,
                                    status='PENDING'
                                ).update(
                                    status='FAILED',
                                    updated_at=timezone.now()
                                )
                            else:
                                logger.info(f"Payment {payment_link_id} is still in {payment_data['status']} state")
                                verification_result['status'] = 'still_pending'
                                # If still pending and not too old, retry after delay
                                if (payment_data['status'] == 'created' and 
                                    wallet_transaction.created_at > timezone.now() - timedelta(minutes=25)):
                                    # Retry with exponential backoff
                                    retry_seconds = min(60 * (2 ** self.request.retries), 900)  # Cap at 15 min
                                    raise self.retry(countdown=retry_seconds)

                except OperationalError as e:
                    if "could not obtain lock" in str(e).lower():
                        logger.info(f"Could not obtain lock for transaction {payment_link_id}, will retry")
                        verification_result['status'] = 'db_locked'
                        # Retry after 2-5 seconds with jitter
                        import random
                        raise self.retry(exc=e, countdown=2 + random.randint(0, 3))
                    raise

            except (razorpay.errors.BadRequestError, RequestException) as e:
                logger.error(f"Error verifying payment {payment_link_id}: {str(e)}")
                verification_result['status'] = 'razorpay_error'
                verification_result['error'] = str(e)
                # Only retry on network/rate limit errors
                if isinstance(e, RequestException) or "rate limit" in str(e).lower():
                    # Exponential backoff with jitter
                    retry_seconds = min(60 * (2 ** self.request.retries), 3600)  # Cap at 1 hour
                    raise self.retry(exc=e, countdown=retry_seconds)
                raise
                
        except SoftTimeLimitExceeded:
            logger.error(f"Soft time limit exceeded for payment verification {payment_link_id}")
            verification_result['status'] = 'timeout'
            # Don't raise so we can properly release the lock
            
        except MaxRetriesExceededError:
            logger.error(f"Max retries exceeded for payment {payment_link_id}")
            verification_result['status'] = 'max_retries'
            # Mark transaction as failed after max retries
            with db_transaction.atomic():
                WalletTransaction.objects.filter(
                    razorpay_order_id=payment_link_id,
                    status='PENDING'
                ).update(
                    status='FAILED',
                    updated_at=timezone.now()
                )
                
        except Exception as e:
            logger.error(f"Unexpected error verifying payment {payment_link_id}: {str(e)}\n{traceback.format_exc()}")
            verification_result['status'] = 'error'
            verification_result['error'] = str(e)
            # Don't retry on unexpected errors unless explicitly handled above
            if self.request.retries < 3:  # Limit retries for unexpected errors
                raise self.retry(exc=e, countdown=300)  # 5 minute delay
            
    finally:
        # Always release the lock
        cache.delete(lock_id)
        # Record task duration for performance monitoring
        verification_result['duration'] = round(time.time() - task_start_time, 2)
        logger.info(f"Payment verification for {payment_link_id} completed in {verification_result['duration']}s with status: {verification_result['status']}")
        
    return verification_result

@shared_task(queue='high_priority')
def check_expired_payments():
    """
    Periodic task to check for expired payments with improved concurrency
    """
    start_time = time.time()
    logger.info("Starting check for expired payments")
    
    # Check if another instance is already running to prevent overlap
    lock_id = "check_expired_payments_lock"
    if not cache.add(lock_id, "1", timeout=50):  # 50 seconds lock (less than periodic interval)
        logger.info("Another check_expired_payments task is already running. Skipping.")
        return {
            'status': 'skipped_concurrent_run',
            'duration': round(time.time() - start_time, 2)
        }
    
    try:
        # Get pending transactions in batches with smarter filtering
        # Focus on recent transactions first, then older ones
        # Separate into categories by age for better prioritization
        
        # Category 1: Recent transactions (< 30 minutes old) - check frequently
        recent_transactions = WalletTransaction.objects.filter(
            status='PENDING',
            razorpay_order_id__isnull=False,
            created_at__gte=timezone.now() - timedelta(minutes=30),
            updated_at__lte=timezone.now() - timedelta(minutes=2)  # Only if not updated recently
        ).order_by('updated_at')[:20]  # Process recent transactions in smaller batches
        
        # Category 2: Medium-age transactions (30 min - 6 hours old) - check less frequently
        medium_transactions = WalletTransaction.objects.filter(
            status='PENDING',
            razorpay_order_id__isnull=False,
            created_at__gte=timezone.now() - timedelta(hours=6),
            created_at__lt=timezone.now() - timedelta(minutes=30),
            updated_at__lte=timezone.now() - timedelta(minutes=10)  # Only if not updated in last 10 minutes
        ).order_by('updated_at')[:15]
        
        # Category 3: Older transactions (6+ hours old) - lowest priority
        older_transactions = WalletTransaction.objects.filter(
            status='PENDING',
            razorpay_order_id__isnull=False,
            created_at__lt=timezone.now() - timedelta(hours=6),
            updated_at__lte=timezone.now() - timedelta(hours=1)  # Only if not updated in last hour
        ).order_by('updated_at')[:10]
        
        # Combine all transactions for processing
        all_transactions = list(recent_transactions) + list(medium_transactions) + list(older_transactions)
        count = len(all_transactions)
        
        logger.info(f"Found {count} pending transactions to verify "
                   f"(Recent: {len(recent_transactions)}, "
                   f"Medium: {len(medium_transactions)}, "
                   f"Older: {len(older_transactions)})")
        
        # Calculate dispatch delay factor based on total count to prevent overloading
        delay_factor = max(1, min(10, count // 5))  # 1-10 seconds based on count
        
        for idx, transaction in enumerate(all_transactions):
            # Calculate dynamic countdown based on transaction age and position in batch
            if transaction in recent_transactions:
                # Recent transactions get lowest delay (2-10s)
                countdown = delay_factor + idx
            elif transaction in medium_transactions:
                # Medium transactions get medium delay (5-20s)
                countdown = (delay_factor * 2) + idx
            else:
                # Older transactions get highest delay (10-30s)
                countdown = (delay_factor * 3) + idx
                
            logger.debug(f"Dispatching verification for {transaction.razorpay_order_id} with {countdown}s delay")
            
            # Use apply_async with countdown to spread out the tasks
            verify_pending_payment.apply_async(
                args=[transaction.razorpay_order_id],
                countdown=countdown,
            )
            
        result = {
            'status': 'success',
            'transactions_found': count,
            'recent_count': len(recent_transactions),
            'medium_count': len(medium_transactions),
            'older_count': len(older_transactions),
            'delay_factor': delay_factor,
            'duration': round(time.time() - start_time, 2)
        }
        
        logger.info(f"Check expired payments completed in {result['duration']}s")
        return result
        
    except Exception as e:
        logger.error(f"Error in check_expired_payments: {str(e)}\n{traceback.format_exc()}")
        return {
            'status': 'error',
            'error': str(e),
            'duration': round(time.time() - start_time, 2)
        }
    finally:
        # Always release the lock
        cache.delete(lock_id)

@shared_task(queue='high_priority')
def monitor_worker_health():
    """
    Monitor Celery worker health and resource usage
    """
    start_time = time.time()
    try:
        # Get current process statistics
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        
        # Get system stats
        cpu_percent = psutil.cpu_percent(interval=1)
        memory_percent = psutil.virtual_memory().percent
        
        # Check Redis connection
        redis_client = redis.from_url(settings.REDIS_URL)
        redis_info = redis_client.info()
        redis_memory = redis_info.get('used_memory_human', 'N/A')
        redis_clients = redis_info.get('connected_clients', 'N/A')
        
        # Queue lengths
        queue_lengths = {}
        for queue in ['high_priority', 'default', 'low_priority']:
            try:
                queue_len = redis_client.llen(f'celery:{queue}')
                queue_lengths[queue] = queue_len
            except:
                queue_lengths[queue] = -1
        
        # Locked transactions (potential issues)
        locked_keys = redis_client.keys('payment_verification_*')
        old_locks = []
        
        # Report
        health_data = {
            'timestamp': timezone.now().isoformat(),
            'process': {
                'pid': os.getpid(),
                'memory_mb': round(memory_info.rss / (1024 * 1024), 2),
                'cpu_percent': round(process.cpu_percent(), 2),
                'threads': len(process.threads()),
                'open_files': len(process.open_files()),
                'connections': len(process.connections()),
            },
            'system': {
                'cpu_percent': cpu_percent,
                'memory_percent': memory_percent,
            },
            'redis': {
                'memory': redis_memory,
                'clients': redis_clients,
                'keys': redis_info.get('db0', {}).get('keys', 'N/A'),
            },
            'queue_lengths': queue_lengths,
            'locks': {
                'payment_verification_locks': len(locked_keys),
            },
            'metrics': {
                'pending_transactions': WalletTransaction.objects.filter(status='PENDING').count(),
                'duration': round(time.time() - start_time, 2),
            }
        }
        
        # Log a summary
        logger.info(f"Worker health check - "
                  f"Memory: {health_data['process']['memory_mb']}MB, "
                  f"CPU: {health_data['process']['cpu_percent']}%, "
                  f"Queues: {queue_lengths}, "
                  f"Pending transactions: {health_data['metrics']['pending_transactions']}")
        
        # Alert on potential issues
        if health_data['process']['memory_mb'] > 300:
            logger.warning(f"High memory usage detected: {health_data['process']['memory_mb']}MB")
            
        if len(locked_keys) > 10:
            logger.warning(f"High number of payment verification locks: {len(locked_keys)}")
            
        if health_data['metrics']['pending_transactions'] > 100:
            logger.warning(f"High number of pending transactions: {health_data['metrics']['pending_transactions']}")
        
        return health_data
        
    except Exception as e:
        logger.error(f"Error in monitor_worker_health: {str(e)}\n{traceback.format_exc()}")
        return {
            'status': 'error',
            'error': str(e),
            'duration': round(time.time() - start_time, 2)
        } 