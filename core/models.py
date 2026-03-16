from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import MinValueValidator, MaxValueValidator
import uuid

class UserManager(BaseUserManager):
    def create_user(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(username, email, password, **extra_fields)

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'superadmin') # По умолчанию суперадмин

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

# ==================== ПОЛЬЗОВАТЕЛИ ====================
class User(AbstractUser):
    class Role(models.TextChoices):
        SUPERADMIN = 'superadmin', 'Суперадмин'
        ADMIN = 'admin', 'Администратор'
        PARTICIPANT = 'participant', 'Участник'

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.PARTICIPANT)
    middle_name = models.CharField(max_length=150, null=True, blank=True)
    phone = models.CharField(max_length=20, unique=True, db_index=True)
    birth_date = models.DateField(null=True, blank=True)
    region = models.CharField(max_length=100) 
    school = models.CharField(max_length=255)
    grade = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(11)], null=True)
    
    participant_id = models.CharField(max_length=20, unique=True, null=True, blank=True, db_index=True)

    REQUIRED_FIELDS = ['phone', 'role']
    objects = UserManager()

    def save(self, *args, **kwargs):
        # Автоматически ставим флаг персонала для админов
        if self.role in [self.Role.ADMIN, self.Role.SUPERADMIN]:
            self.is_staff = True
            
        if not self.participant_id:
            import random
            while True:
                # Генерируем 10 цифр как просил юзер
                new_id = f"USR-{random.randint(1000000000, 9999999999)}"
                if not User.objects.filter(participant_id=new_id).exists():
                    self.participant_id = new_id
                    break
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
    
    start_datetime = models.DateTimeField(db_index=True)
    duration_minutes = models.PositiveIntegerField(default=60)
    
    max_participants = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)
    
    # Списки для фильтрации (например, [5, 6, 7] или [1, 2, 3])
    grades = models.JSONField(default=list, blank=True)
    region_ids = models.JSONField(default=list, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title_ru

    class Meta:
        verbose_name = "Олимпиада"
        verbose_name_plural = "Олимпиады"
        ordering = ['-start_datetime']

    def get_translated(self, field, lang):
        """Возвращает перевод или первый доступный язык"""
        val = getattr(self, f"{field}_{lang}", None)
        if val: return val
        # Если на текущем языке нет, пробуем другие по очереди
        for l in ['uz', 'ru', 'en']:
            val = getattr(self, f"{field}_{l}", None)
            if val: return val
        return ""

# ==================== ТЕСТЫ И ВОПРОСЫ ====================
class Test(models.Model):
    olympiad = models.OneToOneField(Olympiad, on_delete=models.CASCADE, related_name='test')
    title = models.CharField(max_length=255)

    def __str__(self):
        return f"Test for {self.olympiad.title_ru}"

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
        return f"Q in {self.test.olympiad.title_ru}"

class Registration(models.Model):
    class PaymentStatus(models.TextChoices):
        PENDING = 'pending', 'Ожидает оплаты'
        PROCESSING = 'processing', 'Обрабатывается'  # YANGI
        PAID = 'paid', 'Оплачено'
        FREE = 'free', 'Бесплатно'
        EXPIRED = 'expired', 'Бронь истекла'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='registrations')
    olympiad = models.ForeignKey(Olympiad, on_delete=models.CASCADE, related_name='registrations')
    
    registered_at = models.DateTimeField(auto_now_add=True)
    payment_status = models.CharField(max_length=10, choices=PaymentStatus.choices, default=PaymentStatus.PENDING, db_index=True)
    price = models.BigIntegerField(default=0)
    
    payment_deadline = models.DateTimeField(null=True, blank=True)
    
    transaction_id = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        verbose_name = "Регистрация"
        verbose_name_plural = "Регистрации"
        unique_together = ('user', 'olympiad')
        indexes = [
            models.Index(fields=['payment_status', 'payment_deadline']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.olympiad.title_ru}"

class ExamResult(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='exam_results')
    olympiad = models.ForeignKey(Olympiad, on_delete=models.CASCADE, related_name='exam_results')
    score = models.PositiveIntegerField()
    answers_json = models.JSONField(help_text="Сырые ответы пользователя для анализа")
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Результат экзамена"
        verbose_name_plural = "Результаты экзаменов"
        unique_together = ('user', 'olympiad')

    def __str__(self):
        return f"{self.user.username} - {self.score}%"
