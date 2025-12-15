from django.core.management.base import BaseCommand
from django.utils import timezone
from user.models import User
from datetime import timedelta

class Command(BaseCommand):
    help = 'Update user activity data for testing segmentation'

    def handle(self, *args, **options):
        # Get the user and update their last_active to 3 days ago
        user = User.objects.filter(is_superuser=False, is_staff=False).first()
        if user:
            three_days_ago = timezone.now() - timedelta(days=3)
            user.last_active = three_days_ago
            user.login_count = 5
            user.total_sessions = 8
            user.save()
            self.stdout.write(
                self.style.SUCCESS(
                    f'Updated user {user.phone_number}: '
                    f'last_active={user.last_active}, '
                    f'login_count={user.login_count}, '
                    f'total_sessions={user.total_sessions}'
                )
            )
        else:
            self.stdout.write(self.style.WARNING('No user found'))
