from rest_framework import serializers
from .models import (
    User, Olympiad, SubOlympiad, SubOlympiadGrade,
    Question, Test, Registration, ExamResult,
    Notification, Region, UserAchievement,
    SupportTicket, TicketReply, EditRequest, Book, BookOrder
)
import base64
import uuid
from django.core.files.base import ContentFile


class RegistrationSerializer(serializers.ModelSerializer):
    olympiad_title = serializers.ReadOnlyField(source='olympiad.title_ru')
    olympiad_type = serializers.ReadOnlyField(source='olympiad.olympiad_type')
    price = serializers.ReadOnlyField(source='olympiad.price')
    status_label = serializers.SerializerMethodField()
    expires_at = serializers.DateTimeField(source='payment_deadline', read_only=True)
    seconds_left = serializers.ReadOnlyField()

    class Meta:
        model = Registration
        fields = ('id', 'olympiad', 'olympiad_title', 'olympiad_type', 'price',
                  'registered_at', 'payment_status', 'status_label', 'transaction_id',
                  'teacher_name', 'teacher_phone', 'expires_at', 'seconds_left',
                  'unique_participant_id')

    def get_status_label(self, obj):
        return obj.get_payment_status_display()

    def to_representation(self, instance):
        if instance.olympiad.generate_unique_id and not instance.unique_participant_id:
            if instance.payment_status in ['paid', 'free'] or instance.olympiad.olympiad_type == 'online':
                import random
                prefix = (instance.olympiad.unique_id_prefix or "OLY").strip()
                while True:
                    new_id = f"{prefix}-{random.randint(100000, 999999)}"
                    if not Registration.objects.filter(unique_participant_id=new_id).exists():
                        instance.unique_participant_id = new_id
                        instance.save(update_fields=['unique_participant_id'])
                        break
        return super().to_representation(instance)


class RegionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Region
        fields = ('id', 'name_uz', 'name_ru', 'name_en')


class Base64ImageField(serializers.ImageField):
    def to_internal_value(self, data):
        if isinstance(data, str) and data.startswith('data:image'):
            format, imgstr = data.split(';base64,')
            ext = format.split('/')[-1]
            id = uuid.uuid4()
            data = ContentFile(base64.b64decode(imgstr), name=f"{id}.{ext}")
        return super().to_internal_value(data)


class QuestionSerializer(serializers.ModelSerializer):
    text = serializers.CharField(read_only=True)
    image = Base64ImageField(required=False, allow_null=True)

    class Meta:
        model = Question
        fields = ('id', 'test', 'text', 'image', 'options', 'correct_option',
                  'text_ru', 'text_uz', 'text_en')


class QuestionExamSerializer(serializers.ModelSerializer):
    """Serializer used during the exam — EXCLUDES correct_option."""
    text = serializers.CharField(read_only=True)
    image = Base64ImageField(required=False, allow_null=True)

    class Meta:
        model = Question
        fields = ('id', 'test', 'text', 'image', 'options',
                  'text_ru', 'text_uz', 'text_en')

    def to_representation(self, instance):
        request = self.context.get('request')
        lang = request.query_params.get('lang', 'uz') if request and hasattr(request, 'query_params') else 'uz'
        result = super().to_representation(instance)
        result['text'] = instance.get_translated('text', lang)
        return result


class TestSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, read_only=True)

    class Meta:
        model = Test
        fields = ('id', 'olympiad', 'sub_olympiad', 'sub_olympiad_grade', 'title', 'questions')

    def validate(self, attrs):
        olympiad = attrs.get('olympiad')
        sub_olympiad = attrs.get('sub_olympiad')
        sub_olympiad_grade = attrs.get('sub_olympiad_grade')

        if not olympiad and not sub_olympiad and not sub_olympiad_grade:
            raise serializers.ValidationError(
                "Необходимо указать либо олимпиаду, либо предмет, либо сессию класса."
            )
        return attrs


class SubOlympiadGradeSerializer(serializers.ModelSerializer):
    test = TestSerializer(read_only=True)
    participants_count = serializers.SerializerMethodField()
    ongoing_count = serializers.SerializerMethodField()
    finished_count = serializers.SerializerMethodField()

    class Meta:
        model = SubOlympiadGrade
        fields = ('id', 'sub_olympiad', 'grade', 'start_datetime', 'duration_minutes',
                  'is_started', 'is_completed', 'test', 
                  'participants_count', 'ongoing_count', 'finished_count')
        read_only_fields = ('sub_olympiad',)
        extra_kwargs = {
            'id': {'read_only': False, 'required': False}
        }

    def get_participants_count(self, obj):
        # Users registered for the olympiad who are in this grade
        return Registration.objects.filter(
            olympiad=obj.sub_olympiad.olympiad,
            user__grade=obj.grade
        ).exclude(payment_status='expired').count()

    def get_ongoing_count(self, obj):
        return ExamResult.objects.filter(
            sub_olympiad_grade=obj,
            completed_at__isnull=True
        ).count()

    def get_finished_count(self, obj):
        return ExamResult.objects.filter(
            sub_olympiad_grade=obj,
            completed_at__isnull=False
        ).count()


class SubOlympiadSerializer(serializers.ModelSerializer):
    title = serializers.SerializerMethodField()
    grade_sessions = SubOlympiadGradeSerializer(many=True, required=False)

    class Meta:
        model = SubOlympiad
        fields = ('id', 'olympiad', 'title', 'title_ru', 'title_uz', 'title_en',
                  'grade_sessions')
        extra_kwargs = {
            'olympiad': {'required': False},
            'id': {'read_only': False, 'required': False}
        }

    def get_title(self, obj):
        request = self.context.get('request')
        lang = request.query_params.get('lang', 'uz') if request and hasattr(request, 'query_params') else 'uz'
        return obj.get_translated('title', lang)


class ExamResultSerializer(serializers.ModelSerializer):
    sub_olympiad_grade_info = serializers.SerializerMethodField()

    class Meta:
        model = ExamResult
        fields = ('id', 'user', 'olympiad', 'sub_olympiad', 'sub_olympiad_grade',
                  'sub_olympiad_grade_info', 'score', 'start_time', 'completed_at', 'mistakes')

    def get_sub_olympiad_grade_info(self, obj):
        if obj.sub_olympiad_grade:
            return {
                'id': obj.sub_olympiad_grade.id,
                'grade': obj.sub_olympiad_grade.grade,
                'sub_olympiad_id': obj.sub_olympiad_grade.sub_olympiad.id,
                'sub_olympiad_title_ru': obj.sub_olympiad_grade.sub_olympiad.title_ru,
            }
        return None


class NotificationSerializer(serializers.ModelSerializer):
    title = serializers.SerializerMethodField()
    message = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = ('id', 'title', 'message', 'type', 'is_read', 'created_at',
                  'title_uz', 'title_ru', 'title_en', 'message_uz', 'message_ru', 'message_en')

    def get_title(self, obj):
        lang = self.context.get('request').query_params.get('lang', 'uz') if self.context.get('request') else 'uz'
        return obj.get_translated('title', lang)

    def get_message(self, obj):
        lang = self.context.get('request').query_params.get('lang', 'uz') if self.context.get('request') else 'uz'
        return obj.get_translated('message', lang)


class UserAchievementSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserAchievement
        fields = ('id', 'type', 'title_ru', 'title_uz', 'title_en', 'icon', 'earned_at')


class UserSerializer(serializers.ModelSerializer):
    registrations = RegistrationSerializer(many=True, read_only=True)
    exam_results = ExamResultSerializer(many=True, read_only=True)
    notifications = NotificationSerializer(many=True, read_only=True)
    achievements = UserAchievementSerializer(many=True, read_only=True)
    password = serializers.CharField(write_only=True, required=False)
    school = serializers.CharField(required=False, allow_blank=True, default='')

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'middle_name',
                  'phone', 'birth_date', 'region', 'school', 'grade', 'role', 'participant_id',
                  'teacher_name', 'teacher_phone', 'teachers', 'password_text', 'telegram_chat_id', 'password',
                  'registrations', 'exam_results', 'notifications', 'achievements')

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        user = super().create(validated_data)
        if password:
            user.set_password(password)
            user.password_text = password
            user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        user = super().update(instance, validated_data)
        if password:
            user.set_password(password)
            user.password_text = password
            user.save()
        return user


class UserListSerializer(serializers.ModelSerializer):
    registrations = RegistrationSerializer(many=True, read_only=True)

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'middle_name',
                  'phone', 'birth_date', 'region', 'school', 'grade', 'role', 'participant_id',
                  'teacher_name', 'teacher_phone', 'teachers', 'password_text', 'telegram_chat_id',
                  'registrations')

    

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    participant_id = serializers.CharField(read_only=True)
    username = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ('username', 'password', 'first_name', 'last_name', 'middle_name',
                  'phone', 'birth_date', 'region', 'school', 'grade', 'participant_id',
                  'teacher_name', 'teacher_phone', 'teachers')

    def create(self, validated_data):
        if not validated_data.get('username'):
            import uuid
            validated_data['username'] = f"{validated_data.get('phone')}_{uuid.uuid4().hex[:8]}"
        return User.objects.create_user(**validated_data, role=User.Role.PARTICIPANT)


class LoginRequestSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()


class OlympiadSerializer(serializers.ModelSerializer):
    title = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    seats_remaining = serializers.SerializerMethodField()
    is_registered = serializers.SerializerMethodField()
    registered_count = serializers.SerializerMethodField()

    test = TestSerializer(read_only=True)
    subs = SubOlympiadSerializer(many=True, required=False)

    class Meta:
        model = Olympiad
        fields = ('id', 'title', 'description', 'olympiad_type', 'price', 'is_free',
                  'start_datetime', 'duration_minutes', 'max_participants', 'registration_end_date',
                  'is_active', 'is_started', 'is_completed', 'seats_remaining', 'is_registered',
                  'registered_count', 'grades', 'region_ids', 'test', 'subs',
                  'generate_unique_id', 'unique_id_prefix',
                  'title_ru', 'title_uz', 'title_en', 'description_ru', 'description_uz', 'description_en')

    def get_registered_count(self, obj):
        return obj.registrations.exclude(payment_status='expired').count()

    def to_representation(self, instance):
        request = self.context.get('request')
        lang = request.query_params.get('lang', 'uz') if request and hasattr(request, 'query_params') else 'uz'
        result = super().to_representation(instance)
        result['title'] = instance.get_translated('title', lang)
        result['description'] = instance.get_translated('description', lang)
        return result

    def get_seats_remaining(self, obj):
        try:
            if not obj.max_participants:
                return 9999
            reg_count = obj.registrations.exclude(payment_status='expired').count()
            return max(0, obj.max_participants - reg_count)
        except:
            return 0

    def get_is_registered(self, obj):
        request = self.context.get('request')
        try:
            if request and request.user.is_authenticated:
                return obj.registrations.filter(user=request.user).exclude(payment_status='expired').exists()
        except:
            pass
        return False

    def create(self, validated_data):
        subs_data = validated_data.pop('subs', [])

        olympiad = Olympiad.objects.create(**validated_data)

        for sub_data in subs_data:
            grade_sessions_data = sub_data.pop('grade_sessions', [])
            sub = SubOlympiad.objects.create(olympiad=olympiad, **sub_data)

            for gs_data in grade_sessions_data:
                SubOlympiadGrade.objects.create(sub_olympiad=sub, **gs_data)

        # Авто-расчёт дат и списка классов
        self._sync_olympiad_data(olympiad)
        return olympiad

    def update(self, instance, validated_data):
        subs_data = validated_data.pop('subs', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if subs_data is not None:
            # Smart update for subs
            keep_subs = []
            for sub_data in subs_data:
                grade_sessions_data = sub_data.pop('grade_sessions', [])
                sub_id = sub_data.get('id')
                
                if sub_id:
                    # Update existing sub
                    sub = SubOlympiad.objects.get(id=sub_id, olympiad=instance)
                    for attr, value in sub_data.items():
                        setattr(sub, attr, value)
                    sub.save()
                else:
                    # Create new sub
                    sub = SubOlympiad.objects.create(olympiad=instance, **sub_data)
                
                keep_subs.append(sub.id)

                # Smart update for grade_sessions
                keep_sessions = []
                for gs_data in grade_sessions_data:
                    gs_id = gs_data.get('id')
                    if gs_id:
                        # Update existing session
                        gs = SubOlympiadGrade.objects.get(id=gs_id, sub_olympiad=sub)
                        for attr, value in gs_data.items():
                            setattr(gs, attr, value)
                        gs.save()
                    else:
                        # Create new session
                        gs = SubOlympiadGrade.objects.create(sub_olympiad=sub, **gs_data)
                    keep_sessions.append(gs.id)
                
                # Delete sessions not in keep_sessions
                SubOlympiadGrade.objects.filter(sub_olympiad=sub).exclude(id__in=keep_sessions).delete()

            # Delete subs not in keep_subs
            SubOlympiad.objects.filter(olympiad=instance).exclude(id__in=keep_subs).delete()

        self._sync_olympiad_data(instance)
        instance.save()
        return instance

    def _sync_olympiad_data(self, olympiad):
        """Пересчитывает start_datetime и список классов (grades) по сессиям."""
        from django.db.models import Min
        
        # 1. Start datetime sync - ONLY set if empty, ensuring custom dates are never overwritten after editing
        if not olympiad.start_datetime:
            earliest = SubOlympiadGrade.objects.filter(
                sub_olympiad__olympiad=olympiad,
                start_datetime__isnull=False
            ).aggregate(Min('start_datetime'))['start_datetime__min']

            if earliest:
                Olympiad.objects.filter(pk=olympiad.pk).update(start_datetime=earliest)
                olympiad.start_datetime = earliest

        # 2. Grades sync (NEW)
        all_grades = SubOlympiadGrade.objects.filter(
            sub_olympiad__olympiad=olympiad
        ).values_list('grade', flat=True).distinct()
        
        # Convert to numbers and sort
        numeric_grades = []
        for g in all_grades:
            try:
                numeric_grades.append(int(g))
            except:
                pass
        
        olympiad.grades = sorted(numeric_grades)
        Olympiad.objects.filter(pk=olympiad.pk).update(grades=olympiad.grades)

        # 3. Auto-populate unique participant IDs for existing registrations if enabled
        if getattr(olympiad, 'generate_unique_id', False):
            import random
            from django.db.models import Q
            eligible_regs = Registration.objects.filter(
                Q(unique_participant_id__isnull=True) | Q(unique_participant_id=''),
                olympiad=olympiad
            )
            prefix = (getattr(olympiad, 'unique_id_prefix', '') or "OLY").strip()
            for reg in eligible_regs:
                is_paid_or_free = reg.payment_status in ['paid', 'free'] or olympiad.olympiad_type == 'online'
                if is_paid_or_free:
                    while True:
                        new_id = f"{prefix}-{random.randint(100000, 999999)}"
                        if not Registration.objects.filter(unique_participant_id=new_id).exists():
                            reg.unique_participant_id = new_id
                            reg.save(update_fields=['unique_participant_id'])
                            break

class TicketReplySerializer(serializers.ModelSerializer):
    user_full_name = serializers.SerializerMethodField()
    user_role = serializers.ReadOnlyField(source='user.role')
    message = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = TicketReply
        fields = ('id', 'ticket', 'user', 'user_full_name', 'user_role', 'message', 'image', 'created_at')
        read_only_fields = ('user',)

    def get_user_full_name(self, obj):
        try:
            return f"{obj.user.last_name} {obj.user.first_name}".strip() or obj.user.username
        except:
            return "User"

class SupportTicketSerializer(serializers.ModelSerializer):
    replies = TicketReplySerializer(many=True, read_only=True)
    user_full_name = serializers.SerializerMethodField()
    user_participant_id = serializers.ReadOnlyField(source='user.participant_id')
    user_phone = serializers.ReadOnlyField(source='user.phone')
    status_label = serializers.SerializerMethodField()
    message = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = SupportTicket
        fields = (
            'id', 'user', 'user_full_name', 'user_participant_id', 'user_phone', 
            'subject', 'message', 'image', 'status', 'status_label', 
            'replies', 'created_at', 'updated_at'
        )
        read_only_fields = ('user', 'status')

    def get_user_full_name(self, obj):
        try:
            return f"{obj.user.last_name} {obj.user.first_name}".strip() or obj.user.username
        except:
            return "User"

    def get_status_label(self, obj):
        return dict(SupportTicket.Status.choices).get(obj.status, obj.status)

    def get_user_full_name(self, obj):
        try:
            return f"{obj.user.last_name} {obj.user.first_name}".strip() or obj.user.username
        except:
            return "User"

    def get_status_label(self, obj):
        try:
            return obj.get_status_display()
        except:
            return obj.status


class EditRequestSerializer(serializers.ModelSerializer):
    coordinator_name = serializers.SerializerMethodField()
    reviewed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = EditRequest
        fields = (
            'id', 'coordinator', 'coordinator_name',
            'target_type', 'target_id', 'target_display',
            'proposed_changes', 'current_data',
            'status', 'admin_note',
            'reviewed_by', 'reviewed_by_name',
            'created_at', 'updated_at'
        )
        read_only_fields = (
            'coordinator', 'status', 'reviewed_by',
            'reviewed_by_name', 'created_at', 'updated_at'
        )

    def get_coordinator_name(self, obj):
        try:
            return f"{obj.coordinator.last_name} {obj.coordinator.first_name}".strip() or obj.coordinator.username
        except:
            return "Unknown"

    def get_reviewed_by_name(self, obj):
        if not obj.reviewed_by:
            return None
        try:
            return f"{obj.reviewed_by.last_name} {obj.reviewed_by.first_name}".strip() or obj.reviewed_by.username
        except:
            return None


class BookSerializer(serializers.ModelSerializer):
    title = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    cover_image = Base64ImageField(required=False, allow_null=True)
    pdf_file = serializers.FileField(required=False, allow_null=True)
    telegram_link = serializers.URLField(required=False, allow_null=True, allow_blank=True)
    ordered_count = serializers.SerializerMethodField()
    remaining_stock = serializers.SerializerMethodField()

    class Meta:
        model = Book
        fields = ('id', 'title', 'description', 'title_uz', 'title_ru', 'title_en',
                  'description_uz', 'description_ru', 'description_en',
                  'book_type', 'price', 'stock', 'ordered_count', 'remaining_stock',
                  'cover_image', 'pdf_file', 'telegram_link',
                  'is_active', 'created_at')

    def get_ordered_count(self, obj):
        return obj.ordered_count()

    def get_remaining_stock(self, obj):
        return obj.remaining_stock()

    def to_representation(self, instance):
        request = self.context.get('request')
        lang = request.query_params.get('lang', 'uz') if request and hasattr(request, 'query_params') else 'uz'
        result = super().to_representation(instance)
        result['title'] = instance.get_translated('title', lang)
        result['description'] = instance.get_translated('description', lang)
        return result


class BookOrderSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    user_phone = serializers.ReadOnlyField(source='user.phone')
    book_title_ru = serializers.ReadOnlyField(source='book.title_ru')
    book_title_uz = serializers.ReadOnlyField(source='book.title_uz')
    book_title_en = serializers.ReadOnlyField(source='book.title_en')

    class Meta:
        model = BookOrder
        fields = ('id', 'user', 'user_name', 'user_phone', 'book', 'book_title_ru', 'book_title_uz', 'book_title_en',
                  'amount', 'total_price', 'delivery_address', 'receipt_image', 'status', 'rejection_reason', 'created_at', 'updated_at')

    def get_user_name(self, obj):
        try:
            return f"{obj.user.last_name} {obj.user.first_name}".strip() or obj.user.username
        except:
            return obj.user.username
