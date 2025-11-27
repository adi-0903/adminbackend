import time
import logging
from django.core.management.base import BaseCommand
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta
import redis
from django.conf import settings
import psutil
import json
import os
from celery.app.control import Control
from celery.result import AsyncResult

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Monitor Celery worker health and performance'

    def add_arguments(self, parser):
        parser.add_argument(
            '--check-queues',
            action='store_true',
            dest='check_queues',
            help='Check queue lengths and task distribution',
        )
        parser.add_argument(
            '--check-memory',
            action='store_true',
            dest='check_memory',
            help='Check memory usage of workers',
        )
        parser.add_argument(
            '--check-tasks',
            action='store_true',
            dest='check_tasks',
            help='Check for stuck or failed tasks',
        )

    def handle(self, *args, **options):
        check_queues = options['check_queues']
        check_memory = options['check_memory']
        check_tasks = options['check_tasks']
        
        self.stdout.write(self.style.SUCCESS('Starting Celery worker monitoring'))
        
        # Connect to Redis
        r = redis.from_url(settings.REDIS_URL)
        
        # Initialize Celery control
        from Milk_Saas.celery import app
        control = Control(app=app)
        
        # Get active workers
        try:
            active_workers = control.inspect().active()
            if not active_workers:
                self.stdout.write(self.style.WARNING('No active workers found'))
                return
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error getting active workers: {str(e)}'))
            return
        
        # Monitor worker health
        worker_stats = {}
        for worker_name, worker_info in active_workers.items():
            self.stdout.write(f'\nWorker: {worker_name}')
            
            # Get worker process info
            try:
                worker_pid = worker_info.get('pid')
                if worker_pid:
                    process = psutil.Process(worker_pid)
                    worker_stats[worker_name] = {
                        'pid': worker_pid,
                        'cpu_percent': process.cpu_percent(),
                        'memory_percent': process.memory_percent(),
                        'memory_info': process.memory_info()._asdict(),
                        'num_threads': process.num_threads(),
                        'num_fds': process.num_fds(),
                        'create_time': time.strftime('%Y-%m-%d %H:%M:%S', 
                                                   time.localtime(process.create_time())),
                    }
                    
                    self.stdout.write(f'PID: {worker_pid}')
                    self.stdout.write(f'CPU Usage: {worker_stats[worker_name]["cpu_percent"]}%')
                    self.stdout.write(f'Memory Usage: {worker_stats[worker_name]["memory_percent"]:.1f}%')
                    self.stdout.write(f'Threads: {worker_stats[worker_name]["num_threads"]}')
                    self.stdout.write(f'File Descriptors: {worker_stats[worker_name]["num_fds"]}')
                    self.stdout.write(f'Created: {worker_stats[worker_name]["create_time"]}')
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error getting process info: {str(e)}'))
            
            # Check current tasks
            if check_tasks:
                try:
                    current_tasks = worker_info.get('tasks', [])
                    if current_tasks:
                        self.stdout.write('\nCurrent Tasks:')
                        for task in current_tasks:
                            task_id = task.get('id')
                            task_name = task.get('name')
                            task_started = task.get('time_start')
                            if task_started:
                                started_time = time.strftime('%Y-%m-%d %H:%M:%S', 
                                                           time.localtime(task_started))
                            else:
                                started_time = 'Unknown'
                            
                            self.stdout.write(
                                f'Task: {task_name}\n'
                                f'ID: {task_id}\n'
                                f'Started: {started_time}'
                            )
                            
                            # Check if task is stuck (running for too long)
                            if task_started and time.time() - task_started > 1800:  # 30 minutes
                                self.stdout.write(
                                    self.style.WARNING(
                                        f'Task {task_id} has been running for more than 30 minutes'
                                    )
                                )
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'Error checking tasks: {str(e)}'))
        
        # Check queue lengths if requested
        if check_queues:
            self.stdout.write('\nQueue Statistics:')
            queue_stats = {}
            for queue in ['high_priority', 'default', 'low_priority']:
                try:
                    queue_length = r.llen(f'celery:{queue}')
                    queue_stats[queue] = queue_length
                    self.stdout.write(f'{queue}: {queue_length} tasks')
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'Error checking queue {queue}: {str(e)}'))
        
        # Check memory usage if requested
        if check_memory:
            self.stdout.write('\nMemory Usage:')
            system_memory = psutil.virtual_memory()
            self.stdout.write(f'System Memory: {system_memory.percent}% used')
            self.stdout.write(f'Available: {system_memory.available / (1024**3):.1f} GB')
            
            # Check Redis memory
            try:
                redis_info = r.info(section='memory')
                self.stdout.write(f'Redis Memory: {redis_info["used_memory_human"]}')
                self.stdout.write(f'Redis Peak: {redis_info["used_memory_peak_human"]}')
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error checking Redis memory: {str(e)}'))
        
        # Generate summary
        summary = {
            'timestamp': timezone.now().isoformat(),
            'active_workers': len(active_workers),
            'worker_stats': worker_stats,
            'system_memory': {
                'percent': psutil.virtual_memory().percent,
                'available_gb': psutil.virtual_memory().available / (1024**3),
            }
        }
        
        self.stdout.write('\nSummary:')
        self.stdout.write(json.dumps(summary, indent=2))
        
        self.stdout.write(self.style.SUCCESS('Celery worker monitoring completed')) 