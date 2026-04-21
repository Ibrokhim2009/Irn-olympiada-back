from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
import uuid

class UserManager(BaseUserManager):
    def create_user(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(username, email, password, **extra_fields)

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'superadmin')

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self._create_user(username, email, password, **extra_fields)

    def _create_user(self, username, email, password, **extra_fields):
        if not username:
            raise ValueError('The given username must be set')
        email = self.normalize_email(email) if email else ''
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

# ==================== РЕГИОНЫ ====================
class Region(models.Model):
    name_uz = models.CharField(max_length=255)
    name_ru = models.CharField(max_length=255)
    name_en = models.CharField(max_length=255)
    
    class Meta:
        verbose_name = "Регион"
        verbose_name_plural = "Регионы"
        ordering = ['name_ru']

    def __str__(self):
        return self.name_ru

# ==================== ПОЛЬЗОВАТЕЛИ ====================
class User(AbstractUser):
    class Role(models.TextChoices):
        SUPERADMIN = 'superadmin', 'Суперадмин'
        ADMIN = 'admin', 'Администратор'
        PARTICIPANT = 'participant', 'Участник'

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.PARTICIPANT)
    middle_name = models.CharField(max_length=150, null=True, blank=True)
    phone = models.CharField(max_length=20, db_index=True)
    birth_date = models.DateField(null=True, blank=True)
    region = models.ForeignKey(Region, on_delete=models.SET_NULL, null=True, blank=True, related_name='users')
    school = models.CharField(max_length=255)
    grade = models.CharField(max_length=5, null=True, blank=True)
    
    participant_id = models.CharField(max_length=20, unique=True, null=True, blank=True, db_index=True)

    teacher_name = models.CharField(max_length=255, null=True, blank=True)
    teacher_phone = models.CharField(max_length=20, null=True, blank=True)

    REQUIRED_FIELDS = ['phone', 'role', 'teacher_name', 'teacher_phone']
    objects = UserManager()

    def save(self, *args, **kwargs):
        if self.role in [self.Role.ADMIN, self.Role.SUPERADMIN]:
            self.is_staff = True
            
        if not self.participant_id:
            import random
            while True:
                new_id = f"USR-{random.randint(1000000000, 9999999999)}"
                if not User.objects.filter(participant_id=new_id).exists():
                    self.participant_id = new_id
                    break
        
        if self.participant_id:
            self.username = self.participant_id

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.last_name} {self.first_name} ({self.participant_id})"

# ==================== ОЛИМПИАДЫ ====================
class Olympiad(models.Model):
    class Type(models.TextChoices):
        ONLINE = 'online', 'Онлайн (Бесплатно)'
        OFFLINE = 'offline', 'Офлайн (Платно)'

    title_ru = models.CharField(max_length=255, null=True, blank=True)
    title_uz = models.CharField(max_length=255, null=True, blank=True)
    title_en = models.CharField(max_length=255, null=True, blank=True)
    description_ru = models.TextField(null=True, blank=True)
    description_uz = models.TextField(null=True, blank=True)
    description_en = models.TextField(null=True, blank=True)
    
    olympiad_type = models.CharField(max_length=10, choices=Type.choices, default=Type.ONLINE, db_index=True)
    price = models.BigIntegerField(default=0, help_text="Цена в UZS (целое число)")
    is_free = models.BooleanField(default=False, verbose_name="Бесплатно")
    
    start_datetime = models.DateTimeField(db_index=True, null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(default=60, null=True, blank=True)
    
    registration_end_date = models.DateTimeField(null=True, blank=True, verbose_name="Дата окончания регистрации")
    max_participants = models.PositiveIntegerField(null=True, blank=True, default=0, verbose_name="Макс. количество участников (0 - без лимита)")
    is_active = models.BooleanField(default=True)
    
    class Status(models.TextChoices):
        UPCOMING = 'upcoming', 'Предстоит'
        ONGOING = 'ongoing', 'Идет'
        COMPLETED = 'completed', 'Завершена'

    # Списки для фильтрации участников (например, [5, 6, 7] или [1, 2, 3])
    grades = models.JSONField(default=list, blank=True)
    region_ids = models.JSONField(default=list, blank=True)
    
    is_started = models.BooleanField(default=False, verbose_name="Запущена вручную")
    is_completed = models.BooleanField(default=False, verbose_name="Завершена")
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title_ru or ''

    class Meta:
        verbose_name = "Олимпиада"
        verbose_name_plural = "Олимпиады"
        ordering = ['-created_at']

    def get_translated(self, field, lang):
        """Возвращает перевод или первый доступный язык"""
        val = getattr(self, f"{field}_{lang}", None)
        if val: return val
        for l in ['uz', 'ru', 'en']:
            val = getattr(self, f"{field}_{l}", None)
            if val: return val
        return ""

# ==================== ПРЕДМЕТЫ ОЛИМПИАДЫ ====================
class SubOlympiad(models.Model):
    """Предмет (например: Математика, Английский язык) в рамках олимпиады."""
    olympiad = models.ForeignKey(Olympiad, on_delete=models.CASCADE, related_name='subs')
    title_ru = models.CharField(max_length=255, null=True, blank=True)
    title_uz = models.CharField(max_length=255, null=True, blank=True)
    title_en = models.CharField(max_length=255, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.olympiad.title_ru} — {self.title_ru}"

    class Meta:
        verbose_name = "Предмет олимпиады"
        verbose_name_plural = "Предметы олимпиады"
        ordering = ['created_at']

    def get_translated(self, field, lang):
        val = getattr(self, f"{field}_{lang}", None)
        if val: return val
        for l in ['uz', 'ru', 'en']:
            val = getattr(self, f"{field}_{l}", None)
            if val: return val
        return ""

# ==================== СЕССИИ ПРЕДМЕТОВ ПО КЛАССАМ ====================
class SubOlympiadGrade(models.Model):
    """
    Сессия конкретного предмета для конкретного класса.
    Пример: Математика → 5 класс (11:00), Математика → 8 класс (13:00).
    Каждая сессия имеет свои: время начала, длительность, тест, и состояние запуска.
    """
    sub_olympiad = models.ForeignKey(SubOlympiad, on_delete=models.CASCADE, related_name='grade_sessions')
    grade = models.CharField(max_length=10, db_index=True, verbose_name="Класс")
    
    start_datetime = models.DateTimeField(db_index=True, null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(default=60)
    
    is_started = models.BooleanField(default=False, verbose_name="Запущена")
    is_completed = models.BooleanField(default=False, verbose_name="Завершена")
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('sub_olympiad', 'grade')
        verbose_name = "Сессия предмета для класса"
        verbose_name_plural = "Сессии предметов для классов"
        ordering = ['grade']

    def __str__(self):
        return f"{self.sub_olympiad.title_ru} ({self.grade} класс)"

# ==================== ТЕСТЫ И ВОПРОСЫ ====================
class Test(models.Model):
    """
    Тест привязывается к SubOlympiadGrade (основной способ) или напрямую к Olympiad (простая олимпиада).
    sub_olympiad оставлен для обратной совместимости.
    """
    olympiad = models.OneToOneField(Olympiad, on_delete=models.CASCADE, related_name='test', null=True, blank=True)
    sub_olympiad = models.OneToOneField(SubOlympiad, on_delete=models.CASCADE, related_name='test', null=True, blank=True)
    sub_olympiad_grade = models.OneToOneField(SubOlympiadGrade, on_delete=models.CASCADE, related_name='test', null=True, blank=True)
    title = models.CharField(max_length=255)

    def __str__(self):
        if self.sub_olympiad_grade:
            return f"Test: {self.sub_olympiad_grade.sub_olympiad.title_ru} ({self.sub_olympiad_grade.grade} кл.)"
        target = self.sub_olympiad or self.olympiad
        title = getattr(target, 'title_ru', 'Unknown') if target else 'Unknown'
        return f"Test for {title}"

class Question(models.Model):
    test = models.ForeignKey(Test, on_delete=models.CASCADE, related_name='questions')
    text_ru = models.TextField(null=True, blank=True)
    text_uz = models.TextField(null=True, blank=True)
    text_en = models.TextField(null=True, blank=True)
    image = models.ImageField(upload_to='questions/', null=True, blank=True)
    
    options = models.JSONField(help_text="Формат: [{'id': 'A', 'text': '...'}, ...]")
    correct_option = models.CharField(max_length=1, help_text="A, B, C или D")

    def get_translated(self, field, lang):
        val = getattr(self, f"{field}_{lang}", None)
        if val: return val
        for l in ['uz', 'ru', 'en']:
            val = getattr(self, f"{field}_{l}", None)
            if val: return val
        return ""

    def __str__(self):
        test = self.test
        if test.sub_olympiad_grade:
            return f"Q: {test.sub_olympiad_grade.sub_olympiad.title_ru} ({test.sub_olympiad_grade.grade} кл.)"
        target = test.sub_olympiad or test.olympiad
        title = getattr(target, 'title_ru', 'Unknown') if target else 'Unknown'
        return f"Q in {title}"

class Registration(models.Model):
    class PaymentStatus(models.TextChoices):
        PENDING = 'pending', 'Ожидает оплаты'
        PAID = 'paid', 'Оплачено'
        FREE = 'free', 'Бесплатно'
        EXPIRED = 'expired', 'Бронь истекла'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='registrations')
    olympiad = models.ForeignKey(Olympiad, on_delete=models.CASCADE, related_name='registrations')
    
    registered_at = models.DateTimeField(default=timezone.now)
    payment_status = models.CharField(max_length=10, choices=PaymentStatus.choices, default=PaymentStatus.PENDING, db_index=True)
    price = models.BigIntegerField(default=0)
    
    payment_deadline = models.DateTimeField(null=True, blank=True)
    
    transaction_id = models.CharField(max_length=100, null=True, blank=True)

    teacher_name = models.CharField(max_length=255, null=True, blank=True)
    teacher_phone = models.CharField(max_length=20, null=True, blank=True)

    class Meta:
        verbose_name = "Регистрация"
        verbose_name_plural = "Регистрации"
        unique_together = ('user', 'olympiad')
        indexes = [
            models.Index(fields=['payment_status', 'payment_deadline']),
        ]

    def save(self, *args, **kwargs):
        from django.utils import timezone
        from datetime import timedelta
        if not self.payment_deadline and self.payment_status == self.PaymentStatus.PENDING:
            base_time = self.registered_at or timezone.now()
            self.payment_deadline = base_time + timedelta(minutes=15)
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        from django.utils import timezone
        if self.payment_status not in [self.PaymentStatus.PENDING]:
            return False
        return timezone.now() > self.payment_deadline

    @property
    def seconds_left(self):
        from django.utils import timezone
        if self.payment_status not in [self.PaymentStatus.PENDING]:
            return 0
        diff = self.payment_deadline - timezone.now()
        return max(0, int(diff.total_seconds()))

    def __str__(self):
        return f"{self.user.username} - {self.olympiad.title_ru}"

class ExamResult(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='exam_results')
    olympiad = models.ForeignKey(Olympiad, on_delete=models.CASCADE, related_name='exam_results', null=True, blank=True)
    # sub_olympiad_grade — основное поле для новой системы (класс+предмет)
    sub_olympiad_grade = models.ForeignKey(SubOlympiadGrade, on_delete=models.CASCADE, related_name='exam_results', null=True, blank=True)
    # sub_olympiad — оставлен для обратной совместимости
    sub_olympiad = models.ForeignKey(SubOlympiad, on_delete=models.CASCADE, related_name='exam_results', null=True, blank=True)
    
    score = models.PositiveIntegerField(null=True, blank=True)
    answers_json = models.JSONField(null=True, blank=True, help_text="Сырые ответы пользователя для анализа")
    tab_switches = models.PositiveIntegerField(default=0, help_text="Количество переключений вкладок")
    
    start_time = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Результат экзамена"
        verbose_name_plural = "Результаты экзаменов"
        unique_together = ('user', 'olympiad', 'sub_olympiad_grade')

    def __str__(self):
        return f"{self.user.username} - {self.score}%"

class Notification(models.Model):
    class Type(models.TextChoices):
        INFO = 'info', 'Инфо'
        SUCCESS = 'success', 'Успех'
        WARNING = 'warning', 'Предупреждение'
        PAYMENT = 'payment', 'Оплата'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title_uz = models.CharField(max_length=255, null=True, blank=True)
    title_ru = models.CharField(max_length=255, null=True, blank=True)
    title_en = models.CharField(max_length=255, null=True, blank=True)
    
    message_uz = models.TextField(null=True, blank=True)
    message_ru = models.TextField(null=True, blank=True)
    message_en = models.TextField(null=True, blank=True)
    
    type = models.CharField(max_length=10, choices=Type.choices, default=Type.INFO)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def get_translated(self, field, lang):
        val = getattr(self, f"{field}_{lang}", None)
        if val: return val
        for l in ['uz', 'ru', 'en']:
            val = getattr(self, f"{field}_{l}", None)
            if val: return val
        return ""

    def __str__(self):
        return f"{self.user.username} - {self.type}"

class UserAchievement(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='achievements')
    type = models.CharField(max_length=50, help_text="early_bird, top_score, regular, etc.")
    title_ru = models.CharField(max_length=100)
    title_uz = models.CharField(max_length=100)
    title_en = models.CharField(max_length=100)
    icon = models.CharField(max_length=50, help_text="Lucide icon name")
    earned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'type')
        verbose_name = "Достижение"
        verbose_name_plural = "Достижения"

    def get_translated_title(self, lang):
        return getattr(self, f"title_{lang}", self.title_ru)

    def __str__(self):
        return f"{self.user.username} - {self.type}"
