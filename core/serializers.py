from rest_framework import serializers
from .models import User, Olympiad, Question, Test, Registration
class RegistrationSerializer(serializers.ModelSerializer):
    olympiad_title = serializers.ReadOnlyField(source='olympiad.title_ru')
    olympiad_type = serializers.ReadOnlyField(source='olympiad.olympiad_type')
    price = serializers.ReadOnlyField(source='olympiad.price')
    status_label = serializers.SerializerMethodField()

    class Meta:
        model = Registration
        fields = ('id', 'olympiad', 'olympiad_title', 'olympiad_type', 'price', 
                  'registered_at', 'payment_status', 'status_label', 'transaction_id')

    def get_status_label(self, obj):
        return obj.get_payment_status_display()

class QuestionSerializer(serializers.ModelSerializer):
    text = serializers.CharField(read_only=True)

    class Meta:
        model = Question
        fields = ('id', 'test', 'text', 'image', 'options', 'correct_option', 
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
        fields = ('id', 'olympiad', 'title', 'questions')

class UserSerializer(serializers.ModelSerializer):
    registrations = RegistrationSerializer(many=True, read_only=True)
    class Meta:
        model = User
        fields = ('id', 'username', 'first_name', 'last_name', 'middle_name', 
                  'phone', 'region', 'school', 'grade', 'role', 'participant_id', 'registrations')

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    participant_id = serializers.CharField(read_only=True)
    class Meta:
        model = User
        fields = ('username', 'password', 'first_name', 'last_name', 'middle_name', 
                  'phone', 'birth_date', 'region', 'school', 'grade', 'participant_id')
    
    def create(self, validated_data):
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
    class Meta:
        model = Olympiad
        fields = ('id', 'title', 'description', 'olympiad_type', 'price', 'is_free',
                  'start_datetime', 'duration_minutes', 'max_participants', 
                  'is_active', 'seats_remaining', 'is_registered', 'registered_count',
                  'grades', 'region_ids', 'test',
                  'title_ru', 'title_uz', 'title_en', 'description_ru', 'description_uz', 'description_en')

    def get_registered_count(self, obj):
        return obj.registrations.all().count()

    def to_representation(self, instance):
        request = self.context.get('request')
        lang = request.query_params.get('lang', 'uz') if request and hasattr(request, 'query_params') else 'uz'
        
        result = super().to_representation(instance)
        result['title'] = instance.get_translated('title', lang)
        result['description'] = instance.get_translated('description', lang)
        return result

    def get_seats_remaining(self, obj):
        try:
            reg_count = obj.registrations.filter(payment_status__in=['paid', 'free']).count()
            return max(0, obj.max_participants - reg_count)
        except: return 0

    def get_is_registered(self, obj):
        request = self.context.get('request')
        try:
            if request and request.user.is_authenticated:
                return obj.registrations.filter(user=request.user).exists()
        except: pass
        return False

