from django.db import connections
from redis import Redis
from celery.app.control import Control
import socket

class HealthCheck:
    @staticmethod
    def check_database():
        try:
            for name in connections:
                cursor = connections[name].cursor()
                cursor.execute("SELECT 1")
                row = cursor.fetchone()
                if row is None:
                    return False
            return True
        except Exception:
            return False

    @staticmethod
    def check_redis():
        try:
            redis = Redis.from_url(settings.REDIS_URL)
            return redis.ping()
        except Exception:
            return False

    @staticmethod
    def check_celery():
        try:
            control = Control(app=celery_app)
            workers = control.ping(timeout=0.5)
            return len(workers) > 0
        except Exception:
            return False

    @classmethod
    def get_system_health(cls):
        return {
            'database': cls.check_database(),
            'redis': cls.check_redis(),
            'celery': cls.check_celery(),
            'memory_usage': psutil.Process().memory_info().rss / 1024 / 1024,
            'cpu_usage': psutil.Process().cpu_percent(),
        }