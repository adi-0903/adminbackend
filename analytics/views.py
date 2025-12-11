from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q, Count, Avg, Sum
from django.db.models.functions import ExtractHour
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
import logging

from .models import UserSegment, SystemMetrics
from .serializers import (
    UserSegmentSerializer,
    InactiveUserSerializer,
    UserAnalyticsSerializer,
    LiveMetricsSerializer
)
from user.models import User, UserActivity
from collector.models import Collection

logger = logging.getLogger('analytics')


class UserAnalyticsViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """Get overall user analytics"""
        now = timezone.now()
        today = now.date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)
        
        total_users = User.objects.count()
        active_users = User.objects.filter(last_active__gte=now - timedelta(days=3)).count()
        inactive_users = User.objects.filter(
            Q(last_active__lt=now - timedelta(days=3)) | Q(last_active__isnull=True)
        ).count()
        
        new_users_today = User.objects.filter(date_joined__date=today).count()
        new_users_week = User.objects.filter(date_joined__date__gte=week_ago).count()
        new_users_month = User.objects.filter(date_joined__date__gte=month_ago).count()
        
        data = {
            'total_users': total_users,
            'active_users': active_users,
            'inactive_users': inactive_users,
            'new_users_today': new_users_today,
            'new_users_week': new_users_week,
            'new_users_month': new_users_month,
            'churn_rate': 0.0,
            'retention_rate': 100.0,
            'avg_session_duration': 0.0,
            'top_active_users': []
        }
        
        return Response(UserAnalyticsSerializer(data).data)
    
    @action(detail=False, methods=['get'])
    def inactive_users(self, request):
        """Get list of inactive users with risk categorization"""
        days_inactive = int(request.query_params.get('days', 3))
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 50))
        risk_filter = request.query_params.get('risk', None)  # 'high', 'medium', 'low'
        
        now = timezone.now()
        cutoff_date = now - timedelta(days=days_inactive)
        
        # Get users inactive for more than the specified days
        inactive_users_qs = User.objects.filter(
            last_active__lt=cutoff_date,
            last_active__isnull=False
        ).select_related('userinformation').order_by('-last_active')
        
        # Apply risk filter if specified
        if risk_filter:
            filtered_users = []
            for user in inactive_users_qs:
                days_calc = (now - user.last_active).days
                risk = self._get_risk_level(days_calc)
                if risk == risk_filter:
                    filtered_users.append(user)
            paginated_users = filtered_users[(page - 1) * page_size:page * page_size]
            total_count = len(filtered_users)
        else:
            paginated_users = inactive_users_qs[(page - 1) * page_size:page * page_size]
            total_count = inactive_users_qs.count()
        
        users_data = []
        for user in paginated_users:
            days_inactive_calc = (now - user.last_active).days
            risk_level = self._get_risk_level(days_inactive_calc)
            
            user_data = {
                'id': user.id,
                'phone_number': user.phone_number,
                'name': getattr(user, 'userinformation', None) and user.userinformation.name,
                'email': getattr(user, 'userinformation', None) and user.userinformation.email,
                'date_joined': user.date_joined,
                'last_login': user.last_login,
                'last_active': user.last_active,
                'login_count': user.login_count,
                'total_sessions': user.total_sessions,
                'days_inactive': days_inactive_calc,
                'status': risk_level,
                'reason': f"Inactive for {days_inactive_calc} days"
            }
            users_data.append(user_data)
        
        return Response({
            'results': InactiveUserSerializer(users_data, many=True).data,
            'count': total_count,
            'page': page,
            'page_size': page_size
        })
    
    def _get_risk_level(self, days_inactive):
        """Determine risk level based on days inactive"""
        if days_inactive >= 14:
            return 'high'
        elif days_inactive >= 7:
            return 'medium'
        else:
            return 'low'


class LiveDashboardViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def metrics(self, request):
        """Get live dashboard metrics - only for normal users"""
        now = timezone.now()
        today = now.date()
        
        # Filter for normal users only (exclude superusers and staff)
        normal_users_filter = Q(is_superuser=False) & Q(is_staff=False)
        
        current_online_users = User.objects.filter(
            last_active__gte=now - timedelta(minutes=30),
            **{'is_superuser': False, 'is_staff': False}
        ).count()
        
        # Get collection data from normal users only
        today_collections = Collection.objects.filter(
            collection_date=today,
            author__is_superuser=False,
            author__is_staff=False
        ).count()
        today_revenue_obj = Collection.objects.filter(
            collection_date=today,
            author__is_superuser=False,
            author__is_staff=False
        ).aggregate(total=Sum('amount'))['total']
        today_revenue = float(today_revenue_obj) if today_revenue_obj else 0.0
        
        active_sessions = User.objects.filter(
            is_online=True,
            is_superuser=False,
            is_staff=False
        ).count()
        
        # Get recent activities from normal users only
        recent_activities = list(UserActivity.objects.filter(
            timestamp__gte=now - timedelta(hours=24),
            user__is_superuser=False,
            user__is_staff=False
        ).select_related('user').order_by('-timestamp').values(
            'user__phone_number',
            'activity_type',
            'timestamp'
        )[:20])
        
        # Get heatmap data
        user_heatmap = self._get_user_heatmap(now)
        collection_heatmap = self._get_collection_heatmap(now)
        
        # Get today's hotspots
        hotspots = self._get_today_hotspots(now)
        
        # Get performance metrics
        performance_metrics = self._get_performance_metrics(today)
        
        # Get user engagement metrics
        user_engagement = self._get_user_engagement_metrics(now)
        
        # Get business insights
        business_insights = self._get_business_insights(today)
        
        data = {
            'current_online_users': current_online_users,
            'today_collections': today_collections,
            'today_revenue': today_revenue,
            'active_sessions': active_sessions,
            'system_health': {
                'status': 'healthy',
                'response_time': '120ms',
                'uptime': '99.9%',
                'error_rate': '0.1%'
            },
            'recent_activities': recent_activities,
            'heatmap': {
                'user_activity': user_heatmap,
                'collection_activity': collection_heatmap
            },
            'hotspots': hotspots,
            'performance_metrics': performance_metrics,
            'user_engagement': user_engagement,
            'business_insights': business_insights
        }
        
        logger.info(f"Live metrics: {data}")
        return Response(data)

    @action(detail=False, methods=['get'])
    def online_users(self, request):
        """Get list of currently online users"""
        now = timezone.now()
        
        # Get users active in the last 30 minutes
        online_users = User.objects.filter(
            last_active__gte=now - timedelta(minutes=30)
        ).select_related('userinformation').values(
            'id',
            'phone_number',
            'last_active',
            'is_superuser',
            'is_staff',
            'userinformation__name',
            'userinformation__email'
        ).order_by('-last_active')
        
        users_data = []
        for user in online_users:
            users_data.append({
                'id': user['id'],
                'phone_number': user['phone_number'],
                'name': user['userinformation__name'],
                'email': user['userinformation__email'],
                'last_active': user['last_active'],
                'is_superuser': user['is_superuser'],
                'is_staff': user['is_staff']
            })
        
        return Response({
            'count': len(users_data),
            'results': users_data
        })

    @action(detail=False, methods=['get'])
    def user_details(self, request):
        """Get detailed user information with filters"""
        user_type = request.query_params.get('type', 'all')  # new_users_today, active_users_today, etc.
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 50))
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        
        now = timezone.now()
        today = now.date()
        
        # Base queryset
        users_qs = User.objects.select_related('userinformation').order_by('-date_joined')
        
        # Apply filters based on user type
        if user_type == 'new_users_today':
            users_qs = users_qs.filter(date_joined__date=today)
        elif user_type == 'active_users_today':
            users_qs = users_qs.filter(last_active__gte=now - timedelta(hours=24))
        elif user_type == 'active_users_week':
            week_start = today - timedelta(days=today.weekday())
            users_qs = users_qs.filter(last_active__gte=week_start)
        elif user_type == 'total_users':
            pass  # All users
        elif user_type == 'inactive_users':
            users_qs = users_qs.filter(
                Q(last_active__lt=now - timedelta(days=7)) | Q(last_active__isnull=True)
            )
        elif user_type == 'premium_users':
            users_qs = users_qs.filter(is_premium=True) if hasattr(User, 'is_premium') else users_qs.none()
        elif user_type == 'free_users':
            users_qs = users_qs.filter(is_premium=False) if hasattr(User, 'is_premium') else users_qs.all()
        elif user_type == 'trial_users':
            users_qs = users_qs.filter(is_trial=True) if hasattr(User, 'is_trial') else users_qs.none()
        elif user_type == 'suspended_users':
            users_qs = users_qs.filter(is_active=False)
        
        # Apply date range filter if provided
        if date_from:
            try:
                date_from_parsed = timezone.datetime.strptime(date_from, '%Y-%m-%d').date()
                users_qs = users_qs.filter(date_joined__date__gte=date_from_parsed)
            except ValueError:
                pass
        
        if date_to:
            try:
                date_to_parsed = timezone.datetime.strptime(date_to, '%Y-%m-%d').date()
                users_qs = users_qs.filter(date_joined__date__lte=date_to_parsed)
            except ValueError:
                pass
        
        # Pagination
        total_count = users_qs.count()
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_users = users_qs[start_idx:end_idx]
        
        # Build response data
        users_data = []
        for user in paginated_users:
            user_info = getattr(user, 'userinformation', None)
            users_data.append({
                'id': user.id,
                'phone_number': user.phone_number,
                'name': user_info.name if user_info else 'N/A',
                'email': user_info.email if user_info else 'N/A',
                'date_joined': user.date_joined,
                'last_active': user.last_active,
                'last_login': user.last_login,
                'is_active': user.is_active,
                'login_count': getattr(user, 'login_count', 0),
                'total_sessions': getattr(user, 'total_sessions', 0),
                'is_premium': getattr(user, 'is_premium', False),
                'is_trial': getattr(user, 'is_trial', False),
                'days_inactive': (now - user.last_active).days if user.last_active else None,
            })
        
        return Response({
            'count': total_count,
            'page': page,
            'page_size': page_size,
            'results': users_data
        })

    def _get_user_heatmap(self, now):
        """Generate user activity heatmap for the last 5 weeks - normal users only"""
        heatmap_data = []
        today = now.date()
        # Start from 5 weeks ago
        start_date = today - timedelta(weeks=5)
        
        for i in range(35):  # 5 weeks * 7 days
            date = start_date + timedelta(days=i)
            day_start = timezone.make_aware(timezone.datetime.combine(date, timezone.datetime.min.time()))
            day_end = day_start + timedelta(days=1)
            
            # Count user activities for this day - normal users only
            activity_count = UserActivity.objects.filter(
                timestamp__gte=day_start,
                timestamp__lt=day_end,
                user__is_superuser=False,
                user__is_staff=False
            ).count()
            
            heatmap_data.append({
                'date': date.isoformat(),
                'count': activity_count,
                'intensity': min(activity_count / 10.0, 1.0)  # Normalize to 0-1
            })
        
        return heatmap_data

    def _get_collection_heatmap(self, now):
        """Generate collection activity heatmap for the last 5 weeks - normal users only"""
        heatmap_data = []
        today = now.date()
        # Start from 5 weeks ago
        start_date = today - timedelta(weeks=5)
        
        for i in range(35):  # 5 weeks * 7 days
            date = start_date + timedelta(days=i)
            
            # Count collections for this day - normal users only
            collection_count = Collection.objects.filter(
                created_at__date=date,
                author__is_superuser=False,
                author__is_staff=False
            ).count()
            
            heatmap_data.append({
                'date': date.isoformat(),
                'count': collection_count,
                'intensity': min(collection_count / 5.0, 1.0)  # Normalize to 0-1
            })
        
        return heatmap_data

    def _get_performance_metrics(self, today):
        """Get performance metrics for today - normal users only"""
        # Average collection amount today - normal users only
        today_collections = Collection.objects.filter(
            collection_date=today,
            author__is_superuser=False,
            author__is_staff=False
        )
        avg_amount = today_collections.aggregate(
            avg=Avg('amount')
        )['avg'] or 0
        
        # Collections per hour - normal users only
        from django.db.models.functions import ExtractHour
        collections_per_hour = today_collections.annotate(
            hour=ExtractHour('created_at')
        ).values('hour').annotate(
            count=Count('id')
        ).aggregate(
            avg_per_hour=Avg('count')
        )['avg_per_hour'] or 0
        
        # Revenue growth rate (today vs yesterday) - normal users only
        yesterday = today - timedelta(days=1)
        today_revenue = Collection.objects.filter(
            collection_date=today,
            author__is_superuser=False,
            author__is_staff=False
        ).aggregate(total=Sum('amount'))['total'] or 0
        yesterday_revenue = Collection.objects.filter(
            collection_date=yesterday,
            author__is_superuser=False,
            author__is_staff=False
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        growth_rate = 0
        if yesterday_revenue > 0:
            growth_rate = ((today_revenue - yesterday_revenue) / yesterday_revenue) * 100
        
        return {
            'avg_collection_amount': float(avg_amount),
            'collections_per_hour': float(collections_per_hour),
            'revenue_growth_rate': round(growth_rate, 2)
        }

    def _get_user_engagement_metrics(self, now):
        """Get user engagement metrics - normal users only"""
        today = now.date()
        
        # New users today - normal users only
        new_users_today = User.objects.filter(
            date_joined__date=today,
            is_superuser=False,
            is_staff=False
        ).count()
        
        # Active users this week - normal users only
        week_start = today - timedelta(days=today.weekday())
        active_users_week = User.objects.filter(
            last_active__gte=week_start,
            is_superuser=False,
            is_staff=False
        ).count()
        
        # Active users today - normal users only
        active_users_today = User.objects.filter(
            last_active__gte=now - timedelta(hours=24),
            is_superuser=False,
            is_staff=False
        ).count()
        
        # Total registered users - normal users only
        total_users = User.objects.filter(
            is_superuser=False,
            is_staff=False
        ).count()
        
        # Inactive users (no activity in last 7 days) - normal users only
        inactive_users = User.objects.filter(
            Q(last_active__lt=now - timedelta(days=7)) | Q(last_active__isnull=True),
            is_superuser=False,
            is_staff=False
        ).count()
        
        # User retention rate (simplified - users active today vs total users) - normal users only
        active_today = User.objects.filter(
            last_active__gte=now - timedelta(hours=24),
            is_superuser=False,
            is_staff=False
        ).count()
        
        retention_rate = (active_today / total_users * 100) if total_users > 0 else 0
        
        # Average session duration (mock data - would need session tracking)
        avg_session_duration = 15  # minutes
        
        # User growth rate (this week vs last week) - normal users only
        this_week_start = today - timedelta(days=today.weekday())
        last_week_start = this_week_start - timedelta(days=7)
        last_week_end = this_week_start
        
        new_users_this_week = User.objects.filter(
            date_joined__date__gte=this_week_start,
            is_superuser=False,
            is_staff=False
        ).count()
        new_users_last_week = User.objects.filter(
            date_joined__date__gte=last_week_start,
            date_joined__date__lt=last_week_end,
            is_superuser=False,
            is_staff=False
        ).count()
        
        user_growth_rate = 0
        if new_users_last_week > 0:
            user_growth_rate = ((new_users_this_week - new_users_last_week) / new_users_last_week) * 100
        
        # User status breakdown (mock data - would need subscription tracking)
        premium_users = User.objects.filter(is_premium=True).count() if hasattr(User, 'is_premium') else total_users // 4
        free_users = total_users - premium_users
        trial_users = User.objects.filter(is_trial=True).count() if hasattr(User, 'is_trial') else total_users // 10
        suspended_users = User.objects.filter(is_active=False).count()
        
        return {
            'new_users_today': new_users_today,
            'active_users_week': active_users_week,
            'active_users_today': active_users_today,
            'user_retention_rate': round(retention_rate, 2),
            'total_users': total_users,
            'inactive_users': inactive_users,
            'avg_session_duration': avg_session_duration,
            'user_growth_rate': round(user_growth_rate, 2),
            'premium_users': premium_users,
            'free_users': free_users,
            'trial_users': trial_users,
            'suspended_users': suspended_users
        }

    def _get_business_insights(self, today):
        """Get business insights - normal users only"""
        # Today vs yesterday comparison - normal users only
        yesterday = today - timedelta(days=1)
        
        today_collections = Collection.objects.filter(
            collection_date=today,
            author__is_superuser=False,
            author__is_staff=False
        ).count()
        yesterday_collections = Collection.objects.filter(
            collection_date=yesterday,
            author__is_superuser=False,
            author__is_staff=False
        ).count()
        
        today_revenue = Collection.objects.filter(
            collection_date=today,
            author__is_superuser=False,
            author__is_staff=False
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        yesterday_revenue = Collection.objects.filter(
            collection_date=yesterday,
            author__is_superuser=False,
            author__is_staff=False
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        # Weekly trend (last 7 days) - normal users only
        week_ago = today - timedelta(days=7)
        weekly_collections = Collection.objects.filter(
            collection_date__gte=week_ago,
            author__is_superuser=False,
            author__is_staff=False
        ).count()
        
        # Top performing customers - normal users only
        top_customers = Collection.objects.filter(
            collection_date__gte=week_ago,
            author__is_superuser=False,
            author__is_staff=False
        ).values('customer__name').annotate(
            total_amount=Sum('amount'),
            collection_count=Count('id')
        ).order_by('-total_amount')[:5]
        
        return {
            'today_vs_yesterday': {
                'collections': {
                    'today': today_collections,
                    'yesterday': yesterday_collections,
                    'change': today_collections - yesterday_collections
                },
                'revenue': {
                    'today': float(today_revenue),
                    'yesterday': float(yesterday_revenue),
                    'change': float(today_revenue - yesterday_revenue)
                }
            },
            'weekly_trend': weekly_collections,
            'top_customers': list(top_customers)
        }

    def _get_today_hotspots(self, now):
        """Get today's hotspot data - normal users only"""
        today = now.date()
        
        # Peak user time (hour with most activities today) - normal users only
        peak_user_hour = UserActivity.objects.filter(
            timestamp__date=today,
            user__is_superuser=False,
            user__is_staff=False
        ).annotate(
            hour=ExtractHour('timestamp')
        ).values('hour').annotate(
            count=Count('id')
        ).order_by('-count').first()
        
        # Peak collection time (hour with most collections today) - normal users only
        peak_collection_hour = Collection.objects.filter(
            collection_date=today,
            author__is_superuser=False,
            author__is_staff=False
        ).annotate(
            hour=ExtractHour('created_at')
        ).values('hour').annotate(
            count=Count('id')
        ).order_by('-count').first()
        
        # Most active user today - normal users only
        most_active_user = UserActivity.objects.filter(
            timestamp__date=today,
            user__is_superuser=False,
            user__is_staff=False
        ).values('user__phone_number').annotate(
            count=Count('id')
        ).order_by('-count').first()
        
        # Total activities today - normal users only
        total_activities_today = UserActivity.objects.filter(
            timestamp__date=today,
            user__is_superuser=False,
            user__is_staff=False
        ).count()
        
        return {
            'peak_user_time': {
                'hour': peak_user_hour['hour'] if peak_user_hour else 0,
                'count': peak_user_hour['count'] if peak_user_hour else 0
            },
            'peak_collection_time': {
                'hour': peak_collection_hour['hour'] if peak_collection_hour else 0,
                'count': peak_collection_hour['count'] if peak_collection_hour else 0
            },
            'most_active_user': {
                'count': most_active_user['count'] if most_active_user else 0
            },
            'total_activities_today': total_activities_today
        }
