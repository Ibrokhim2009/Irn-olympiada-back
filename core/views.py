from django.db import models
from django.shortcuts import get_object_or_404
from rest_framework import generics, status, permissions, viewsets
from rest_framework.decorators import action
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
    OlympiadSerializer, SubOlympiadSerializer, QuestionSerializer, QuestionExamSerializer, RegistrationSerializer,
    TestSerializer, NotificationSerializer, RegionSerializer
)
from .models import User, Olympiad, SubOlympiad, Registration, ExamResult, Test, Question, Notification, Region
from .permissions import IsAdminUserOrReadOnly
from .utils_payme import get_payme_link
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


class RegionViewSet(viewsets.ModelViewSet):
    queryset = Region.objects.all()
    serializer_class = RegionSerializer
    permission_classes = (IsAdminUserOrReadOnly,)


class TestViewSet(viewsets.ModelViewSet):
    queryset = Test.objects.all()
    serializer_class = TestSerializer
    permission_classes = (IsAdminUserOrReadOnly,)

    def create(self, request, *args, **kwargs):
        olympiad_id = request.data.get('olympiad')
        sub_olympiad_id = request.data.get('sub_olympiad')
        
        # Пытаемся найти существующий тест или создать новый
        test, created = Test.objects.get_or_create(
            olympiad_id=olympiad_id,
            sub_olympiad_id=sub_olympiad_id,
            defaults={
                'title': request.data.get('title', f"Test for {sub_olympiad_id or olympiad_id}")
            }
        )
        
        serializer = self.get_serializer(test)
        status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(serializer.data, status=status_code)


class SubOlympiadViewSet(viewsets.ModelViewSet):
    queryset = SubOlympiad.objects.all()
    serializer_class = SubOlympiadSerializer
    permission_classes = (IsAdminUserOrReadOnly,)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def start_now(self, request, pk=None):
        sub = self.get_object()
        sub.is_started = True
        sub.is_completed = False
        sub.save()
        
        # Уведомляем тех, кто зарегистрирован на основную олимпиаду
        olympiad = sub.olympiad
        regs = olympiad.registrations.filter(payment_status__in=['paid', 'free'])
        
        notifs_to_create = []
        for reg in regs:
            notifs_to_create.append(Notification(
                user=reg.user,
                title_ru=f"Предмет {sub.title_ru} начался!",
                title_uz=f"Fan {sub.title_uz} boshlandi!",
                title_en=f"Subject {sub.title_en} started!",
                message_ru=f"Вы можете приступить к выполнению заданий по предмету {sub.title_ru} в личном кабинете.",
                message_uz=f"Shaxsiy kabinetda {sub.title_uz} fani bo'yicha topshiriqlarni bajarishni boshlashingiz mumkin.",
                message_en=f"You can start taking the test for {sub.title_en} in your dashboard.",
                type='success'
            ))
        
        created_notifs = Notification.objects.bulk_create(notifs_to_create)
        
        # Мгновенная рассылка через вебсокеты
        channel_layer = get_channel_layer()
        for notif in created_notifs:
            async_to_sync(channel_layer.group_send)(
                f'user_{notif.user.id}',
                {
                    'type': 'notification_send',
                    'data': {
                        'id': notif.id,
                        'title_ru': notif.title_ru,
                        'title_uz': notif.title_uz,
                        'message_ru': notif.message_ru,
                        'message_uz': notif.message_uz,
                        'type': notif.type,
                        'created_at': timezone.now().isoformat()
                    }
                }
            )
            
        return Response({'status': 'Sub-Olympiad started'})

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def finish_now(self, request, pk=None):
        sub = self.get_object()
        sub.is_completed = True
        sub.is_started = False
        sub.save()
        return Response({'status': 'Sub-Olympiad finished'})


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
        refresh = RefreshToken.for_user(user)
        return Response({
            'user': UserSerializer(user).data,
            'access': str(refresh.access_token),
            'refresh': str(refresh)
        }, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = (permissions.AllowAny,)

    @swagger_auto_schema(request_body=LoginRequestSerializer, responses={200: UserSerializer})
    def post(self, request):
        serializer = LoginRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        login_input = serializer.validated_data.get('username')
        password = serializer.validated_data.get('password')

        # 1. Сначала пробуем аутентифицировать как обычно (по username/participant_id)
        user = authenticate(username=login_input, password=password)

        if not user:
            # 2. Если не вышло, проверяем, не телефон ли это
            users_with_phone = User.objects.filter(phone=login_input)
            
            valid_users = []
            for u in users_with_phone:
                if u.check_password(password):
                    valid_users.append(u)
            
            if len(valid_users) > 1:
                # Найдено несколько аккаунтов на этот номер
                accounts_data = [
                    {
                        'participant_id': u.participant_id,
                        'full_name': f"{u.last_name} {u.first_name} {u.middle_name or ''}".strip(),
                        'grade': u.grade
                    } for u in valid_users
                ]
                return Response({
                    'multiple_accounts': True,
                    'accounts': accounts_data,
                    'message': 'Найдено несколько аккаунтов. Пожалуйста, выберите нужный.'
                }, status=status.HTTP_200_OK)
            
            elif len(valid_users) == 1:
                user = valid_users[0]
            
            # 3. Пробуем по email (на всякий случай, как было раньше)
            if not user:
                try:
                    found_user = User.objects.get(email=login_input)
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
    serializer_class = RegistrationSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        Registration.objects.filter(
            user=self.request.user,
            payment_status=Registration.PaymentStatus.PENDING,
            payment_deadline__lt=timezone.now()
        ).update(payment_status=Registration.PaymentStatus.EXPIRED)
        return Registration.objects.filter(user=self.request.user).order_by('-registered_at')


class GetPaymeLinkView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, registration_id):
        registration = generics.get_object_or_404(Registration, id=registration_id, user=request.user)

        if registration.payment_status in ['paid', 'free']:
            return Response({'error': 'Already paid'}, status=status.HTTP_400_BAD_REQUEST)

        # ✅ Always use olympiad.price as source of truth
        amount = registration.olympiad.price
        if not amount or amount <= 0:
            return Response({'error': 'Invalid payment amount'}, status=status.HTTP_400_BAD_REQUEST)

        # ✅ Sync registration.price if it drifted
        if registration.price != amount:
            registration.price = amount
            registration.save(update_fields=['price'])

        link = get_payme_link(registration.id, amount)
        return Response({'link': link})


from payme.views import PaymeWebHookAPIView


class PaymeCallbackView(PaymeWebHookAPIView):
    permission_classes = (permissions.AllowAny,)

    def handle_successfully_payment(self, params, result, *args, **kwargs):
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
            print(f"✅ Registration {reg_id} marked as PAID")
        except Registration.DoesNotExist:
            print(f"❌ Registration {reg_id} not found during payme callback")


class OlympiadViewSet(viewsets.ModelViewSet):
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
        
        # Уведомляем тех, кто зарегистрирован
        regs = olympiad.registrations.filter(payment_status__in=['paid', 'free'])
        
        notifs_to_create = []
        for reg in regs:
            notifs_to_create.append(Notification(
                user=reg.user,
                title_ru=f"Олимпиада {olympiad.title_ru} началась!",
                title_uz=f"Olimpiada {olympiad.title_uz} boshlandi!",
                title_en=f"Olympiad {olympiad.title_en} started!",
                message_ru=f"Олимпиада началась. Вы можете приступить к выполнению предметов в личном кабинете.",
                message_uz=f"Olimpiada boshlandi. Shaxsiy kabinetda fanlarni bajarishni boshlashingiz mumkin.",
                message_en=f"The olympiad has started. You can now start the test in your dashboard.",
                type='success'
            ))
            
        created_notifs = Notification.objects.bulk_create(notifs_to_create)
        
        # Мгновенная рассылка через вебсокеты
        channel_layer = get_channel_layer()
        for notif in created_notifs:
            async_to_sync(channel_layer.group_send)(
                f'user_{notif.user.id}',
                {
                    'type': 'notification_send',
                    'data': {
                        'id': notif.id,
                        'title_ru': notif.title_ru,
                        'title_uz': notif.title_uz,
                        'message_ru': notif.message_ru,
                        'message_uz': notif.message_uz,
                        'type': notif.type,
                        'created_at': timezone.now().isoformat()
                    }
                }
            )
            
        return Response({'status': 'Olympiad started'})

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def finish_now(self, request, pk=None):
        olympiad = self.get_object()
        olympiad.is_started = False
        olympiad.is_completed = True
        olympiad.save()
        return Response({'status': 'Olympiad finished'})


class RegisterForOlympiadView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @swagger_auto_schema(responses={201: RegistrationSerializer, 400: 'Ошибка'})
    def post(self, request, pk):
        olympiad = generics.get_object_or_404(Olympiad, pk=pk)

        now = timezone.now()
        if now >= olympiad.start_datetime:
            return Response({"error": "Регистрация закрыта: олимпиада уже началась"}, status=400)

        if olympiad.registration_end_date and now >= olympiad.registration_end_date:
            return Response({"error": "Регистрация закрыта: время вышло"}, status=400)

        Registration.objects.filter(
            olympiad=olympiad,
            payment_status=Registration.PaymentStatus.PENDING,
            payment_deadline__lt=timezone.now()
        ).update(payment_status=Registration.PaymentStatus.EXPIRED)

        reg_count = olympiad.registrations.filter(
            payment_status__in=['paid', 'free', 'pending']
        ).count()

        if olympiad.max_participants > 0 and reg_count >= olympiad.max_participants:
            if not Registration.objects.filter(
                user=request.user, olympiad=olympiad,
                payment_status__in=['paid', 'free', 'pending']
            ).exists():
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
                'price': olympiad.price,  # ✅ stored in UZS (sum)
                'teacher_name': request.user.teacher_name,
                'teacher_phone': request.user.teacher_phone,
            }
        )

        if not created and registration.payment_status == Registration.PaymentStatus.EXPIRED:
            registration.payment_status = initial_status
            registration.registered_at = timezone.now()
            registration.payment_deadline = None
            registration.save()
            created = True

        if not created:
            return Response({'error': 'Вы уже зарегистрированы'}, status=status.HTTP_400_BAD_REQUEST)

        from .models import UserAchievement
        from datetime import timedelta

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

        # ✅ Only generate payment link if price is valid
        if initial_status == Registration.PaymentStatus.PENDING:
            if registration.price and registration.price > 0:
                try:
                    response_data['payment_link'] = get_payme_link(registration.id, registration.price)
                except Exception as e:
                    response_data['payment_link'] = None
                    response_data['payment_error'] = str(e)
            else:
                response_data['payment_link'] = None
                response_data['payment_error'] = 'Olympiad price is not set correctly'

        return Response(response_data, status=status.HTTP_201_CREATED)


class ExamView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @swagger_auto_schema(responses={200: QuestionSerializer(many=True)})
    def get(self, request, sub_olympiad_id):
        sub = generics.get_object_or_404(SubOlympiad, pk=sub_olympiad_id)
        registration = generics.get_object_or_404(Registration, user=request.user, olympiad=sub.olympiad)
        
        if registration.payment_status not in ['paid', 'free']:
            return Response({'error': 'Оплата не подтверждена'}, status=status.HTTP_403_FORBIDDEN)
        
        # ✅ Check if already completed
        existing_result = ExamResult.objects.filter(user=request.user, sub_olympiad=sub).first()
        if existing_result and existing_result.completed_at:
             return Response({'error': 'Вы уже завершили этот тест'}, status=status.HTTP_403_FORBIDDEN)

        # ✅ Record attempt start time if it doesn't exist
        if not existing_result:
            existing_result = ExamResult.objects.create(
                user=request.user,
                olympiad=sub.olympiad,
                sub_olympiad=sub,
                start_time=timezone.now()
            )

        try:
            test = sub.test
        except Test.DoesNotExist:
            return Response({'error': 'Тест не найден для этого предмета'}, status=404)
            
        serializer = QuestionExamSerializer(test.questions.all(), many=True, context={'request': request})
        
        return Response({
            'questions': serializer.data,
            'start_time': existing_result.start_time,
            'server_time': timezone.now(),
            'duration_minutes': sub.duration_minutes
        })


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
    def post(self, request, sub_olympiad_id):
        sub = generics.get_object_or_404(SubOlympiad, pk=sub_olympiad_id)
        answers = request.data.get('answers', {})
        tab_switches = request.data.get('tab_switches', 0)

        # ✅ Find the ongoing result/attempt
        result = generics.get_object_or_404(ExamResult, user=request.user, sub_olympiad=sub)
        
        if result.completed_at:
            return Response({'error': 'Test already submitted'}, status=400)

        # ✅ Backend Grading
        try:
            test = sub.test
        except Test.DoesNotExist:
            return Response({'error': 'Test not found'}, status=404)

        questions = test.questions.all()
        if not questions.exists():
             return Response({'error': 'Test has no questions'}, status=400)

        correct_count = 0
        for q in questions:
            student_answer = answers.get(str(q.id))
            if student_answer == q.correct_option:
                correct_count += 1
        
        score = round((correct_count / questions.count()) * 100) if questions.count() > 0 else 0

        # ✅ Update existing result
        result.score = score
        result.answers_json = answers
        result.tab_switches = tab_switches
        result.completed_at = timezone.now()
        result.save()

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
        seeds = [
            {
                'type': Notification.Type.INFO,
                'title_uz': 'Xush kelibsiz!', 'title_ru': 'Добро пожаловать!', 'title_en': 'Welcome!',
                'message_uz': 'IRN Olympiads platformasiga xush kelibsiz.',
                'message_ru': 'Добро пожаловать на платформу IRN Olympiads.',
                'message_en': 'Welcome to the IRN Olympiads platform.'
            },
            {
                'type': Notification.Type.SUCCESS,
                'title_uz': 'Profil tasdiqlandi', 'title_ru': 'Профиль подтвержден', 'title_en': 'Profile Verified',
                'message_uz': 'Sizning bir martalik kodingiz muvaffaqiyatli qabul qilindi.',
                'message_ru': 'Ваш одноразовый код успешно принят.',
                'message_en': 'Your one-time code has been successfully accepted.'
            },
            {
                'type': Notification.Type.WARNING,
                'title_uz': 'Muhim eslatma', 'title_ru': 'Важное напоминание', 'title_en': 'Important Reminder',
                'message_uz': 'Matematika olimpiadasi ertaga soat 10:00 da boshlanadi.',
                'message_ru': 'Олимпиада по математике начнется завтра в 10:00.',
                'message_en': 'The Math Olympiad starts tomorrow at 10:00 AM.'
            },
            {
                'type': Notification.Type.PAYMENT,
                'title_uz': "To'lov kutilmoqda", 'title_ru': 'Ожидается оплата', 'title_en': 'Payment Pending',
                'message_uz': "Joyingizni saqlab qolish uchun 15 daqiqa ichida to'lov qiling.",
                'message_ru': 'Оплатите в течение 15 минут, чтобы сохранить место.',
                'message_en': 'Pay within 15 minutes to secure your spot.'
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

        paid_registrations = Registration.objects.filter(payment_status='paid')
        total_paid = paid_registrations.count()
        total_revenue = sum(r.price for r in paid_registrations)

        region_stats = User.objects.filter(role=User.Role.PARTICIPANT) \
            .values('region__name_ru') \
            .annotate(region=models.F('region__name_ru'), count=models.Count('id')) \
            .values('region', 'count')

        grade_stats = User.objects.filter(role=User.Role.PARTICIPANT).values('grade').annotate(
            count=models.Count('id'))

        online_registrations = Registration.objects.filter(olympiad__olympiad_type='online').count()
        offline_registrations = Registration.objects.filter(olympiad__olympiad_type='offline').count()

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

        from django.db.models.functions import TruncMonth
        six_months_ago = timezone.now() - timezone.timedelta(days=180)
        trend = User.objects.filter(role=User.Role.PARTICIPANT, date_joined__gte=six_months_ago) \
            .annotate(month=TruncMonth('date_joined')) \
            .values('month') \
            .annotate(registrations=models.Count('id')) \
            .order_by('month')

        trend_data = [{'month': t['month'].strftime('%b'), 'registrations': t['registrations']} for t in trend]

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

        try:
            my_result = ExamResult.objects.get(user=request.user, olympiad=olympiad)
        except ExamResult.DoesNotExist:
            return Response({'error': 'Result not found'}, status=404)

        rank = ExamResult.objects.filter(olympiad=olympiad, score__gt=my_result.score).count() + 1
        total_participants = ExamResult.objects.filter(olympiad=olympiad).count()

        try:
            test = olympiad.test
        except:
            return Response({'error': 'Test not found'}, status=404)

        questions_data = []
        user_answers = my_result.answers_json or {}
        correct_count = wrong_count = no_answer_count = 0
        lang = request.query_params.get('lang', 'uz')

        for q in test.questions.all().order_by('id'):
            user_ans = user_answers.get(str(q.id))
            is_correct = user_ans == q.correct_option

            if not user_ans:
                no_answer_count += 1
            elif is_correct:
                correct_count += 1
            else:
                wrong_count += 1

            questions_data.append({
                'id': q.id,
                'text': q.get_translated('text', lang),
                'options': q.options,
                'user_answer': user_ans,
                'correct_answer': q.correct_option,
                'is_correct': is_correct,
                'image': q.image.url if q.image else None
            })

        leaderboard = ExamResult.objects.filter(olympiad=olympiad).order_by('-score', 'completed_at')[:10]
        leaderboard_data = [{
            'rank': i + 1,
            'username': res.user.username,
            'full_name': f"{res.user.last_name} {res.user.first_name}",
            'score': res.score,
            'is_me': res.user == request.user
        } for i, res in enumerate(leaderboard)]

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
        elif target in ['specific', 'group']:
            users_to_notify = participants.filter(id__in=user_ids)
        elif target == 'olympiad_participants':
            users_to_notify = participants.filter(registrations__olympiad_id=olympiad_id)
        elif target == 'olympiad_results':
            users_to_notify = participants.filter(exam_results__olympiad_id=olympiad_id)
        else:
            users_to_notify = User.objects.none()

        notifs_to_create = [Notification(user=u, **data) for u in users_to_notify.distinct()]
        created_notifs = Notification.objects.bulk_create(notifs_to_create)

        # Trigger manual broadcasts since bulk_create skips signals
        channel_layer = get_channel_layer()

        for notif in created_notifs:
            async_to_sync(channel_layer.group_send)(
                f'user_{notif.user.id}',
                {
                    'type': 'notification_send',
                    'data': {
                        'id': notif.id,
                        'title_ru': notif.title_ru,
                        'title_uz': notif.title_uz,
                        'message_ru': notif.message_ru,
                        'message_uz': notif.message_uz,
                        'type': notif.type,
                        'created_at': timezone.now().isoformat()
                    }
                }
            )

        return Response({'success': True, 'count': len(created_notifs)})