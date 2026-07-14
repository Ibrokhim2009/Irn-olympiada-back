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
        user.password_text = password
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
        COORDINATOR = 'coordinator', 'Координатор'
        PARTICIPANT = 'participant', 'Участник'

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.PARTICIPANT)
    middle_name = models.CharField(max_length=150, null=True, blank=True)
    phone = models.CharField(max_length=20, db_index=True)
    birth_date = models.DateField(null=True, blank=True)
    region = models.ForeignKey(Region, on_delete=models.SET_NULL, null=True, blank=True, related_name='users')
    school = models.CharField(max_length=255)
    grade = models.CharField(max_length=5, null=True, blank=True)
    
    participant_id = models.CharField(max_length=20, unique=True, null=True, blank=True, db_index=True)
    telegram_chat_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    telegram_username = models.CharField(max_length=100, null=True, blank=True)
    password_text = models.CharField(max_length=255, null=True, blank=True, help_text="Stored plain password for admin visibility")

    teacher_name = models.CharField(max_length=255, null=True, blank=True)
    teacher_phone = models.CharField(max_length=20, null=True, blank=True)
    
    teachers = models.JSONField(default=list, blank=True, help_text="List of teachers: [{'name': '...', 'phone': '...'}]")
    
    last_activity = models.DateTimeField(null=True, blank=True, db_index=True)

    totp_secret = models.CharField(max_length=64, null=True, blank=True)
    totp_enabled = models.BooleanField(default=False)

    REQUIRED_FIELDS = ['phone', 'role', 'teacher_name', 'teacher_phone']
    objects = UserManager()

    def save(self, *args, **kwargs):
        if self.role in [self.Role.ADMIN, self.Role.SUPERADMIN, self.Role.COORDINATOR]:
            self.is_staff = True
            if not self.school:
                self.school = "Staff"
            
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
    
    generate_unique_id = models.BooleanField(default=False, verbose_name="Генерировать уникальный ID участника")
    unique_id_prefix = models.CharField(max_length=20, null=True, blank=True, verbose_name="Префикс уникального ID")

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
    
    unique_participant_id = models.CharField(max_length=50, null=True, blank=True, unique=True, db_index=True, verbose_name="Уникальный ID участника для этой олимпиады")

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
        import random
        
        update_fields = kwargs.get('update_fields')
        if update_fields is not None:
            update_fields = set(update_fields)

        if not self.payment_deadline and self.payment_status == self.PaymentStatus.PENDING:
            base_time = self.registered_at or timezone.now()
            self.payment_deadline = base_time + timedelta(minutes=30)
            if update_fields is not None:
                update_fields.add('payment_deadline')
            
        if self.olympiad.generate_unique_id and not self.unique_participant_id:
            is_paid_or_free = self.payment_status in [self.PaymentStatus.PAID, self.PaymentStatus.FREE] or self.olympiad.olympiad_type == 'online'
            if is_paid_or_free:
                prefix = (self.olympiad.unique_id_prefix or "OLY").strip()
                while True:
                    new_id = f"{prefix}-{random.randint(100000, 999999)}"
                    if not Registration.objects.filter(unique_participant_id=new_id).exists():
                        self.unique_participant_id = new_id
                        if update_fields is not None:
                            update_fields.add('unique_participant_id')
                        break

        if update_fields is not None:
            kwargs['update_fields'] = list(update_fields)

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
    mistakes = models.JSONField(default=list, blank=True, help_text="Список ошибок: [{'question_number': '5', 'user_answer': 'A', 'correct_answer': 'B', 'minus_points': 6}]")
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

# ==================== ТЕХПОДДЕРЖКА (ТИКЕТЫ) ====================
class SupportTicket(models.Model):
    class Status(models.TextChoices):
        OPEN = 'open', 'Открыт'
        IN_PROGRESS = 'in_progress', 'В процессе'
        RESOLVED = 'resolved', 'Решен'
        CLOSED = 'closed', 'Закрыт'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='support_tickets')
    subject = models.CharField(max_length=255)
    message = models.TextField(null=True, blank=True)
    image = models.ImageField(upload_to='support/', null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Тикет техподдержки"
        verbose_name_plural = "Тикеты техподдержки"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.subject} ({self.user.username})"

class TicketReply(models.Model):
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name='replies')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.TextField(null=True, blank=True)
    image = models.ImageField(upload_to='support/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Ответ на тикет"
        verbose_name_plural = "Ответы на тикеты"
        ordering = ['created_at']

    def __str__(self):
        return f"Reply to {self.ticket.subject}"


class SMSSentHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sms_history')
    template_id = models.CharField(max_length=100, db_index=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'template_id')
        verbose_name = "История отправки СМС"
        verbose_name_plural = "История отправки СМС"

    def __str__(self):
        return f"SMS to {self.user.username} (Template: {self.template_id})"


class EditRequest(models.Model):
    """
    A request from a coordinator to edit a User or ExamResult record.
    Admin can approve (apply changes) or reject the request.
    """
    class Status(models.TextChoices):
        PENDING = 'pending', 'На рассмотрении'
        APPROVED = 'approved', 'Одобрено'
        REJECTED = 'rejected', 'Отклонено'

    class TargetType(models.TextChoices):
        USER = 'user', 'Пользователь'
        RESULT = 'result', 'Результат'
        REGISTRATION = 'registration', 'Регистрация'

    coordinator = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='edit_requests_sent'
    )
    target_type = models.CharField(max_length=20, choices=TargetType.choices)
    target_id = models.PositiveIntegerField()
    target_display = models.CharField(max_length=255, blank=True, help_text="Name/label of the target for display")
    proposed_changes = models.JSONField(help_text="Dict of {field: new_value}")
    current_data = models.JSONField(blank=True, null=True, help_text="Snapshot of current values before change")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    admin_note = models.TextField(blank=True, null=True)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='edit_requests_reviewed'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Запрос на редактирование"
        verbose_name_plural = "Запросы на редактирование"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.coordinator.username} → {self.target_type}#{self.target_id} ({self.status})"


class ClickTransactions(models.Model):
    CREATED = 0
    INITIATING = 1
    SUCCESSFULLY = 2
    CANCELED = -2
    CANCELED_DURING_INIT = -1

    STATE = [
        (CREATED, "Created"),
        (INITIATING, "Initiating"),
        (SUCCESSFULLY, "Successfully"),
        (CANCELED, "Canceled after successful performed"),
        (CANCELED_DURING_INIT, "Canceled during initiation"),
    ]

    transaction_id = models.CharField(max_length=50, unique=True, verbose_name="ID транзакции Click")
    click_paydoc_id = models.CharField(max_length=50, null=True, blank=True, verbose_name="ID платежного документа Click")
    registration = models.ForeignKey('Registration', on_delete=models.SET_NULL, null=True, blank=True, related_name='click_transactions', verbose_name="Регистрация")
    amount = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Сумма")
    state = models.IntegerField(choices=STATE, default=CREATED, verbose_name="Статус")
    cancel_reason = models.CharField(max_length=255, null=True, blank=True, verbose_name="Причина отмены/Ошибка")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Создано в")
    updated_at = models.DateTimeField(auto_now=True, db_index=True, verbose_name="Изменено в")
    performed_at = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name="Выполнено в")
    cancelled_at = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name="Отменено в")

    class Meta:
        verbose_name = "CLICK Transaction"
        verbose_name_plural = "CLICK Transactions"
        ordering = ["-created_at"]
        db_table = "click_transactions"

    def __str__(self):
        return f"CLICK Transaction #{self.transaction_id} Registration: {self.registration_id} - {self.get_state_display()}"


# ==================== КНИЖНЫЙ МАГАЗИН (КНИГИ) ====================
class Book(models.Model):
    class BookType(models.TextChoices):
        FREE = 'free', 'Бесплатно'
        PAID = 'paid', 'Платно'

    title_uz = models.CharField(max_length=255, null=True, blank=True)
    title_ru = models.CharField(max_length=255, null=True, blank=True)
    title_en = models.CharField(max_length=255, null=True, blank=True)
    description_uz = models.TextField(null=True, blank=True)
    description_ru = models.TextField(null=True, blank=True)
    description_en = models.TextField(null=True, blank=True)

    book_type = models.CharField(max_length=10, choices=BookType.choices, default=BookType.FREE, db_index=True)
    price = models.BigIntegerField(default=0, help_text="Цена в UZS (целое число)")
    stock = models.PositiveIntegerField(default=0, help_text="Общее количество книг на складе (максимум для заказов)")
    cover_image = models.ImageField(upload_to='books/covers/', null=True, blank=True)
    pdf_file = models.FileField(upload_to='books/pdfs/', null=True, blank=True, help_text="Только для бесплатных книг")
    telegram_link = models.URLField(max_length=500, null=True, blank=True, help_text="Ссылка на Telegram для покупки платных книг")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Книга"
        verbose_name_plural = "Книги"
        ordering = ['-created_at']

    def __str__(self):
        return self.title_ru or self.title_uz or self.title_en or f"Book #{self.pk}"

    def get_translated(self, field, lang):
        val = getattr(self, f"{field}_{lang}", None)
        if val: return val
        for l in ['uz', 'ru', 'en']:
            val = getattr(self, f"{field}_{l}", None)
            if val: return val
        return ""

    def ordered_count(self):
        """Informational: total units ever ordered (excluding rejected orders)."""
        return self.orders.exclude(status='rejected').aggregate(
            total=models.Sum('amount')
        )['total'] or 0

    def remaining_stock(self):
        """`stock` is live inventory: decremented when an order is placed,
        restored when an order is rejected. This is simply the current count."""
        return self.stock


class BookOrder(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Ожидает проверки'
        ACCEPTED = 'accepted', 'Оплата принята'
        REJECTED = 'rejected', 'Отклонено'
        DELIVERING = 'delivering', 'Доставляется'
        DELIVERED = 'delivered', 'Доставлено'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='book_orders')
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='orders')
    amount = models.PositiveIntegerField(default=1)
    total_price = models.BigIntegerField()
    delivery_address = models.TextField()
    receipt_image = models.ImageField(upload_to='receipts/', null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    rejection_reason = models.TextField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Заказ книги"
        verbose_name_plural = "Заказы книг"
        ordering = ['-created_at']

    def __str__(self):
        book_title = self.book.title_ru or self.book.title_uz or self.book.title_en or 'Unknown Book'
        return f"Order #{self.id} - {self.user.username} - {book_title} ({self.amount} шт.)"


class VisaApplicant(models.Model):
    class Status(models.TextChoices):
        NEW = 'new', 'Новый участник'
        AWAITING_PAYMENT = 'awaiting_payment', 'Ожидается оплата'
        AWAITING_DOCUMENTS = 'awaiting_documents', 'Ожидаются документы'
        DOCUMENTS_RECEIVED = 'documents_received', 'Документы получены'
        DOCUMENTS_REVIEWING = 'documents_reviewing', 'Документы проверяются'
        NEEDS_CORRECTION = 'needs_correction', 'Требуется исправление'
        NEEDS_REPLACEMENT = 'needs_replacement', 'Требуется замена документов'
        AWAITING_TRANSLATION = 'awaiting_translation', 'Ожидается перевод'
        AWAITING_APPOINTMENT = 'awaiting_appointment', 'Ожидается запись в посольство'
        APPOINTMENT_SCHEDULED = 'appointment_scheduled', 'Запись назначена'
        READY_FOR_EMBASSY = 'ready_for_embassy', 'Готов к посольству'
        DOCUMENTS_SUBMITTED = 'documents_submitted', 'Документы поданы'
        AWAITING_DECISION = 'awaiting_decision', 'Ожидается решение'
        VISA_APPROVED = 'visa_approved', 'Виза одобрена'
        PASSPORT_RECEIVED = 'passport_received', 'Паспорт получен'
        VISA_REJECTED = 'visa_rejected', 'Виза отклонена'
        CANCELLED = 'cancelled', 'Заявка отменена'

    # Personal data
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    middle_name = models.CharField(max_length=150, null=True, blank=True)
    birth_date = models.DateField(null=True, blank=True)

    # Contacts
    phone = models.CharField(max_length=20, db_index=True)
    email = models.EmailField(null=True, blank=True)
    address = models.TextField(null=True, blank=True)

    # Passport data
    passport_number = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    passport_issue_date = models.DateField(null=True, blank=True)
    passport_expiry_date = models.DateField(null=True, blank=True)
    passport_issuing_authority = models.CharField(max_length=255, null=True, blank=True)

    # Country and program
    country = models.CharField(max_length=100, db_index=True, help_text="Страна поездки")
    program_name = models.CharField(max_length=255, null=True, blank=True, help_text="Название программы, если не привязана к олимпиаде")
    olympiad = models.ForeignKey('Olympiad', on_delete=models.SET_NULL, null=True, blank=True, related_name='visa_applicants')

    # Payment
    payment_required = models.BigIntegerField(default=0, help_text="Требуемая сумма оплаты, UZS")
    payment_paid = models.BigIntegerField(default=0, help_text="Уже оплаченная сумма, UZS")

    # Status & embassy
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.NEW, db_index=True)
    embassy_appointment_date = models.DateTimeField(null=True, blank=True)

    # Responsible staff
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_visa_applicants')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_visa_applicants')

    # Follow-up / travel logistics
    class PassportLocation(models.TextChoices):
        WITH_PARTICIPANT = 'with_participant', 'У участника'
        OFFICE = 'office', 'В офисе'
        COURIER = 'courier', 'У курьера'
        EMBASSY = 'embassy', 'В посольстве'

    last_contact_date = models.DateField(null=True, blank=True)
    documents_verified = models.BooleanField(default=False)
    ready_for_submission = models.BooleanField(default=False)
    passport_original_location = models.CharField(max_length=20, choices=PassportLocation.choices, null=True, blank=True)
    flight_date = models.DateTimeField(null=True, blank=True)
    family_head = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='family_members')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Визовый участник"
        verbose_name_plural = "Визовые участники"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.last_name} {self.first_name} ({self.country})"

    @property
    def full_name(self):
        return f"{self.last_name} {self.first_name} {self.middle_name or ''}".strip()

    @property
    def debt(self):
        return max(0, self.payment_required - self.payment_paid)

    @property
    def has_expired_documents(self):
        from django.utils import timezone
        today = timezone.now().date()
        return self.documents.filter(superseded=False, expiry_date__isnull=False, expiry_date__lt=today).exists()

    @property
    def has_documents_needing_replacement(self):
        return self.documents.filter(superseded=False, needs_replacement=True).exists()

    @property
    def readiness_score(self):
        checks = [
            self.debt <= 0,
            not self.has_expired_documents,
            not self.has_documents_needing_replacement,
            self.documents_verified,
            self.embassy_appointment_date is not None,
            self.ready_for_submission,
        ]
        return round(100 * sum(1 for c in checks if c) / len(checks))


class VisaDocument(models.Model):
    class Category(models.TextChoices):
        SCAN = 'scan', 'Скан документа'
        PHOTO = 'photo', 'Фотография'
        RECEIPT = 'receipt', 'Чек об оплате'
        INVITATION = 'invitation', 'Приглашение'
        QUESTIONNAIRE = 'questionnaire', 'Анкета'
        TRANSLATION = 'translation', 'Перевод'
        APPOINTMENT_CONFIRMATION = 'appointment_confirmation', 'Подтверждение записи'
        READY_PACKAGE = 'ready_package', 'Готовый пакет документов'

    applicant = models.ForeignKey(VisaApplicant, on_delete=models.CASCADE, related_name='documents')
    category = models.CharField(max_length=30, choices=Category.choices)
    file = models.FileField(upload_to='visa/documents/')
    expiry_date = models.DateField(null=True, blank=True)
    needs_replacement = models.BooleanField(default=False)
    notes = models.CharField(max_length=255, null=True, blank=True)

    previous_version = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='next_versions')
    superseded = models.BooleanField(default=False)

    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='uploaded_visa_documents')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Визовый документ"
        verbose_name_plural = "Визовые документы"
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.get_category_display()} — {self.applicant.full_name}"

    @property
    def is_expired(self):
        if not self.expiry_date:
            return False
        from django.utils import timezone
        return self.expiry_date < timezone.now().date()


class VisaNote(models.Model):
    applicant = models.ForeignKey(VisaApplicant, on_delete=models.CASCADE, related_name='notes')
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='visa_notes')
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Заметка (виза)"
        verbose_name_plural = "Заметки (виза)"
        ordering = ['-created_at']

    def __str__(self):
        return f"Note on {self.applicant.full_name} by {self.author}"


class VisaTask(models.Model):
    applicant = models.ForeignKey(VisaApplicant, on_delete=models.CASCADE, related_name='tasks')
    title = models.CharField(max_length=255)
    due_date = models.DateField(null=True, blank=True)
    done = models.BooleanField(default=False)
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='visa_tasks')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Задача (виза)"
        verbose_name_plural = "Задачи (виза)"
        ordering = ['done', 'due_date', '-created_at']

    def __str__(self):
        return f"{self.title} — {self.applicant.full_name}"


class VisaAuditLog(models.Model):
    class Action(models.TextChoices):
        CREATED = 'created', 'Создан'
        UPDATED = 'updated', 'Изменён'
        STATUS_CHANGED = 'status_changed', 'Статус изменён'
        DOCUMENT_UPLOADED = 'document_uploaded', 'Документ загружен'
        DOCUMENT_DELETED = 'document_deleted', 'Документ удалён'
        NOTE_ADDED = 'note_added', 'Заметка добавлена'
        TASK_DONE = 'task_done', 'Задача выполнена'

    applicant = models.ForeignKey(VisaApplicant, on_delete=models.CASCADE, related_name='audit_logs')
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='visa_audit_actions')
    action = models.CharField(max_length=30, choices=Action.choices)
    detail = models.CharField(max_length=500, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Журнал действий (виза)"
        verbose_name_plural = "Журнал действий (виза)"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_action_display()} — {self.applicant.full_name}"


