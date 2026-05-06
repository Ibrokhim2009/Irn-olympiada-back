import hashlib
import time
from django.utils import timezone
from django.core.cache import cache
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import get_user_model

User = get_user_model()

class UserActivityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Identify user
        user = request.user
        
        # If user is not yet authenticated (common in JWT-based APIs at middleware level)
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

        now = timezone.now()
        
        if user and user.is_authenticated:
            # Registered User Tracking
            cache_key = f'last-act-v2-{user.id}'
            if not cache.get(cache_key):
                User.objects.filter(id=user.id).update(last_activity=now)
                cache.set(cache_key, True, 60)
        else:
            # Anonymous Visitor Tracking
            ip = request.META.get('REMOTE_ADDR', '0.0.0.0')
            ua = request.META.get('HTTP_USER_AGENT', '')
            visitor_id = hashlib.md5(f"{ip}-{ua}".encode()).hexdigest()
            
            # Use a short-lived cache key for throttling updates to the guest list
            throttle_key = f'guest-throttle-{visitor_id}'
            if not cache.get(throttle_key):
                guests = cache.get('online_guests', {})
                current_ts = time.time()
                
                # Cleanup old guests (older than 5 minutes) and add current
                guests = {k: v for k, v in guests.items() if v > current_ts - 300}
                guests[visitor_id] = current_ts
                
                cache.set('online_guests', guests, 600) # Persist guest list for 10 min
                cache.set(throttle_key, True, 60) # Throttle this visitor for 60s

        return self.get_response(request)
