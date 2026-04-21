from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    User, Olympiad, SubOlympiad, SubOlympiadGrade, 
    Test, Question, Registration, ExamResult, 
    Notification, Region
)

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'participant_id', 'role', 'school', 'grade', 'region')
    list_filter = ('role', 'grade', 'region')
    search_fields = ('username', 'first_name', 'last_name', 'phone', 'participant_id')
    
    def get_fieldsets(self, request, obj=None):
        if request.user.role == User.Role.SUPERADMIN or request.user.is_superuser:
            return UserAdmin.fieldsets + (
                ('Permissions & Role', {'fields': ('role',)}),
                ('Extra Data', {'fields': ('phone', 'birth_date', 'region', 'school', 'grade', 'participant_id', 'teacher_name', 'teacher_phone')}),
            )
        
        return (
            (None, {'fields': ('username', 'password')}),
            ('Personal info', {'fields': ('first_name', 'last_name', 'email')}),
            ('Additional Info', {'fields': ('phone', 'birth_date', 'region', 'school', 'grade', 'participant_id', 'teacher_name', 'teacher_phone')}),
        )

    def save_model(self, request, obj, form, change):
        is_super = request.user.role == User.Role.SUPERADMIN or request.user.is_superuser
        if not is_super and not change:
            obj.role = User.Role.PARTICIPANT
        super().save_model(request, obj, form, change)

@admin.register(Olympiad)
class OlympiadAdmin(admin.ModelAdmin):
    list_display = ('title_ru', 'olympiad_type', 'price', 'is_started', 'is_completed', 'is_active')
    list_filter = ('olympiad_type', 'is_active', 'is_started', 'is_completed')
    search_fields = ('title_ru', 'title_uz')
    actions = ['reset_to_upcoming', 'mark_as_started', 'mark_as_finished']

    @admin.action(description="Сбросить статус до 'Предстоит' (остановить)")
    def reset_to_upcoming(self, request, queryset):
        queryset.update(is_started=False, is_completed=False)

    @admin.action(description="Установить статус 'Запущена'")
    def mark_as_started(self, request, queryset):
        queryset.update(is_started=True, is_completed=False)

    @admin.action(description="Установить статус 'Завершена'")
    def mark_as_finished(self, request, queryset):
        queryset.update(is_started=True, is_completed=True)

@admin.register(SubOlympiad)
class SubOlympiadAdmin(admin.ModelAdmin):
    list_display = ('title_ru', 'olympiad')
    list_filter = ('olympiad',)
    search_fields = ('title_ru', 'title_uz')

@admin.register(SubOlympiadGrade)
class SubOlympiadGradeAdmin(admin.ModelAdmin):
    list_display = ('sub_olympiad', 'grade', 'is_started', 'is_completed', 'start_datetime')
    list_filter = ('grade', 'is_started', 'is_completed', 'sub_olympiad__olympiad')
    actions = ['reset_to_upcoming', 'mark_as_started', 'mark_as_finished']

    @admin.action(description="Сбросить статус сессии до 'Предстоит'")
    def reset_to_upcoming(self, request, queryset):
        queryset.update(is_started=False, is_completed=False)

    @admin.action(description="Запустить сессию")
    def mark_as_started(self, request, queryset):
        queryset.update(is_started=True, is_completed=False)

    @admin.action(description="Завершить сессию")
    def mark_as_finished(self, request, queryset):
        queryset.update(is_started=True, is_completed=True)

class QuestionInline(admin.TabularInline):
    model = Question
    extra = 1

@admin.register(Test)
class TestAdmin(admin.ModelAdmin):
    list_display = ('title', 'olympiad', 'sub_olympiad', 'sub_olympiad_grade')
    list_filter = ('olympiad',)
    inlines = [QuestionInline]

@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ("id",'user', 'olympiad', 'payment_status', 'registered_at', 'get_teacher_name')
    list_filter = ('payment_status', 'registered_at')
    search_fields = ('user__username', 'olympiad__title_ru', 'user__teacher_name')

    def get_teacher_name(self, obj):
        return obj.teacher_name or obj.user.teacher_name
    get_teacher_name.short_description = "Имя учителя"

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
    list_display = ('user', 'olympiad', 'sub_olympiad_grade', 'score', 'completed_at')
    list_filter = ('completed_at', 'olympiad')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')
    readonly_fields = ('completed_at',)

