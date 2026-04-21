from rest_framework import serializers
from .models import (
    User, Olympiad, SubOlympiad, SubOlympiadGrade,
    Question, Test, Registration, ExamResult,
    Notification, Region, UserAchievement
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
                  'teacher_name', 'teacher_phone', 'expires_at', 'seconds_left')

    def get_status_label(self, obj):
        return obj.get_payment_status_display()


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

    class Meta:
        model = SubOlympiadGrade
        fields = ('id', 'sub_olympiad', 'grade', 'start_datetime', 'duration_minutes',
                  'is_started', 'is_completed', 'test')
        read_only_fields = ('sub_olympiad',)


class SubOlympiadSerializer(serializers.ModelSerializer):
    title = serializers.SerializerMethodField()
    grade_sessions = SubOlympiadGradeSerializer(many=True, required=False)

    class Meta:
        model = SubOlympiad
        fields = ('id', 'olympiad', 'title', 'title_ru', 'title_uz', 'title_en',
                  'grade_sessions')
        extra_kwargs = {
            'olympiad': {'required': False}
        }

    def get_title(self, obj):
        request = self.context.get('request')
        lang = request.query_params.get('lang', 'uz') if request and hasattr(request, 'query_params') else 'uz'
        return obj.get_translated('title', lang)


class ExamResultSerializer(serializers.ModelSerializer):
    sub_olympiad_grade_info = serializers.SerializerMethodField()

    class Meta:
        model = ExamResult
        fields = ('id', 'olympiad', 'sub_olympiad', 'sub_olympiad_grade',
                  'sub_olympiad_grade_info', 'score', 'completed_at')

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

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'middle_name',
                  'phone', 'birth_date', 'region', 'school', 'grade', 'role', 'participant_id',
                  'teacher_name', 'teacher_phone',
                  'registrations', 'exam_results', 'notifications', 'achievements')


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    participant_id = serializers.CharField(read_only=True)
    username = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ('username', 'password', 'first_name', 'last_name', 'middle_name',
                  'phone', 'birth_date', 'region', 'school', 'grade', 'participant_id',
                  'teacher_name', 'teacher_phone')

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
            instance.subs.all().delete()
            for sub_data in subs_data:
                grade_sessions_data = sub_data.pop('grade_sessions', [])
                sub = SubOlympiad.objects.create(olympiad=instance, **sub_data)
                for gs_data in grade_sessions_data:
                    SubOlympiadGrade.objects.create(sub_olympiad=sub, **gs_data)

        self._sync_olympiad_data(instance)
        instance.save()
        return instance

    def _sync_olympiad_data(self, olympiad):
        """Пересчитывает start_datetime и список классов (grades) по сессиям."""
        from django.db.models import Min
        
        # 1. Start datetime sync
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
