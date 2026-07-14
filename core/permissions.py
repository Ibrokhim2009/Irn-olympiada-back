from rest_framework import permissions

class IsSuperAdmin(permissions.BasePermission):
    """Только для суперадминов"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'superadmin'

class IsAdminUserOrReadOnly(permissions.BasePermission):
    """Админы могут менять, остальные только смотреть"""
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_authenticated and request.user.role in ['admin', 'superadmin']

class IsParticipant(permissions.BasePermission):
    """Только для зарегистрированных участников"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'participant'

class IsAdminOrCoordinatorReadOnly(permissions.BasePermission):
    """Суперадмины и админы могут делать всё, координаторы могут только смотреть, остальные не могут ничего"""
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.role in ['superadmin', 'admin']:
            return True
        if request.user.role == 'coordinator' and request.method in permissions.SAFE_METHODS:
            return True
        return False

class IsAdminOrCoordinator(permissions.BasePermission):
    """Суперадмины, админы и координаторы могут делать всё, остальные не могут ничего"""
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role in ['superadmin', 'admin', 'coordinator']
        )
