from rest_framework import serializers
from .models import User, Olympiad, SubOlympiad, Question, Test, Registration, ExamResult, Notification, Region, UserAchievement
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
        fields = ('id', 'test', 'text', 'image', 'options',
                  'text_ru', 'text_uz', 'text_en')

class QuestionExamSerializer(serializers.ModelSerializer):
    """Serializer used during the exam. EXCLUDES correct_option."""
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
    """Base Test Serializer (Safe for list views)"""
    class Meta:
        model = Test
        fields = ('id', 'olympiad', 'sub_olympiad', 'title')

    def validate(self, attrs):
        olympiad = attrs.get('olympiad')
        sub_olympiad = attrs.get('sub_olympiad')

        # Если указана олимпиада, но нет саб-олимпиады, проверяем, нет ли у олимпиады сабов
        if olympiad and not sub_olympiad:
            if olympiad.subs.exists():
                raise serializers.ValidationError({
                    "olympiad": "Эта олимпиада состоит из нескольких предметов. Создайте тест для конкретного предмета."
                })
        
        # Если указано и то, и другое (что странно для 1-к-1), или ничего
        if not olympiad and not sub_olympiad:
             raise serializers.ValidationError("Необходимо указать либо олимпиаду, либо предмет.")

        return attrs

class SubOlympiadSerializer(serializers.ModelSerializer):
    title = serializers.SerializerMethodField()
    test = TestSerializer(read_only=True)
    
    class Meta:
        model = SubOlympiad
        fields = ('id', 'olympiad', 'title', 'title_ru', 'title_uz', 'title_en', 
                  'start_datetime', 'duration_minutes', 'is_started', 'is_completed', 'test')
        extra_kwargs = {
            'olympiad': {'required': False}
        }

    def get_title(self, obj):
        request = self.context.get('request')
        lang = request.query_params.get('lang', 'uz') if request and hasattr(request, 'query_params') else 'uz'
        return obj.get_translated('title', lang)

class ExamResultSerializer(serializers.ModelSerializer):
    sub_olympiad_title = serializers.ReadOnlyField(source='sub_olympiad.title_ru')
    class Meta:
        model = ExamResult
        fields = ('id', 'olympiad', 'sub_olympiad', 'sub_olympiad_title', 'score', 'completed_at')

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
        # Если юзернейм не пришел, используем телефон (модель потом заменит его на participant_id)
        if not validated_data.get('username'):
            import uuid
            # Добавляем хвост, чтобы не было конфликта по уникальности ДО вызова save()
            validated_data['username'] = f"{validated_data.get('phone')}_{uuid.uuid4().hex[:8]}"
        return User.objects.create_user(**validated_data, role=User.Role.PARTICIPANT)

class LoginRequestSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()

class OlympiadSerializer(serializers.ModelSerializer):
    # Явно объявляем для Swagger и фронта
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
                  'is_active', 'is_started', 'is_completed', 'seats_remaining', 'is_registered', 'registered_count',
                  'grades', 'region_ids', 'test', 'subs',
                  'title_ru', 'title_uz', 'title_en', 'description_ru', 'description_uz', 'description_en')

    def get_registered_count(self, obj):
        # Считаем всех, кроме тех, у кого бронь явно истекла
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
                return 9999 # Значение для "без лимита"
            # Учитываем всех активных (paid, free, pending)
            reg_count = obj.registrations.exclude(payment_status='expired').count()
            return max(0, obj.max_participants - reg_count)
        except: return 0

    def get_is_registered(self, obj):
        request = self.context.get('request')
        try:
            if request and request.user.is_authenticated:
                # Считаем, что пользователь НЕ зарегистрирован, если его бронь истекла
                return obj.registrations.filter(user=request.user).exclude(payment_status='expired').exists()
        except: pass
        return False

    def create(self, validated_data):
        subs_data = validated_data.pop('subs', [])
        
        # Авто-расчет даты начала и длительности по предметам
        if subs_data:
            start_dates = [s.get('start_datetime') for s in subs_data if s.get('start_datetime')]
            if start_dates:
                validated_data['start_datetime'] = min(start_dates)
            validated_data['duration_minutes'] = sum(s.get('duration_minutes', 0) for s in subs_data)
            
        olympiad = Olympiad.objects.create(**validated_data)
        
        for sub_data in subs_data:
            SubOlympiad.objects.create(olympiad=olympiad, **sub_data)
            
        return olympiad

    def update(self, instance, validated_data):
        subs_data = validated_data.pop('subs', None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
            
        if subs_data is not None:
            # Обновляем предметы: удаляем старые и создаем новые (простейший способ для админки)
            instance.subs.all().delete()
            for sub_data in subs_data:
                SubOlympiad.objects.create(olympiad=instance, **sub_data)
            
            # Пересчитываем дату и длительность
            start_dates = [s.get('start_datetime') for s in subs_data if s.get('start_datetime')]
            if start_dates:
                instance.start_datetime = min(start_dates)
            instance.duration_minutes = sum(s.get('duration_minutes', 0) for s in subs_data)
        
        instance.save()
        return instance

