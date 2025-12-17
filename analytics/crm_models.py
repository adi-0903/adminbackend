from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

class InactiveUserTask(models.Model):
    """Model to track CRM tasks for inactive users"""
    STATUS_CHOICES = [
        ('backlog', 'Backlog'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='crm_tasks',
        db_index=True,
        help_text="The inactive user this task is related to"
    )
    title = models.CharField(
        max_length=255,
        help_text="Brief title of the task"
    )
    description = models.TextField(
        blank=True,
        help_text="Detailed description of the work to be done"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='backlog',
        db_index=True
    )
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default='medium',
        db_index=True
    )
    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_crm_tasks',
        help_text="Admin user assigned to this task"
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_crm_tasks',
        help_text="Admin user who created this task"
    )
    due_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Expected completion date"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Actual completion timestamp"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(
        blank=True,
        help_text="Additional notes or updates"
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text="Order within the status column for drag-and-drop"
    )
    
    class Meta:
        verbose_name = 'Inactive User Task'
        verbose_name_plural = 'Inactive User Tasks'
        ordering = ['order', '-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['status', 'priority']),
            models.Index(fields=['assigned_to', 'status']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.user.phone_number} ({self.status})"
    
    def save(self, *args, **kwargs):
        if self.status == 'completed' and not self.completed_at:
            self.completed_at = timezone.now()
        elif self.status != 'completed':
            self.completed_at = None
        super().save(*args, **kwargs)
    
    @classmethod
    def get_tasks_by_user(cls, user):
        """Get all tasks for a specific inactive user"""
        return cls.objects.filter(user=user).order_by('order', '-created_at')
    
    @classmethod
    def get_tasks_by_status(cls, status):
        """Get all tasks with a specific status"""
        return cls.objects.filter(status=status).order_by('order', '-created_at')


class TaskComment(models.Model):
    """Model to store comments/updates on tasks"""
    task = models.ForeignKey(
        InactiveUserTask,
        on_delete=models.CASCADE,
        related_name='comments'
    )
    author = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Task Comment'
        verbose_name_plural = 'Task Comments'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Comment on {self.task.title} by {self.author}"
