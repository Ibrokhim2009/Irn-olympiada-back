from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Olympiad, Test, Question, Registration, ExamResult

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'participant_id', 'role', 'school', 'grade', 'region')
    list_filter = ('role', 'grade', 'region')
    
    def get_fieldsets(self, request, obj=None):
        # Если это суперадмин (по роли или по флагу системного суперпользователя)
        if request.user.role == User.Role.SUPERADMIN or request.user.is_superuser:
            return UserAdmin.fieldsets + (
                ('Permissions & Role', {'fields': ('role',)}),
                ('Extra Data', {'fields': ('phone', 'birth_date', 'region', 'school', 'grade', 'participant_id')}),
            )
        
        # Для обычных админов урезаем права (нельзя менять роли и системные флаги)
        return (
            (None, {'fields': ('username', 'password')}),
            ('Personal info', {'fields': ('first_name', 'last_name', 'email')}),
            ('Additional Info', {'fields': ('phone', 'birth_date', 'region', 'school', 'grade', 'participant_id')}),
        )

    def save_model(self, request, obj, form, change):
        # Если не суперадмин пытается создать пользователя, по умолчанию это участник
        is_super = request.user.role == User.Role.SUPERADMIN or request.user.is_superuser
        if not is_super and not change:
            obj.role = User.Role.PARTICIPANT
        super().save_model(request, obj, form, change)

@admin.register(Olympiad)
class OlympiadAdmin(admin.ModelAdmin):
    list_display = ('title_ru', 'olympiad_type', 'price', 'start_datetime', 'max_participants', 'is_active')
    list_filter = ('olympiad_type', 'is_active', 'start_datetime')
    search_fields = ('title_ru', 'title_uz')

class QuestionInline(admin.TabularInline):
    model = Question
    extra = 1

@admin.register(Test)
class TestAdmin(admin.ModelAdmin):
    list_display = ('olympiad', 'title')
    inlines = [QuestionInline]

@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ('user', 'olympiad', 'payment_status', 'registered_at', 'payment_deadline')
    list_filter = ('payment_status', 'registered_at')
    search_fields = ('user__username', 'olympiad__title_ru')

@admin.register(ExamResult)
class ExamResultAdmin(admin.ModelAdmin):
    list_display = ('user', 'olympiad', 'score', 'completed_at')
    list_filter = ('completed_at',)
    readonly_fields = ('completed_at',)
