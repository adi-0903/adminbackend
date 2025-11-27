import time
import logging
from django.core.management.base import BaseCommand
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta
from wallet.models import WalletTransaction
import redis
from django.conf import settings
import json
from django.db.models import Avg, Count, Min, Max
from django.db.models.functions import TruncHour

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Analyze payment verification performance and identify bottlenecks'

    def add_arguments(self, parser):
        parser.add_argument(
            '--hours',
            type=int,
            default=24,
            help='Hours to analyze (default: 24)',
        )
        parser.add_argument(
            '--min-transactions',
            type=int,
            default=10,
            help='Minimum number of transactions to consider for analysis (default: 10)',
        )

    def handle(self, *args, **options):
        hours = options['hours']
        min_transactions = options['min_transactions']
        
        self.stdout.write(self.style.SUCCESS('Starting payment performance analysis'))
        
        # Get time range
        end_time = timezone.now()
        start_time = end_time - timedelta(hours=hours)
        
        # Get all transactions in the time range
        transactions = WalletTransaction.objects.filter(
            created_at__range=(start_time, end_time),
            razorpay_order_id__isnull=False
        ).order_by('created_at')
        
        total_transactions = transactions.count()
        self.stdout.write(f'Analyzing {total_transactions} transactions from {start_time} to {end_time}')
        
        # Calculate verification time for successful transactions
        successful_transactions = transactions.filter(status='SUCCESS')
        verification_times = []
        
        for transaction in successful_transactions:
            if transaction.updated_at and transaction.created_at:
                verification_time = (transaction.updated_at - transaction.created_at).total_seconds()
                verification_times.append(verification_time)
        
        # Calculate statistics
        stats = {
            'total_transactions': total_transactions,
            'successful_transactions': successful_transactions.count(),
            'failed_transactions': transactions.filter(status='FAILED').count(),
            'pending_transactions': transactions.filter(status='PENDING').count(),
            'verification_times': {
                'min': min(verification_times) if verification_times else None,
                'max': max(verification_times) if verification_times else None,
                'avg': sum(verification_times) / len(verification_times) if verification_times else None,
            }
        }
        
        # Analyze hourly patterns
        hourly_stats = transactions.annotate(
            hour=TruncHour('created_at')
        ).values('hour').annotate(
            count=Count('id'),
            success_rate=Count('id', filter=Q(status='SUCCESS')) * 100.0 / Count('id'),
            avg_verification_time=Avg(
                ExtractEpoch(F('updated_at') - F('created_at')),
                filter=Q(status='SUCCESS')
            )
        ).order_by('hour')
        
        # Identify potential bottlenecks
        bottlenecks = []
        
        # Check for high failure rates
        if stats['failed_transactions'] > 0:
            failure_rate = (stats['failed_transactions'] / total_transactions) * 100
            if failure_rate > 5:  # More than 5% failure rate
                bottlenecks.append({
                    'type': 'high_failure_rate',
                    'description': f'High failure rate of {failure_rate:.1f}%',
                    'recommendation': 'Investigate common failure patterns and improve error handling'
                })
        
        # Check for slow verification times
        if stats['verification_times']['avg'] and stats['verification_times']['avg'] > 300:  # More than 5 minutes
            bottlenecks.append({
                'type': 'slow_verification',
                'description': f'Average verification time of {stats["verification_times"]["avg"]:.1f} seconds',
                'recommendation': 'Optimize payment verification process and check external API response times'
            })
        
        # Check for high pending transactions
        if stats['pending_transactions'] > 100:  # More than 100 pending transactions
            bottlenecks.append({
                'type': 'high_pending',
                'description': f'High number of pending transactions: {stats["pending_transactions"]}',
                'recommendation': 'Increase worker concurrency or optimize task processing'
            })
        
        # Analyze hourly patterns for bottlenecks
        for hour_stat in hourly_stats:
            if hour_stat['count'] >= min_transactions:
                if hour_stat['success_rate'] < 90:  # Less than 90% success rate
                    bottlenecks.append({
                        'type': 'hourly_low_success',
                        'description': f'Low success rate of {hour_stat["success_rate"]:.1f}% at {hour_stat["hour"]}',
                        'recommendation': 'Investigate issues during this time period'
                    })
                
                if hour_stat['avg_verification_time'] and hour_stat['avg_verification_time'] > 300:
                    bottlenecks.append({
                        'type': 'hourly_slow_verification',
                        'description': f'Slow verification time of {hour_stat["avg_verification_time"]:.1f}s at {hour_stat["hour"]}',
                        'recommendation': 'Check for system load or external API issues during this period'
                    })
        
        # Generate report
        report = {
            'time_range': {
                'start': start_time.isoformat(),
                'end': end_time.isoformat(),
                'hours': hours
            },
            'statistics': stats,
            'hourly_analysis': list(hourly_stats),
            'bottlenecks': bottlenecks,
            'recommendations': [
                bottleneck['recommendation'] for bottleneck in bottlenecks
            ]
        }
        
        # Output report
        self.stdout.write('\nPerformance Analysis Report:')
        self.stdout.write(json.dumps(report, indent=2))
        
        # Output summary
        self.stdout.write('\nSummary:')
        self.stdout.write(f'Total Transactions: {stats["total_transactions"]}')
        self.stdout.write(f'Success Rate: {(stats["successful_transactions"] / total_transactions * 100):.1f}%')
        self.stdout.write(f'Average Verification Time: {stats["verification_times"]["avg"]:.1f}s')
        self.stdout.write(f'Number of Bottlenecks Found: {len(bottlenecks)}')
        
        self.stdout.write(self.style.SUCCESS('Payment performance analysis completed')) 