from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework import viewsets
from rest_framework.permissions import AllowAny
from django.http import HttpRequest
from .youtube_channel_models import YouTubeChannelLink
from typing import Any

from collector import youtube_channel_models

class YouTubeLinkViewSet(viewsets.ViewSet):
    permission_classes = [AllowAny]

    @action(detail=False, methods=['get'], url_path='youtube-link')
    def yt_link(self, request: HttpRequest, *args: Any, **kwargs: Any) -> Response:
        # Get only the most recent active dairy information
        yt_link = YouTubeChannelLink.objects.filter(
            is_active=True
        ).order_by('-created_at').first()

        if yt_link:
            return Response(
                {
                    "link": yt_link.link
                }
            )
        return Response(
            {
                'link': ''
            }
        )
