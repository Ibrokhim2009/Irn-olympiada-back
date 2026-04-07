from django.db import models
from django.shortcuts import get_object_or_404
from rest_framework import generics, status, permissions, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.utils import timezone
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from rest_framework import response
from payme import Payme
from .serializers import (
    RegisterSerializer, UserSerializer, LoginRequestSerializer,
    OlympiadSerializer, QuestionSerializer, RegistrationSerializer,
    TestSerializer, NotificationSerializer, RegionSerializer
)
from .models import User, Olympiad, Registration, ExamResult, Test, Question, Notification, Region
from .permissions import IsAdminUserOrReadOnly

class RegionViewSet(viewsets.ModelViewSet):
    queryset = Region.objects.all()
    serializer_class = RegionSerializer
    permission_classes = (IsAdminUserOrReadOnly,)

class TestViewSet(viewsets.ModelViewSet):
    queryset = Test.objects.all()
    serializer_class = TestSerializer
    permission_classes = (IsAdminUserOrReadOnly,)

class QuestionViewSet(viewsets.ModelViewSet):
    queryset = Question.objects.all()
    serializer_class = QuestionSerializer
    permission_classes = (IsAdminUserOrReadOnly,)






class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (permissions.AllowAny,)
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        
        # Генерируем токены для автоматического логина
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'user': UserSerializer(user).data,
            'access': str(refresh.access_token),
            'refresh': str(refresh)
        }, status=status.HTTP_201_CREATED)

class LoginView(APIView):
    permission_classes = (permissions.AllowAny,)
    
    @swagger_auto_schema(
        request_body=LoginRequestSerializer,
        responses={200: UserSerializer}
    )
    def post(self, request):
        serializer = LoginRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        username_input = serializer.validated_data.get('username')
        password = serializer.validated_data.get('password')
        
        # 1. Пытаемся стандартно (по email/username)
        # В Django authenticate проверяет поле USERNAME_FIELD (по умолчанию 'username')
        user = authenticate(username=username_input, password=password)
        
        # 2. Если не вышло (например, ввели почту, а в поле username другой логин), 
        # пытаемся найти по полю email
        if not user:
            try:
                found_user = User.objects.get(email=username_input)
                if found_user.check_password(password):
                    user = found_user
            except User.DoesNotExist:
                pass

        # 3. Пытаемся найти по participant_id
        if not user:
            try:
                found_user = User.objects.get(participant_id=username_input)
                if found_user.check_password(password):
                    user = found_user
            except User.DoesNotExist:
                pass

        if user:
            refresh = RefreshToken.for_user(user)
            return Response({
                'user': UserSerializer(user).data,
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            })
        return Response({'error': 'Неверный логин или пароль'}, status=status.HTTP_401_UNAUTHORIZED)

class UserProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    def get_object(self):
        return self.request.user


from rest_framework import filters
from django_filters.rest_framework import DjangoFilterBackend

from rest_framework.pagination import PageNumberPagination

class UserPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.filter(role=User.Role.PARTICIPANT).order_by('-date_joined')
    serializer_class = UserSerializer
    permission_classes = (permissions.IsAdminUser,)
    pagination_class = UserPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['region', 'grade', 'registrations__olympiad']
    search_fields = ['username', 'first_name', 'last_name', 'middle_name', 'phone', 'participant_id']
    ordering_fields = ['date_joined', 'first_name', 'last_name']

class RegistrationViewSet(viewsets.ReadOnlyModelViewSet):
    """История регистраций (оплат) текущего пользователя"""
    serializer_class = RegistrationSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        from .models import Registration
        from django.utils import timezone
        
        # Автоматически помечаем просроченные регистрации ТЕКУЩЕГО пользователя как EXPIRED
        Registration.objects.filter(
            user=self.request.user,
            payment_status=Registration.PaymentStatus.PENDING,
            payment_deadline__lt=timezone.now()
        ).update(payment_status=Registration.PaymentStatus.EXPIRED)
        
        return Registration.objects.filter(user=self.request.user).order_by('-registered_at')


from .utils_payme import get_payme_link

class GetPaymeLinkView(APIView):
    permission_classes = (permissions.IsAuthenticated,)
    
    def get(self, request, registration_id):
        registration = generics.get_object_or_404(Registration, id=registration_id, user=request.user)
        if registration.payment_status in ['paid', 'free']:
            return Response({'error': 'Already paid'}, status=status.HTTP_400_BAD_REQUEST)
        
        link = get_payme_link(registration.id, registration.price)
        return Response({'link': link})


from payme.views import PaymeWebHookAPIView

class PaymeCallbackView(PaymeWebHookAPIView):
    permission_classes = (permissions.AllowAny,)
    
    def handle_successfully_payment(self, params, result, *args, **kwargs):
        from .models import Registration
        reg_id = params.get('account', {}).get('registration_id') or result.get('account', {}).get('id')
        
        if not reg_id:
            from payme.models import PaymeTransactions
            try:
                trans = PaymeTransactions.objects.get(transaction_id=params.get('id'))
                reg_id = trans.account_id
            except Exception:
                pass

        try:
            registration = Registration.objects.get(id=reg_id)
            registration.payment_status = Registration.PaymentStatus.PAID
            registration.save()
            print(f"Registration {reg_id} marked as PAID via payme-pkg")
        except Registration.DoesNotExist:
            print(f"Registration {reg_id} not found during payme callback")

from rest_framework.decorators import action

class OlympiadViewSet(viewsets.ModelViewSet):
    """CRUD олимпиад (чтение для всех, правка для админов)"""
    queryset = Olympiad.objects.all()
    serializer_class = OlympiadSerializer
    permission_classes = (IsAdminUserOrReadOnly,)

    def get_queryset(self):
        if self.request.user.is_authenticated and self.request.user.role in ['admin', 'superadmin']:
            return Olympiad.objects.all()
        return Olympiad.objects.filter(is_active=True)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def start_now(self, request, pk=None):
        olympiad = self.get_object()
        olympiad.is_started = True
        olympiad.is_completed = False
        olympiad.save()
        
        # Автоматическое уведомление всем зарегистрированным
        from .models import Notification
        regs = olympiad.registrations.filter(payment_status__in=['paid', 'free'])
        for reg in regs:
            Notification.objects.create(
                user=reg.user,
                title_ru=f"Олимпиада {olympiad.title_ru} началась!",
                title_uz=f"Olimpiada {olympiad.title_uz} boshlandi!",
                title_en=f"Olympiad {olympiad.title_en} started!",
                message_ru="Вы можете приступить к выполнению заданий в личном кабинете.",
                message_uz="Shaxsiy kabinetda topshiriqlarni bajarishni boshlashingiz mumkin.",
                message_en="You can start taking the test in your dashboard.",
                type='success'
            )
        
        return Response({'status': 'Olympiad started'})

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def finish_now(self, request, pk=None):
        olympiad = self.get_object()
        olympiad.is_completed = True
        olympiad.is_started = False
        olympiad.save()
        return Response({'status': 'Olympiad finished'})

class RegisterForOlympiadView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @swagger_auto_schema(
        responses={201: RegistrationSerializer, 400: 'Ошибка (нет мест и т.д.)'}
    )
    def post(self, request, pk):
        olympiad = generics.get_object_or_404(Olympiad, pk=pk)
        
        # 0. Проверка дат
        now = timezone.now()
        if now >= olympiad.start_datetime:
            return Response({"error": "Регистрация закрыта: олимпиада уже началась"}, status=400)
            
        if olympiad.registration_end_date and now >= olympiad.registration_end_date:
            return Response({"error": "Регистрация закрыта: время вышло"}, status=400)
        
        # Прежде чем считать места, сбросим просроченные брони У ВСЕХ участников этой олимпиады
        Registration.objects.filter(
            olympiad=olympiad,
            payment_status=Registration.PaymentStatus.PENDING,
            payment_deadline__lt=timezone.now()
        ).update(payment_status=Registration.PaymentStatus.EXPIRED)

        # Считаем PAID + FREE + АКТИВНЫЕ PENDING
        reg_count = olympiad.registrations.filter(
            payment_status__in=['paid', 'free', 'pending']
        ).count()

        if olympiad.max_participants > 0 and reg_count >= olympiad.max_participants:
            # Но если у текущего пользователя уже есть место (даже PENDING), мы его не блокируем
            if not Registration.objects.filter(user=request.user, olympiad=olympiad, payment_status__in=['paid', 'free', 'pending']).exists():
                return Response({'error': 'Мест больше нет'}, status=status.HTTP_400_BAD_REQUEST)
            
        if olympiad.is_free or olympiad.price == 0:
            initial_status = Registration.PaymentStatus.FREE
        else:
            initial_status = Registration.PaymentStatus.PENDING

        registration, created = Registration.objects.get_or_create(
            user=request.user,
            olympiad=olympiad,
            defaults={
                'payment_status': initial_status,
                'price': olympiad.price,
                'teacher_name': request.user.teacher_name,
                'teacher_phone': request.user.teacher_phone,
            }
        )
        # Если регистрация уже была, но она EXPIRED, мы позволяем перевыпустить её
        if not created and registration.payment_status == Registration.PaymentStatus.EXPIRED:
             registration.payment_status = initial_status
             registration.registered_at = timezone.now() # Обновляем время регистрации
             registration.payment_deadline = None # Будет пересчитано в save()
             registration.save()
             created = True
             
        if not created:
            return Response({'error': 'Вы уже зарегистрированы'}, status=status.HTTP_400_BAD_REQUEST)

        # Logic for ACHIEVEMENTS
        from .models import UserAchievement, Notification
        from datetime import timedelta
        
        # 1. Early Bird (7 days before)
        if olympiad.start_datetime and (olympiad.start_datetime - timezone.now() > timedelta(days=7)):
            UserAchievement.objects.get_or_create(
                user=request.user, type='early_bird',
                defaults={
                    'title_ru': 'Ранняя пташка',
                    'title_uz': 'Erta tong pahlavoni',
                    'title_en': 'Early Bird',
                    'icon': 'Bird'
                }
            )
        
        # 2. Regular (3+ registrations)
        if Registration.objects.filter(user=request.user).count() >= 3:
            UserAchievement.objects.get_or_create(
                user=request.user, type='regular',
                defaults={
                    'title_ru': 'Постоянный участник',
                    'title_uz': 'Doimiy ishtirokchi',
                    'title_en': 'Regular Participant',
                    'icon': 'Trophy'
                }
            )

        response_data = RegistrationSerializer(registration).data
        if initial_status == Registration.PaymentStatus.PENDING:
            response_data['payment_link'] = get_payme_link(registration.id, registration.price)

        return Response(response_data, status=status.HTTP_201_CREATED)

class ExamView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @swagger_auto_schema(responses={200: QuestionSerializer(many=True)})
    def get(self, request, olympiad_id):
        registration = generics.get_object_or_404(Registration, user=request.user, olympiad_id=olympiad_id)
        if registration.payment_status not in ['paid', 'free']:
             return Response({'error': 'Оплата не подтверждена'}, status=status.HTTP_403_FORBIDDEN)
        
        test = generics.get_object_or_404(Test, olympiad_id=olympiad_id)
        serializer = QuestionSerializer(test.questions.all(), many=True, context={'request': request})
        return Response(serializer.data)

class SubmitResultView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'score': openapi.Schema(type=openapi.TYPE_INTEGER),
                'answers': openapi.Schema(type=openapi.TYPE_OBJECT)
            }
        )
    )
    def post(self, request, olympiad_id):
        olympiad = generics.get_object_or_404(Olympiad, pk=olympiad_id)
        score = request.data.get('score')
        answers = request.data.get('answers')
        
        ExamResult.objects.get_or_create(
            user=request.user,
            olympiad=olympiad,
            defaults={'score': score, 'answers_json': answers}
        )

        # ACHIEVEMENT: Top Scorer (90+)
        from .models import UserAchievement
        if score >= 90:
            UserAchievement.objects.get_or_create(
                user=request.user, type='top_scorer',
                defaults={
                    'title_ru': 'Золотая медаль (Топ результат)',
                    'title_uz': 'Oltin medal (Top natija)',
                    'title_en': 'Gold Medal (Top Result)',
                    'icon': 'Star'
                }
            )
        elif score >= 70:
            UserAchievement.objects.get_or_create(
                user=request.user, type='silver',
                defaults={
                    'title_ru': 'Серебряная медаль',
                    'title_uz': 'Kumush medal',
                    'title_en': 'Silver Medal',
                    'icon': 'Award'
                }
            )

        # ACHIEVEMENT: Night Owl (midnight to 6am)
        from django.utils import timezone
        now_hour = timezone.now().hour
        if 0 <= now_hour < 6:
             UserAchievement.objects.get_or_create(
                user=request.user, type='night_owl',
                defaults={
                    'title_ru': 'Ночная сова',
                    'title_uz': 'Tun qushi',
                    'title_en': 'Night Owl',
                    'icon': 'Moon'
                }
            )

        return Response({'success': True, 'score': score})

class ClickCallbackView(APIView):
    permission_classes = (permissions.AllowAny,)
    def post(self, request):
        return Response({"result": "not_implemented_yet"})

class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)

    @swagger_auto_schema(responses={200: '{"success": true}'})
    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.save()
        return Response({'success': True})

    @action(detail=False, methods=['post'])
    def mark_all_as_read(self, request):
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({'success': True})

class SeedNotificationsView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request):
        user = request.user
        # Удаляем старые, если есть (для теста)
        # Notification.objects.filter(user=user).delete()
        
        seeds = [
            {
                'type': Notification.Type.INFO,
                'title_uz': 'Xush kelibsiz!', 'title_ru': 'Добро пожаловать!', 'title_en': 'Welcome!',
                'message_uz': 'IRN Olympiads platformasiga xush kelibsiz. Bu yerda siz fanlar bo\'yicha bilimlaringizni sinashingiz mumkin.',
                'message_ru': 'Добро пожаловать на платформу IRN Olympiads. Здесь вы можете проверить свои знания по различным предметам.',
                'message_en': 'Welcome to the IRN Olympiads platform. Here you can test your knowledge in various subjects.'
            },
            {
                'type': Notification.Type.SUCCESS,
                'title_uz': 'Profil tasdiqlandi', 'title_ru': 'Профиль подтвержден', 'title_en': 'Profile Verified',
                'message_uz': 'Sizning bir martalik kodingiz muvaffaqiyatli qabul qilindi. Endi barcha imkoniyatlardan foydalanishingiz mumkin.',
                'message_ru': 'Ваш одноразовый код успешно принят. Теперь вы можете использовать все возможности платформы.',
                'message_en': 'Your one-time code has been successfully accepted. You can now use all the features of the platform.'
            },
            {
                'type': Notification.Type.WARNING,
                'title_uz': 'Muhim eslatma', 'title_ru': 'Важное напоминание', 'title_en': 'Important Reminder',
                'message_uz': 'Matematika olimpiadasi ertaga soat 10:00 da boshlanadi. Kechikmang!',
                'message_ru': 'Олимпиада по математике начнется завтра в 10:00. Не опаздывайте!',
                'message_en': 'The Math Olympiad starts tomorrow at 10:00 AM. Don\'t be late!'
            },
            {
                'type': Notification.Type.PAYMENT,
                'title_uz': 'To\'lov kutilmoqda', 'title_ru': 'Ожидается оплата', 'title_en': 'Payment Pending',
                'message_uz': 'Siz Ingliz tili olimpiadasiga yozildingiz. Joyingizni saqlab qolish uchun 15 daqiqa ichida to\'lov qiling.',
                'message_ru': 'Вы записались на олимпиаду по английскому языку. Оплатите в течение 15 минут, чтобы сохранить место.',
                'message_en': 'You have registered for the English Olympiad. Pay within 15 minutes to secure your spot.'
            }
        ]
        
        created_count = 0
        for data in seeds:
            Notification.objects.create(user=user, **data)
            created_count += 1
            
        return Response({'success': True, 'created': created_count})

class AdminStatsView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        if request.user.role != User.Role.ADMIN and not request.user.is_superuser:
             return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
             
        total_users = User.objects.filter(role=User.Role.PARTICIPANT).count()
        total_olympiads = Olympiad.objects.count()
        online_oly = Olympiad.objects.filter(olympiad_type='online').count()
        offline_oly = Olympiad.objects.filter(olympiad_type='offline').count()
        
        # Платежи и доход
        paid_registrations = Registration.objects.filter(payment_status='paid')
        total_paid = paid_registrations.count()
        total_revenue = sum(r.price for r in paid_registrations)
        
        # Статистика по регионам (теперь через FK)
        region_stats = User.objects.filter(role=User.Role.PARTICIPANT)\
            .values('region__name_ru')\
            .annotate(region=models.F('region__name_ru'), count=models.Count('id'))\
            .values('region', 'count')
        
        # Статистика по классам
        grade_stats = User.objects.filter(role=User.Role.PARTICIPANT).values('grade').annotate(count=models.Count('id'))
        
        # Регистрации по типам
        online_registrations = Registration.objects.filter(olympiad__olympiad_type='online').count()
        offline_registrations = Registration.objects.filter(olympiad__olympiad_type='offline').count()

        # Наполняемость
        oly_fill = []
        for oly in Olympiad.objects.all():
            reg_count = oly.registrations.filter(payment_status__in=['paid', 'free']).count()
            oly_fill.append({
                'id': oly.id,
                'title_uz': oly.title_uz,
                'title_ru': oly.title_ru,
                'title_en': oly.title_en,
                'registered': reg_count,
                'max': oly.max_participants,
                'fill': round((reg_count / oly.max_participants * 100), 1) if oly.max_participants > 0 else 0,
                'type': oly.olympiad_type
            })

        # Динамика (последние 6 месяцев)
        from django.db.models.functions import TruncMonth
        from django.utils import timezone
        
        six_months_ago = timezone.now() - timezone.timedelta(days=180)
        trend = User.objects.filter(role=User.Role.PARTICIPANT, date_joined__gte=six_months_ago)\
            .annotate(month=TruncMonth('date_joined'))\
            .values('month')\
            .annotate(registrations=models.Count('id'))\
            .order_by('month')
            
        trend_data = []
        for t in trend:
            trend_data.append({
                'month': t['month'].strftime('%b'),
                'registrations': t['registrations']
            })

        return Response({
            'total_users': total_users,
            'total_olympiads': total_olympiads,
            'online_oly': online_oly,
            'offline_oly': offline_oly,
            'total_paid': total_paid,
            'total_revenue': total_revenue,
            'region_stats': list(region_stats),
            'grade_stats': list(grade_stats),
            'online_registrations': online_registrations,
            'offline_registrations': offline_registrations,
            'oly_fill': oly_fill,
            'trend_data': trend_data
        })

class ResultAnalysisView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, olympiad_id):
        olympiad = get_object_or_404(Olympiad, id=olympiad_id)
        
        # 1. Get user's result
        try:
            my_result = ExamResult.objects.get(user=request.user, olympiad=olympiad)
        except ExamResult.DoesNotExist:
            return Response({'error': 'Result not found'}, status=404)

        # 2. Calculate Rank
        rank = ExamResult.objects.filter(olympiad=olympiad, score__gt=my_result.score).count() + 1
        total_participants = ExamResult.objects.filter(olympiad=olympiad).count()

        # 3. Prepare detailed analysis
        try:
            test = olympiad.test
        except:
            return Response({'error': 'Test not found'}, status=404)
            
        questions_data = []
        user_answers = my_result.answers_json or {}
        
        correct_count = 0
        wrong_count = 0
        no_answer_count = 0

        # Translation helper
        lang = request.query_params.get('lang', 'uz')

        for q in test.questions.all().order_by('id'):
            user_ans = user_answers.get(str(q.id))
            is_correct = user_ans == q.correct_option
            
            if not user_ans: no_answer_count += 1
            elif is_correct: correct_count += 1
            else: wrong_count += 1

            questions_data.append({
                'id': q.id,
                'text': q.get_translated('text', lang),
                'options': q.options,
                'user_answer': user_ans,
                'correct_answer': q.correct_option,
                'is_correct': is_correct,
                'image': q.image.url if q.image else None
            })
            
        # Top 10 leaderboard
        leaderboard = ExamResult.objects.filter(olympiad=olympiad).order_by('-score', 'completed_at')[:10]
        leaderboard_data = []
        for i, res in enumerate(leaderboard):
            leaderboard_data.append({
                'rank': i + 1,
                'username': res.user.username,
                'full_name': f"{res.user.last_name} {res.user.first_name}",
                'score': res.score,
                'is_me': res.user == request.user
            })

        return Response({
            'olympiad_title': olympiad.get_translated('title', lang),
            'score': my_result.score,
            'completed_at': my_result.completed_at,
            'rank': rank,
            'total_participants': total_participants,
            'stats': {
                'correct': correct_count,
                'wrong': wrong_count,
                'no_answer': no_answer_count,
                'total': test.questions.count()
            },
            'questions': questions_data,
            'leaderboard': leaderboard_data
        })
class SendNotificationView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request):
        if request.user.role != User.Role.ADMIN and not request.user.is_superuser:
            return Response({'error': 'Forbidden'}, status=403)

        target = request.data.get('target', 'all')
        user_ids = request.data.get('user_ids', [])
        olympiad_id = request.data.get('olympiad_id')
        
        data = {
            'type': request.data.get('type', 'info'),
            'title_ru': request.data.get('title_ru', ''),
            'title_uz': request.data.get('title_uz', ''),
            'title_en': request.data.get('title_en', ''),
            'message_ru': request.data.get('message_ru', ''),
            'message_uz': request.data.get('message_uz', ''),
            'message_en': request.data.get('message_en', ''),
        }

        participants = User.objects.filter(role=User.Role.PARTICIPANT)
        
        if target == 'all':
            users_to_notify = participants
        elif target == 'specific' or target == 'group':
            users_to_notify = participants.filter(id__in=user_ids)
        elif target == 'olympiad_participants':
            users_to_notify = participants.filter(registrations__olympiad_id=olympiad_id)
        elif target == 'olympiad_results':
            users_to_notify = participants.filter(exam_results__olympiad_id=olympiad_id)
        else:
            users_to_notify = User.objects.none()

        # Bulk create notifications
        notifs_to_create = [
            Notification(user=u, **data) for u in users_to_notify.distinct()
        ]
        Notification.objects.bulk_create(notifs_to_create)

        return Response({'success': True, 'count': len(notifs_to_create)})
