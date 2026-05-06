from django.utils import timezone
from django.core.cache import cache
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import get_user_model

User = get_user_model()

class UserActivityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # If user is not yet authenticated (common in JWT-based APIs at middleware level)
        # we try to manually identify them from the Authorization header
        user = request.user
        
        if not user or user.is_anonymous:
            auth_header = request.META.get('HTTP_AUTHORIZATION', '')
            if auth_header.startswith('Bearer '):
                try:
                    token_key = auth_header.split(' ')[1]
                    access_token = AccessToken(token_key)
                    user_id = access_token.get('user_id')
                    user = User.objects.get(id=user_id)
                except Exception:
                    pass

        if user and user.is_authenticated:
            now = timezone.now()
            
            # Use cache to throttle updates to once every 60 seconds (more frequent for testing)
            cache_key = f'last-act-v2-{user.id}'
            if not cache.get(cache_key):
                # Update DB
                User.objects.filter(id=user.id).update(last_activity=now)
                # Set cache for 60 seconds
                cache.set(cache_key, True, 60)

        return self.get_response(request)
