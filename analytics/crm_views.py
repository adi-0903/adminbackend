from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q, Count
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model

from .crm_models import InactiveUserTask, TaskComment
from .crm_serializers import (
    InactiveUserTaskSerializer,
    InactiveUserTaskCreateSerializer,
    InactiveUserTaskUpdateSerializer,
    TaskStatusUpdateSerializer,
    TaskCommentSerializer,
    UserTasksSummarySerializer
)

User = get_user_model()


class InactiveUserTaskViewSet(viewsets.ModelViewSet):
    """ViewSet for managing CRM tasks for inactive users"""
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = InactiveUserTask.objects.select_related(
            'user', 'assigned_to', 'created_by'
        ).prefetch_related('comments')
        
        user_id = self.request.query_params.get('user_id')
        status_filter = self.request.query_params.get('status')
        priority_filter = self.request.query_params.get('priority')
        assigned_to = self.request.query_params.get('assigned_to')
        
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if priority_filter:
            queryset = queryset.filter(priority=priority_filter)
        if assigned_to:
            queryset = queryset.filter(assigned_to_id=assigned_to)
        
        return queryset.order_by('order', '-created_at')
    
    def get_serializer_class(self):
        if self.action == 'create':
            return InactiveUserTaskCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return InactiveUserTaskUpdateSerializer
        return InactiveUserTaskSerializer
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        
        task = InactiveUserTask.objects.select_related(
            'user', 'assigned_to', 'created_by'
        ).get(pk=serializer.instance.pk)
        
        return Response(
            InactiveUserTaskSerializer(task).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=False, methods=['get'])
    def by_user(self, request):
        """Get all tasks for a specific user"""
        user_id = request.query_params.get('user_id')
        if not user_id:
            return Response(
                {'error': 'user_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        tasks = InactiveUserTask.objects.filter(user_id=user_id).select_related(
            'user', 'assigned_to', 'created_by'
        ).prefetch_related('comments').order_by('order', '-created_at')
        
        serializer = InactiveUserTaskSerializer(tasks, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def by_status(self, request):
        """Get tasks grouped by status"""
        tasks = self.get_queryset()
        
        grouped_tasks = {
            'backlog': [],
            'in_progress': [],
            'completed': []
        }
        
        for task in tasks:
            serialized_task = InactiveUserTaskSerializer(task).data
            grouped_tasks[task.status].append(serialized_task)
        
        return Response(grouped_tasks)
    
    @action(detail=True, methods=['patch'])
    def update_status(self, request, pk=None):
        """Update task status and order"""
        task = self.get_object()
        serializer = TaskStatusUpdateSerializer(task, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        return Response(InactiveUserTaskSerializer(task).data)
    
    @action(detail=True, methods=['post'])
    def add_comment(self, request, pk=None):
        """Add a comment to a task"""
        task = self.get_object()
        
        comment_data = {
            'task': task.id,
            'comment': request.data.get('comment'),
            'author': request.user.id
        }
        
        serializer = TaskCommentSerializer(data=comment_data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['post'])
    def bulk_update_order(self, request):
        """Bulk update task orders for drag-and-drop"""
        tasks_data = request.data.get('tasks', [])
        
        if not tasks_data:
            return Response(
                {'error': 'tasks array is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        updated_tasks = []
        for task_data in tasks_data:
            task_id = task_data.get('id')
            new_status = task_data.get('status')
            new_order = task_data.get('order')
            
            if task_id:
                try:
                    task = InactiveUserTask.objects.get(pk=task_id)
                    if new_status:
                        task.status = new_status
                    if new_order is not None:
                        task.order = new_order
                    task.save()
                    updated_tasks.append(task)
                except InactiveUserTask.DoesNotExist:
                    continue
        
        serializer = InactiveUserTaskSerializer(updated_tasks, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get task summary statistics"""
        user_id = request.query_params.get('user_id')
        
        if user_id:
            tasks = InactiveUserTask.objects.filter(user_id=user_id)
        else:
            tasks = InactiveUserTask.objects.all()
        
        summary = tasks.aggregate(
            total=Count('id'),
            backlog=Count('id', filter=Q(status='backlog')),
            in_progress=Count('id', filter=Q(status='in_progress')),
            completed=Count('id', filter=Q(status='completed'))
        )
        
        return Response(summary)
    
    @action(detail=False, methods=['get'])
    def users_with_tasks(self, request):
        """Get list of users who have tasks with task counts"""
        tasks = InactiveUserTask.objects.select_related('user').values(
            'user__id', 'user__phone_number'
        ).annotate(
            backlog_count=Count('id', filter=Q(status='backlog')),
            in_progress_count=Count('id', filter=Q(status='in_progress')),
            completed_count=Count('id', filter=Q(status='completed')),
            total_tasks=Count('id')
        ).order_by('-total_tasks')
        
        users_summary = []
        for task_data in tasks:
            users_summary.append({
                'user_id': task_data['user__id'],
                'user_phone': task_data['user__phone_number'],
                'backlog_count': task_data['backlog_count'],
                'in_progress_count': task_data['in_progress_count'],
                'completed_count': task_data['completed_count'],
                'total_tasks': task_data['total_tasks']
            })
        
        return Response(users_summary)


class TaskCommentViewSet(viewsets.ModelViewSet):
    """ViewSet for managing task comments"""
    permission_classes = [IsAuthenticated]
    serializer_class = TaskCommentSerializer
    
    def get_queryset(self):
        queryset = TaskComment.objects.select_related('task', 'author')
        
        task_id = self.request.query_params.get('task_id')
        if task_id:
            queryset = queryset.filter(task_id=task_id)
        
        return queryset.order_by('-created_at')
    
    def perform_create(self, serializer):
        serializer.save(author=self.request.user)
