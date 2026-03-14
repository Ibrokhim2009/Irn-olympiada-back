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
