import os
from celery import Celery
from celery.schedules import crontab, schedule
from django.conf import settings
import celery.signals
import logging

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Milk_Saas.settings')

app = Celery('Milk_Saas')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs.
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

# Configure periodic tasks with improved reliability
app.conf.beat_schedule = {
    'check-expired-payments': {
        'task': 'wallet.tasks.check_expired_payments',
        'schedule': schedule(run_every=5),  # Run every 5 seconds for faster verification
        'options': {
            'queue': 'high_priority',
            'expires': 4,  # Expire slightly before next run
            'retry': True,
            'retry_policy': {
                'max_retries': 3,
                'interval_start': 0,
                'interval_step': 0.2,
                'interval_max': 0.5,
            }
        }
    },
    'monitor-worker-health': {
        'task': 'wallet.tasks.monitor_worker_health',
        'schedule': schedule(run_every=60),  # Run every minute
        'options': {
            'queue': 'high_priority',
            'expires': 55,
        }
    },
}

# Configure task-specific settings for improved reliability
app.conf.task_default_rate_limit = '100/m'  # Default rate limit
app.conf.worker_hijack_root_logger = False  # Don't hijack root logger
app.conf.worker_log_format = '[%(asctime)s: %(levelname)s/%(processName)s] %(message)s'
app.conf.task_soft_time_limit = 180  # 3 minutes soft timeout
app.conf.task_time_limit = 300  # 5 minutes hard timeout
app.conf.worker_max_tasks_per_child = 200  # Restart worker after 200 tasks
app.conf.worker_prefetch_multiplier = 1  # Only prefetch one task at a time

# Configure acks settings for reliability
app.conf.task_acks_late = True  # Only acknowledge task after it's completed
app.conf.task_reject_on_worker_lost = True  # Reject tasks if worker is killed
app.conf.task_default_retry_delay = 15  # Default retry delay is 15 seconds
app.conf.broker_transport_options = {
    'visibility_timeout': 1800,  # 30 minutes
    'max_retries': 3,
    'interval_start': 0,
    'interval_step': 0.2,
    'interval_max': 0.5,
    'heartbeat': 10,  # Send heartbeat every 10 seconds
    'heartbeat_checkrate': 3,  # Check heartbeat every 3 seconds
}

# Error handling for system-level issues
logger = logging.getLogger(__name__)

@celery.signals.worker_ready.connect
def worker_ready(**_):
    """Log when worker is ready"""
    logger.info("Celery worker is ready!")

@celery.signals.worker_shutdown.connect
def worker_shutdown(**_):
    """Log when worker shuts down"""
    logger.warning("Celery worker is shutting down!")

@celery.signals.task_failure.connect
def task_failure(task_id, exception, traceback, **_):
    """Log task failures with detailed info"""
    logger.error(f"Task {task_id} failed: {exception}\n{traceback}")

@celery.signals.task_rejected.connect
def task_rejected(request, **_):
    """Log rejected tasks"""
    logger.warning(f"Task rejected: {request.task}")

@celery.signals.task_revoked.connect
def task_revoked(request, terminated, signum, expired, **_):
    """Log revoked tasks with reason"""
    reason = "expired" if expired else f"terminated by signal {signum}" if terminated else "revoked"
    logger.warning(f"Task {request.id} was {reason}")

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}') 