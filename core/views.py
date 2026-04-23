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
    OlympiadSerializer, SubOlympiadSerializer, SubOlympiadGradeSerializer,
    QuestionSerializer, QuestionExamSerializer, RegistrationSerializer,
    TestSerializer, NotificationSerializer, RegionSerializer
)
from .models import (
    User, Olympiad, SubOlympiad, SubOlympiadGrade,
    Registration, ExamResult, Test, Question,
    Notification, Region
)
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
        sub_olympiad_grade_id = request.data.get('sub_olympiad_grade')

        lookup = {}
        if sub_olympiad_grade_id:
            lookup['sub_olympiad_grade_id'] = sub_olympiad_grade_id
        elif sub_olympiad_id:
            lookup['sub_olympiad_id'] = sub_olympiad_id
        elif olympiad_id:
            lookup['olympiad_id'] = olympiad_id

        test, created = Test.objects.get_or_create(
            **lookup,
            defaults={
                'title': request.data.get('title', f"Test for {sub_olympiad_grade_id or sub_olympiad_id or olympiad_id}")
            }
        )

        serializer = self.get_serializer(test)
        status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(serializer.data, status=status_code)


class SubOlympiadViewSet(viewsets.ModelViewSet):
    queryset = SubOlympiad.objects.all()
    serializer_class = SubOlympiadSerializer
    permission_classes = (IsAdminUserOrReadOnly,)


class SubOlympiadGradeViewSet(viewsets.ModelViewSet):
    """
    CRUD for grade-specific sessions within a subject.
    Supports start_now / finish_now per-grade controls.
    """
    queryset = SubOlympiadGrade.objects.all()
    serializer_class = SubOlympiadGradeSerializer
    permission_classes = (IsAdminUserOrReadOnly,)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def start_now(self, request, pk=None):
        session = self.get_object()
        session.is_started = True
        session.is_completed = False
        session.save()

        olympiad = session.sub_olympiad.olympiad
        regs = olympiad.registrations.filter(payment_status__in=['paid', 'free'])

        notifs_to_create = []
        for reg in regs:
            user_grade = str(reg.user.grade or '').strip()
            session_grade = str(session.grade).strip()
            if user_grade != session_grade:
                continue  # notify only participants of this grade
            notifs_to_create.append(Notification(
                user=reg.user,
                title_ru=f"Предмет {session.sub_olympiad.title_ru} ({session.grade} кл.) начался!",
                title_uz=f"Fan {session.sub_olympiad.title_uz} ({session.grade}-sinf) boshlandi!",
                title_en=f"Subject {session.sub_olympiad.title_en} (Grade {session.grade}) started!",
                message_ru=f"Вы можете приступить к тесту по предмету {session.sub_olympiad.title_ru} в личном кабинете.",
                message_uz=f"Shaxsiy kabinetda {session.sub_olympiad.title_uz} fanidan testni boshlashingiz mumkin.",
                message_en=f"You can now start the test for {session.sub_olympiad.title_en} in your dashboard.",
                type='success'
            ))

        created_notifs = Notification.objects.bulk_create(notifs_to_create)

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            'olympiads',
            {
                'type': 'olympiad_update',
                'data': {'event': 'GRADE_STARTED', 'session_id': session.id,
                         'sub_id': session.sub_olympiad.id, 'grade': session.grade}
            }
        )

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

        return Response({'status': f'Grade {session.grade} session started'})

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def finish_now(self, request, pk=None):
        session = self.get_object()
        session.is_started = False
        session.is_completed = True
        session.save()

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            'olympiads',
            {
                'type': 'olympiad_update',
                'data': {'event': 'GRADE_FINISHED', 'session_id': session.id,
                         'sub_id': session.sub_olympiad.id, 'grade': session.grade}
            }
        )
        return Response({'status': f'Grade {session.grade} session finished'})


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

        user = authenticate(username=login_input, password=password)

        if not user:
            users_with_phone = User.objects.filter(phone=login_input)
            valid_users = [u for u in users_with_phone if u.check_password(password)]

            if len(valid_users) > 1:
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
                    'message': 'Multiple accounts found. Please choose one.'
                }, status=status.HTTP_200_OK)
            elif len(valid_users) == 1:
                user = valid_users[0]

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

        return Response({'error': 'Invalid username or password'}, status=status.HTTP_401_UNAUTHORIZED)


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

    @action(detail=True, methods=['post'])
    def reset_password(self, request, pk=None):
        user = self.get_object()
        new_password = request.data.get('new_password')
        if not new_password:
            return Response({'error': 'Пароль не может быть пустым'}, status=400)
        user.set_password(new_password)
        user.save()
        return Response({'success': True, 'message': f'Пароль для {user.username} успешно обновлен'})


class RegistrationViewSet(viewsets.ModelViewSet):
    serializer_class = RegistrationSerializer
    permission_classes = (permissions.IsAuthenticated,)
    http_method_names = ['get', 'delete'] # Only allow GET and DELETE

    def get_queryset(self):
        Registration.objects.filter(
            user=self.request.user,
            payment_status=Registration.PaymentStatus.PENDING,
            payment_deadline__lt=timezone.now()
        ).update(payment_status=Registration.PaymentStatus.EXPIRED)
        return Registration.objects.filter(user=self.request.user).order_by('-registered_at')

    def perform_destroy(self, instance):
        if instance.payment_status not in [Registration.PaymentStatus.PENDING, Registration.PaymentStatus.EXPIRED]:
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Нельзя отменить оплаченную регистрацию.")
        instance.delete()



class GetPaymeLinkView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, registration_id):
        registration = generics.get_object_or_404(Registration, id=registration_id, user=request.user)

        if registration.payment_status in ['paid', 'free']:
            return Response({'error': 'Already paid'}, status=status.HTTP_400_BAD_REQUEST)

        amount = registration.olympiad.price
        if not amount or amount <= 0:
            return Response({'error': 'Invalid payment amount'}, status=status.HTTP_400_BAD_REQUEST)

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
        user = self.request.user
        if not user.is_authenticated:
            return Olympiad.objects.filter(is_active=True)

        if user.role in ['admin', 'superadmin']:
            return Olympiad.objects.all()

        # For participants:
        # 1. Shows olympiads they are registered for
        # 2. Shows active olympiads that match their grade
        reg_filter = models.Q(registrations__user=user)
        
        grade_filter = models.Q(is_active=True)
        if user.grade:
            user_grade = str(user.grade).strip()
            grade_filter &= (
                models.Q(grades=[]) | 
                models.Q(subs__grade_sessions__grade__iexact=user_grade)
            )
        
        return Olympiad.objects.filter(reg_filter | grade_filter).distinct()


    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def start_now(self, request, pk=None):
        olympiad = self.get_object()
        olympiad.is_started = True
        olympiad.is_completed = False
        olympiad.save()

        regs = olympiad.registrations.filter(payment_status__in=['paid', 'free'])
        notifs_to_create = []
        for reg in regs:
            notifs_to_create.append(Notification(
                user=reg.user,
                title_ru=f"Олимпиада {olympiad.title_ru} началась!",
                title_uz=f"Olimpiada {olympiad.title_uz} boshlandi!",
                title_en=f"Olympiad {olympiad.title_en} started!",
                message_ru="Олимпиада началась. Вы можете приступить к выполнению предметов в личном кабинете.",
                message_uz="Olimpiada boshlandi. Shaxsiy kabinetda fanlarni bajarishni boshlashingiz mumkin.",
                message_en="The olympiad has started. You can now start the test in your dashboard.",
                type='success'
            ))

        created_notifs = Notification.objects.bulk_create(notifs_to_create)
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            'olympiads',
            {'type': 'olympiad_update', 'data': {'event': 'STARTED', 'id': olympiad.id, 'is_sub': False}}
        )
        for notif in created_notifs:
            async_to_sync(channel_layer.group_send)(
                f'user_{notif.user.id}',
                {'type': 'notification_send', 'data': {
                    'id': notif.id, 'title_ru': notif.title_ru, 'title_uz': notif.title_uz,
                    'message_ru': notif.message_ru, 'message_uz': notif.message_uz,
                    'type': notif.type, 'created_at': timezone.now().isoformat()
                }}
            )
        return Response({'status': 'Olympiad started'})

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def finish_now(self, request, pk=None):
        olympiad = self.get_object()
        olympiad.is_started = False
        olympiad.is_completed = True
        olympiad.save()
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            'olympiads',
            {'type': 'olympiad_update', 'data': {'event': 'FINISHED', 'id': olympiad.id, 'is_sub': False}}
        )
        return Response({'status': 'Olympiad finished'})


class RegisterForOlympiadView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @swagger_auto_schema(responses={201: RegistrationSerializer, 400: 'Ошибка'})
    def post(self, request, pk):
        olympiad = generics.get_object_or_404(Olympiad, pk=pk)
        now = timezone.now()

        if olympiad.start_datetime and now >= olympiad.start_datetime:
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
                'price': olympiad.price,
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
                    'title_ru': 'Ранняя пташка', 'title_uz': 'Erta tong pahlavoni',
                    'title_en': 'Early Bird', 'icon': 'Bird'
                }
            )

        if Registration.objects.filter(user=request.user).count() >= 3:
            UserAchievement.objects.get_or_create(
                user=request.user, type='regular',
                defaults={
                    'title_ru': 'Постоянный участник', 'title_uz': 'Doimiy ishtirokchi',
                    'title_en': 'Regular Participant', 'icon': 'Trophy'
                }
            )

        response_data = RegistrationSerializer(registration).data

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
    """
    GET /api/exam/grade-session/<grade_session_id>/
    Returns questions for the user's specific grade session.
    """
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, grade_session_id):
        session = generics.get_object_or_404(SubOlympiadGrade, pk=grade_session_id)

        # Verify user's grade matches this session
        user_grade = str(request.user.grade or '').strip()
        if user_grade != str(session.grade).strip():
            return Response({'error': 'Этот тест не предназначен для вашего класса'}, status=status.HTTP_403_FORBIDDEN)

        # Verify registration for this olympiad
        olympiad = session.sub_olympiad.olympiad
        registration = generics.get_object_or_404(Registration, user=request.user, olympiad=olympiad)

        if registration.payment_status not in ['paid', 'free']:
            return Response({'error': 'Оплата не подтверждена'}, status=status.HTTP_403_FORBIDDEN)

        if not session.is_started or session.is_completed:
            return Response({'error': 'Тест ещё не начался или уже завершён'}, status=status.HTTP_403_FORBIDDEN)

        # Check if already completed
        existing_result = ExamResult.objects.filter(
            user=request.user, sub_olympiad_grade=session
        ).first()

        if existing_result and existing_result.completed_at:
            return Response({'error': 'Вы уже завершили этот тест'}, status=status.HTTP_403_FORBIDDEN)

        if not existing_result:
            existing_result = ExamResult.objects.create(
                user=request.user,
                olympiad=olympiad,
                sub_olympiad_grade=session,
                start_time=timezone.now()
            )

        try:
            test = session.test
        except Test.DoesNotExist:
            return Response({'error': 'Тест не найден для этого класса'}, status=404)

        serializer = QuestionExamSerializer(test.questions.all(), many=True, context={'request': request})
        return Response({
            'questions': serializer.data,
            'start_time': existing_result.start_time,
            'server_time': timezone.now(),
            'duration_minutes': session.duration_minutes
        })


class SubmitResultView(APIView):
    """
    POST /api/exam/grade-session/<grade_session_id>/submit/
    """
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, grade_session_id):
        session = generics.get_object_or_404(SubOlympiadGrade, pk=grade_session_id)
        answers = request.data.get('answers', {})
        tab_switches = request.data.get('tab_switches', 0)

        result = generics.get_object_or_404(
            ExamResult, user=request.user, sub_olympiad_grade=session
        )

        if result.completed_at:
            return Response({'error': 'Test already submitted'}, status=400)

        try:
            test = session.test
        except Test.DoesNotExist:
            return Response({'error': 'Test not found'}, status=404)

        questions = test.questions.all()
        if not questions.exists():
            return Response({'error': 'Test has no questions'}, status=400)

        correct_count = sum(
            1 for q in questions if answers.get(str(q.id)) == q.correct_option
        )
        score = round((correct_count / questions.count()) * 100) if questions.count() > 0 else 0

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
                    'title_ru': 'Золотая медаль (Топ результат)', 'title_uz': 'Oltin medal (Top natija)',
                    'title_en': 'Gold Medal (Top Result)', 'icon': 'Star'
                }
            )
        elif score >= 70:
            UserAchievement.objects.get_or_create(
                user=request.user, type='silver',
                defaults={
                    'title_ru': 'Серебряная медаль', 'title_uz': 'Kumush medal',
                    'title_en': 'Silver Medal', 'icon': 'Award'
                }
            )

        now_hour = timezone.now().hour
        if 0 <= now_hour < 6:
            UserAchievement.objects.get_or_create(
                user=request.user, type='night_owl',
                defaults={
                    'title_ru': 'Ночная сова', 'title_uz': 'Tun qushi',
                    'title_en': 'Night Owl', 'icon': 'Moon'
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
                'fill': round((reg_count / oly.max_participants * 100), 1) if oly.max_participants and oly.max_participants > 0 else 0,
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

    def get(self, request, olympiad_id=None, grade_session_id=None):
        # We might receive olympiad_id from /exams/<id>/analysis/
        # OR we might receive grade_session_id from /exams/grade-session/<id>/analysis/
        
        target_olympiad_id = olympiad_id
        session_id = request.query_params.get('session_id') or \
                     request.query_params.get('grade_session_id') or \
                     request.query_params.get('sub_olympiad_grade')
        
        # If we got grade_session_id from URL, use it as session_id
        if grade_session_id:
            session_id = grade_session_id
            from .models import SubOlympiadGrade
            gs = get_object_or_404(SubOlympiadGrade, id=grade_session_id)
            target_olympiad_id = gs.sub_olympiad.olympiad_id
            
        olympiad = get_object_or_404(Olympiad, id=target_olympiad_id)
        
        query = ExamResult.objects.filter(user=request.user, olympiad=olympiad)
        if session_id:
            query = query.filter(sub_olympiad_grade_id=session_id)
            
        my_result = query.first()
        if not my_result:
            return Response({'error': f'Result not found for olympiad {target_olympiad_id} and session {session_id}'}, status=404)
            
        if not my_result.completed_at:
            if not my_result.answers_json:
                return Response({'error': 'Attempt not completed yet (completed_at is missing and no answers found)'}, status=400)
            # Proceed anyway if we have answers, but don't save to DB as requested
            pass
            
        if not my_result.start_time:
            # Fallback if start_time is missing for some reason
            my_result.start_time = my_result.completed_at - timezone.timedelta(minutes=olympiad.duration_minutes or 60)
            my_result.save()

        rank_query = ExamResult.objects.filter(olympiad=olympiad, completed_at__isnull=False)
        if my_result.sub_olympiad_grade:
            rank_query = rank_query.filter(sub_olympiad_grade=my_result.sub_olympiad_grade)
        else:
            rank_query = rank_query.filter(sub_olympiad_grade__isnull=True)

        my_duration = my_result.completed_at - my_result.start_time
        from django.db.models import F, ExpressionWrapper, fields as db_fields, Q
        better_results = rank_query.annotate(
            duration=ExpressionWrapper(F('completed_at') - F('start_time'), output_field=db_fields.DurationField())
        ).filter(
            Q(score__gt=my_result.score) |
            Q(score=my_result.score, duration__lt=my_duration)
        ).count()

        rank = better_results + 1
        total_participants = rank_query.count()

        test = None
        if my_result.sub_olympiad_grade:
            test = getattr(my_result.sub_olympiad_grade, 'test', None)
        else:
            test = getattr(olympiad, 'test', None)

        if not test:
            return Response({'error': 'Test not found'}, status=404)

        questions_data = []
        user_answers = my_result.answers_json or {}
        correct_count = wrong_count = no_answer_count = 0

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

        leaderboard = rank_query.annotate(
            duration=ExpressionWrapper(F('completed_at') - F('start_time'), output_field=db_fields.DurationField())
        ).order_by('-score', 'duration')[:10]

        leaderboard_data = [{
            'rank': i + 1,
            'username': res.user.username,
            'full_name': f"{res.user.last_name} {res.user.first_name}",
            'score': res.score,
            'is_me': res.user == request.user
        } for i, res in enumerate(leaderboard)]

        session_title = None
        if my_result.sub_olympiad_grade:
            session_title = my_result.sub_olympiad_grade.sub_olympiad.get_translated('title', lang)

        return Response({
            'olympiad_title': olympiad.get_translated('title', lang),
            'sub_title': session_title,
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


class PersonalResultsListView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        target_user = request.user
        user_id = request.query_params.get('user_id')

        if user_id and request.user.is_staff:
            try:
                target_user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return Response({"error": "User not found"}, status=404)

        results = ExamResult.objects.filter(
            user=target_user,
            completed_at__isnull=False
        ).select_related('olympiad', 'sub_olympiad_grade', 'sub_olympiad_grade__sub_olympiad')

        lang = request.query_params.get('lang', 'uz')
        data = []
        for res in results:
            is_visible = False
            if res.olympiad:
                if res.olympiad.olympiad_type == 'online' or res.olympiad.is_free:
                    is_visible = True
                elif res.olympiad.is_completed:
                    is_visible = True
            else:
                is_visible = True

            if not is_visible:
                continue

            session_title = None
            session_id = None
            if res.sub_olympiad_grade:
                session_title = res.sub_olympiad_grade.sub_olympiad.get_translated('title', lang)
                session_id = res.sub_olympiad_grade.id

            data.append({
                'id': res.id,
                'olympiad_id': res.olympiad.id if res.olympiad else None,
                'olympiad_title': res.olympiad.get_translated('title', lang) if res.olympiad else "Unknown Olympiad",
                'olympiad_type': res.olympiad.olympiad_type if res.olympiad else 'online',
                'session_id': session_id,
                'sub_olympiad_title': session_title,
                'grade': res.sub_olympiad_grade.grade if res.sub_olympiad_grade else None,
                'score': res.score,
                'completed_at': res.completed_at,
            })

        return Response(data)


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


class AllResultsListView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        if request.user.role != User.Role.ADMIN and not request.user.is_superuser:
            return Response({'error': 'Forbidden'}, status=403)

        results = ExamResult.objects.filter(
            completed_at__isnull=False
        ).select_related('user', 'olympiad', 'sub_olympiad_grade', 'sub_olympiad_grade__sub_olympiad').order_by('-completed_at')

        lang = request.query_params.get('lang', 'uz')
        data = []
        for res in results:
            session_title = None
            session_id = None
            if res.sub_olympiad_grade:
                session_title = res.sub_olympiad_grade.sub_olympiad.get_translated('title', lang)
                session_id = res.sub_olympiad_grade.id

            data.append({
                'id': res.id,
                'user_id': res.user.id,
                'user_name': f'{res.user.last_name} {res.user.first_name}',
                'participant_id': res.user.participant_id,
                'olympiad_id': res.olympiad.id if res.olympiad else None,
                'olympiad_title': res.olympiad.get_translated('title', lang) if res.olympiad else 'Unknown',
                'session_id': session_id,
                'sub_olympiad_title': session_title,
                'grade': res.sub_olympiad_grade.grade if res.sub_olympiad_grade else None,
                'score': res.score,
                'completed_at': res.completed_at,
                'time_spent': (res.completed_at - res.start_time).total_seconds() // 60 if res.completed_at and res.start_time else 0
            })

        return Response(data)