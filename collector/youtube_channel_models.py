from __future__ import annotations

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

class ActiveManager(models.Manager):
    def get_queryset(self) -> QuerySet:
        return super().get_queryset().filter(is_active=True)

class BaseModel(models.Model):
    author: models.ForeignKey = models.ForeignKey(User, on_delete=models.CASCADE, db_index=True)
    is_active: models.BooleanField = models.BooleanField(default=True, db_index=True)
    created_at: models.DateTimeField = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True)

    objects: ActiveManager = ActiveManager()
    all_objects: models.Manager = models.Manager()

    class Meta:
        abstract = True

    def soft_delete(self) -> None:
        self.is_active = False
        self.save(update_fields=['is_active', 'updated_at'])

    
class YouTubeChannelLink(BaseModel):
    link = models.URLField(null=True,blank=True)

    def __str__(self) -> str:
        return self.link