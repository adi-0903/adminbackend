from rest_framework import serializers
from .crm_models import InactiveUserTask, TaskComment
from django.contrib.auth import get_user_model

User = get_user_model()


class TaskCommentSerializer(serializers.ModelSerializer):
    author_phone = serializers.CharField(source='author.phone_number', read_only=True)
    
    class Meta:
        model = TaskComment
        fields = [
            'id', 'task', 'author', 'author_phone', 'comment', 
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'author_phone']


class InactiveUserTaskSerializer(serializers.ModelSerializer):
    user_phone = serializers.CharField(source='user.phone_number', read_only=True)
    assigned_to_phone = serializers.CharField(source='assigned_to.phone_number', read_only=True, allow_null=True)
    created_by_phone = serializers.CharField(source='created_by.phone_number', read_only=True, allow_null=True)
    comments = serializers.SerializerMethodField()
    comments_count = serializers.SerializerMethodField()
    
    def get_comments(self, obj):
        comments = obj.comments.all().order_by('-created_at')
        return TaskCommentSerializer(comments, many=True).data
    
    class Meta:
        model = InactiveUserTask
        fields = [
            'id', 'user', 'user_phone', 'title', 'description', 'status', 
            'priority', 'assigned_to', 'assigned_to_phone', 'created_by', 
            'created_by_phone', 'due_date', 'completed_at', 'created_at', 
            'updated_at', 'notes', 'order', 'comments', 'comments_count'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'completed_at']
    
    def get_comments_count(self, obj):
        return obj.comments.count()
    
    def validate(self, data):
        if 'user' in data and 'assigned_to' in data:
            if data['user'] == data['assigned_to']:
                raise serializers.ValidationError(
                    "Cannot assign task to the same user it's about"
                )
        return data


class InactiveUserTaskCreateSerializer(serializers.ModelSerializer):
    """Simplified serializer for creating tasks"""
    
    class Meta:
        model = InactiveUserTask
        fields = [
            'user', 'title', 'description', 'status', 'priority', 
            'assigned_to', 'due_date', 'notes'
        ]
    
    def create(self, validated_data):
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['created_by'] = request.user
        return super().create(validated_data)


class InactiveUserTaskUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating tasks"""
    
    class Meta:
        model = InactiveUserTask
        fields = [
            'title', 'description', 'status', 'priority', 
            'assigned_to', 'due_date', 'notes', 'order'
        ]


class TaskStatusUpdateSerializer(serializers.Serializer):
    """Serializer for updating task status and order"""
    status = serializers.ChoiceField(choices=InactiveUserTask.STATUS_CHOICES)
    order = serializers.IntegerField(min_value=0, required=False)
    
    def update(self, instance, validated_data):
        instance.status = validated_data.get('status', instance.status)
        if 'order' in validated_data:
            instance.order = validated_data['order']
        instance.save()
        return instance


class UserTasksSummarySerializer(serializers.Serializer):
    """Serializer for task summary by user"""
    user_id = serializers.IntegerField()
    user_phone = serializers.CharField()
    backlog_count = serializers.IntegerField()
    in_progress_count = serializers.IntegerField()
    completed_count = serializers.IntegerField()
    total_tasks = serializers.IntegerField()
