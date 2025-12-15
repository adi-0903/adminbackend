from django.utils.deprecation import MiddlewareMixin
from .models import DeviceInfo, UserSession, UserActivity
from .utils import parse_user_agent, get_client_ip
from django.utils import timezone
from datetime import timedelta


class DeviceTrackingMiddleware(MiddlewareMixin):
    """
    Middleware to track device information and user sessions
    """
    
    def process_request(self, request):
        if request.user.is_authenticated:
            user_agent = request.META.get('HTTP_USER_AGENT', '')
            ip_address = get_client_ip(request)
            
            # Parse device info
            device_data = parse_user_agent(user_agent)
            
            # Update or create device info
            device_info, created = DeviceInfo.objects.update_or_create(
                user=request.user,
                defaults={
                    'device_type': device_data['device_type'],
                    'platform': device_data['platform'],
                    'device_model': device_data['device_model'],
                    'os_version': device_data['os_version'],
                    'user_agent': device_data['user_agent'],
                    'ip_address': ip_address,
                    'last_device_used': device_data['device_model'],
                    'last_seen': timezone.now(),
                }
            )
            
            # Create or update session
            # Check if there's an active session from this device in the last 30 minutes
            thirty_minutes_ago = timezone.now() - timedelta(minutes=30)
            active_session = UserSession.objects.filter(
                user=request.user,
                device_info=device_info,
                is_active=True,
                session_start__gte=thirty_minutes_ago
            ).first()
            
            if not active_session:
                UserSession.objects.create(
                    user=request.user,
                    device_info=device_info,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
            else:
                # Update last seen
                active_session.save()
            
            # Store device info in request for later use
            request.device_info = device_info
            request.ip_address = ip_address
        
        return None
