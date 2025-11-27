from functools import wraps
from redis import Redis
import time

class CircuitBreaker:
    def __init__(self, redis_client, service_name, threshold=5, timeout=60):
        self.redis = redis_client
        self.service_name = service_name
        self.threshold = threshold
        self.timeout = timeout

    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            failure_count = int(self.redis.get(f"{self.service_name}_failures") or 0)
            last_failure = float(self.redis.get(f"{self.service_name}_last_failure") or 0)

            # Check if circuit is open
            if failure_count >= self.threshold:
                if time.time() - last_failure < self.timeout:
                    raise Exception(f"Circuit breaker is open for {self.service_name}")
                self.redis.set(f"{self.service_name}_failures", 0)

            try:
                result = func(*args, **kwargs)
                self.redis.set(f"{self.service_name}_failures", 0)
                return result
            except Exception as e:
                self.redis.incr(f"{self.service_name}_failures")
                self.redis.set(f"{self.service_name}_last_failure", time.time())
                raise e

        return wrapper