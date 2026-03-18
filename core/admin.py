from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Olympiad, Test, Question, Registration, ExamResult, Notification, Region

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'participant_id', 'role', 'school', 'grade', 'region')
    list_filter = ('role', 'grade', 'region')
    
    def get_fieldsets(self, request, obj=None):
        # Если это суперадмин (по роли или по флагу системного суперпользователя)
        if request.user.role == User.Role.SUPERADMIN or request.user.is_superuser:
            return UserAdmin.fieldsets + (
                ('Permissions & Role', {'fields': ('role',)}),
                ('Extra Data', {'fields': ('phone', 'birth_date', 'region', 'school', 'grade', 'participant_id', 'teacher_name', 'teacher_phone')}),
            )
        
        # Для обычных админов урезаем права (нельзя менять роли и системные флаги)
        return (
            (None, {'fields': ('username', 'password')}),
            ('Personal info', {'fields': ('first_name', 'last_name', 'email')}),
            ('Additional Info', {'fields': ('phone', 'birth_date', 'region', 'school', 'grade', 'participant_id', 'teacher_name', 'teacher_phone')}),
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
    list_display = ("id",'user', 'olympiad', 'payment_status', 'registered_at', 'get_teacher_name', 'get_teacher_phone')
    list_filter = ('payment_status', 'registered_at')
    search_fields = ('user__username', 'olympiad__title_ru', 'user__teacher_name')

    def get_teacher_name(self, obj):
        return obj.teacher_name or obj.user.teacher_name
    get_teacher_name.short_description = "Имя учителя"

    def get_teacher_phone(self, obj):
        return obj.teacher_phone or obj.user.teacher_phone
    get_teacher_phone.short_description = "Телефон учителя"

@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ('id', 'name_ru', 'name_uz', 'name_en')
    search_fields = ('name_ru', 'name_uz', 'name_en')

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'type', 'title_ru', 'is_read', 'created_at')
    list_filter = ('type', 'is_read', 'created_at')

@admin.register(ExamResult)
class ExamResultAdmin(admin.ModelAdmin):
    list_display = ('user', 'olympiad', 'score', 'completed_at')
    list_filter = ('completed_at',)
    readonly_fields = ('completed_at',)
