from django.utils import timezone
from django.core.cache import cache

class UserActivityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            # We update last_activity in the database only once every 5 minutes to avoid excessive writes
            # But we can also use cache for even faster tracking
            now = timezone.now()
            user = request.user
            
            # Check if we should update DB (throttle to 5 mins)
            last_update = cache.get(f'last-activity-{user.id}')
            if not last_update or (now - last_update).total_seconds() > 300:
                user.last_activity = now
                user.save(update_fields=['last_activity'])
                cache.set(f'last-activity-{user.id}', now, 3600)

        response = self.get_response(request)
        return response
