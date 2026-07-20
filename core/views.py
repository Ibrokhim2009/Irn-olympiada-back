import hashlib
import json
import logging
import pyotp
import requests
import threading
from django.core import signing
from django.conf import settings
from django.db import models, transaction
from django.http import FileResponse, Http404
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
    RegisterSerializer, UserSerializer, UserListSerializer, LoginRequestSerializer,
    OlympiadSerializer, SubOlympiadSerializer, SubOlympiadGradeSerializer,
    QuestionSerializer, QuestionExamSerializer, RegistrationSerializer,
    TestSerializer, NotificationSerializer, RegionSerializer, ExamResultSerializer,
    SupportTicketSerializer, TicketReplySerializer, EditRequestSerializer,
    BookSerializer, BookOrderSerializer,
    VisaApplicantListSerializer, VisaApplicantDetailSerializer,
    VisaDocumentSerializer, VisaNoteSerializer, VisaTaskSerializer, VisaAuditLogSerializer
)
from .models import (
    User, Olympiad, SubOlympiad, SubOlympiadGrade,
    Registration, ExamResult, Test, Question,
    Notification, Region, SupportTicket, TicketReply,
    SMSSentHistory, ClickTransactions, EditRequest, Book, BookOrder,
    VisaApplicant, VisaDocument, VisaNote, VisaTask, VisaAuditLog
)
from .permissions import IsAdminUserOrReadOnly, IsAdminOrCoordinatorReadOnly, IsAdminOrCoordinator
from .utils_payme import get_payme_link
from .utils_click import get_click_link
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
        user_ids = request.data.get('user_ids', [])

        if user_ids:
            # Start only for specific users
            users = User.objects.filter(id__in=user_ids)
            notifs_to_create = []
            for user in users:
                ExamResult.objects.get_or_create(
                    user=user,
                    olympiad=session.sub_olympiad.olympiad,
                    sub_olympiad_grade=session,
                    defaults={'start_time': timezone.now()}
                )
                notifs_to_create.append(Notification(
                    user=user,
                    title_ru=f"Предмет {session.sub_olympiad.title_ru} доступен для вас!",
                    title_uz=f"Fan {session.sub_olympiad.title_uz} siz uchun ochildi!",
                    title_en=f"Subject {session.sub_olympiad.title_en} is available for you!",
                    message_ru=f"Администратор открыл вам доступ к тесту {session.sub_olympiad.title_ru} ({session.grade} кл.).",
                    message_uz=f"Admin sizga {session.sub_olympiad.title_uz} ({session.grade}-sinf) fanidan testga ruxsat berdi.",
                    message_en=f"Admin has granted you access to the test for {session.sub_olympiad.title_en} (Grade {session.grade}).",
                    type='success'
                ))
            
            Notification.objects.bulk_create(notifs_to_create)
            return Response({'status': f'Grade {session.grade} session started for {len(user_ids)} users'})

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
        user_ids = request.data.get('user_ids', [])

        if user_ids:
            # Finish only for specific users — mark their exam results as completed
            results = ExamResult.objects.filter(
                sub_olympiad_grade=session,
                user__id__in=user_ids,
                completed_at__isnull=True
            )
            updated = results.update(
                completed_at=timezone.now(),
                score=0  # score=0 if not submitted normally; can be overridden
            )
            return Response({'status': f'Finished exam for {updated} user(s) in grade {session.grade} session'})

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
            if user.totp_enabled:
                pre_auth_token = signing.dumps({'user_id': user.id}, salt='visa-2fa-login')
                return Response({'requires_2fa': True, 'pre_auth_token': pre_auth_token})

            refresh = RefreshToken.for_user(user)
            return Response({
                'user': UserSerializer(user).data,
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            })

        return Response({'error': 'Invalid username or password'}, status=status.HTTP_401_UNAUTHORIZED)


class TwoFactorVerifyView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        pre_auth_token = request.data.get('pre_auth_token')
        code = request.data.get('code')
        if not pre_auth_token or not code:
            return Response({'error': 'pre_auth_token and code are required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            payload = signing.loads(pre_auth_token, salt='visa-2fa-login', max_age=300)
        except signing.BadSignature:
            return Response({'error': 'Invalid or expired login attempt'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(id=payload['user_id'], totp_enabled=True)
        except User.DoesNotExist:
            return Response({'error': 'Invalid or expired login attempt'}, status=status.HTTP_400_BAD_REQUEST)

        if not pyotp.TOTP(user.totp_secret).verify(code, valid_window=1):
            return Response({'error': 'Invalid code'}, status=status.HTTP_400_BAD_REQUEST)

        refresh = RefreshToken.for_user(user)
        return Response({
            'user': UserSerializer(user).data,
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        })


class TwoFactorSetupView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request):
        secret = pyotp.random_base32()
        request.user.totp_secret = secret
        request.user.save(update_fields=['totp_secret'])
        otpauth_url = pyotp.TOTP(secret).provisioning_uri(name=request.user.username, issuer_name="IRN Olympiads")
        return Response({'secret': secret, 'otpauth_url': otpauth_url})


class TwoFactorConfirmView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request):
        code = request.data.get('code')
        if not request.user.totp_secret or not code:
            return Response({'error': 'code is required'}, status=status.HTTP_400_BAD_REQUEST)
        if not pyotp.TOTP(request.user.totp_secret).verify(code, valid_window=1):
            return Response({'error': 'Invalid code'}, status=status.HTTP_400_BAD_REQUEST)
        request.user.totp_enabled = True
        request.user.save(update_fields=['totp_enabled'])
        return Response({'success': True})


class TwoFactorDisableView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request):
        password = request.data.get('password')
        if not password or not request.user.check_password(password):
            return Response({'error': 'Invalid password'}, status=status.HTTP_400_BAD_REQUEST)
        request.user.totp_enabled = False
        request.user.totp_secret = None
        request.user.save(update_fields=['totp_enabled', 'totp_secret'])
        return Response({'success': True})


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
    max_page_size = 50000


class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = (IsAdminOrCoordinatorReadOnly,)
    pagination_class = UserPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = []
    search_fields = ['username', 'first_name', 'last_name', 'middle_name', 'phone', 'participant_id', 'registrations__unique_participant_id']
    ordering_fields = ['date_joined', 'first_name', 'last_name']

    def get_serializer_class(self):
        if self.action == 'list':
            return UserListSerializer
        return self.serializer_class

    def get_queryset(self):
        role = self.request.query_params.get('role')
        if role:
            queryset = User.objects.filter(role=role)
        elif self.action in ['retrieve', 'update', 'partial_update', 'destroy']:
            queryset = User.objects.all()
        else:
            queryset = User.objects.filter(role=User.Role.PARTICIPANT)
        if self.action in ['retrieve', 'update', 'partial_update']:
            queryset = queryset.prefetch_related(
                'registrations__olympiad',
                'exam_results__sub_olympiad_grade__sub_olympiad',
                'notifications',
                'achievements'
            )
        elif self.action == 'list':
            queryset = queryset.prefetch_related(
                'registrations__olympiad'
            )
        queryset = queryset.order_by('-date_joined')
        
        regions = self.request.query_params.getlist('region') or self.request.query_params.getlist('region[]')
        if not regions and 'region' in self.request.query_params:
            regions = self.request.query_params.get('region').split(',')
        if regions:
            regions = [r.strip() for r in regions if r.strip()]
            if regions:
                queryset = queryset.filter(region__in=regions)

        grades = self.request.query_params.getlist('grade') or self.request.query_params.getlist('grade[]')
        if not grades and 'grade' in self.request.query_params:
            grades = self.request.query_params.get('grade').split(',')
        if grades:
            grades = [g.strip() for g in grades if g.strip()]
            if grades:
                queryset = queryset.filter(grade__in=grades)

        olympiads = self.request.query_params.getlist('registrations__olympiad') or self.request.query_params.getlist('registrations__olympiad[]')
        if not olympiads and 'registrations__olympiad' in self.request.query_params:
            olympiads = self.request.query_params.get('registrations__olympiad').split(',')
        if olympiads:
            olympiads = [o.strip() for o in olympiads if o.strip()]

        payment_status = self.request.query_params.get('payment_status') or self.request.query_params.get('registrations__payment_status')
        if olympiads and payment_status:
            if payment_status == 'paid':
                queryset = queryset.filter(
                    models.Q(registrations__olympiad__in=olympiads) & (
                        models.Q(registrations__payment_status='paid') |
                        models.Q(registrations__olympiad__olympiad_type='online')
                    )
                ).distinct()
            elif payment_status == 'pending':
                queryset = queryset.filter(
                    registrations__olympiad__in=olympiads,
                    registrations__payment_status='pending'
                ).distinct()
            elif payment_status == 'not_paid':
                queryset = queryset.filter(
                    models.Q(registrations__olympiad__in=olympiads) & ~models.Q(
                        models.Q(registrations__payment_status__in=['paid', 'pending']) |
                        models.Q(registrations__olympiad__olympiad_type='online')
                    )
                ).distinct()
        else:
            if olympiads:
                queryset = queryset.filter(registrations__olympiad__in=olympiads).distinct()
            if payment_status:
                if payment_status == 'paid':
                    queryset = queryset.filter(
                        models.Q(registrations__payment_status='paid') |
                        models.Q(registrations__olympiad__olympiad_type='online')
                    ).distinct()
                elif payment_status == 'pending':
                    queryset = queryset.filter(registrations__payment_status='pending').distinct()
                elif payment_status == 'not_paid':
                    queryset = queryset.filter(registrations__isnull=False).exclude(
                        models.Q(registrations__payment_status__in=['paid', 'pending']) |
                        models.Q(registrations__olympiad__olympiad_type='online')
                    ).distinct()

        return queryset

    @action(detail=False, methods=['get'], url_path='sms-stats')
    def sms_stats(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        total_profiles = queryset.count()
        
        template_id = request.query_params.get('template_id')
        
        # Get all phone numbers from the filtered queryset
        phones = list(queryset.exclude(phone='').values_list('phone', flat=True))
        
        unique_phones_set = set(p.strip() for p in phones if p)
        total_unique_phones = len(unique_phones_set)
        
        already_sent_phones_count = 0
        already_sent_user_ids_count = 0
        
        if template_id and total_unique_phones > 0:
            try:
                # Get all phone numbers that have received this template
                all_sent_phones = set(
                    User.objects.filter(sms_history__template_id=template_id)
                    .exclude(phone='')
                    .values_list('phone', flat=True)
                )
                # Intersection of sent phones with unique phones in the current filtered set
                already_sent_phones_count = len(unique_phones_set.intersection(all_sent_phones))
                
                # Find how many users in our current queryset are in all_sent_user_ids
                all_sent_user_ids = set(
                    SMSSentHistory.objects.filter(template_id=template_id).values_list('user_id', flat=True)
                )
                filtered_user_ids = set(queryset.values_list('id', flat=True))
                already_sent_user_ids_count = len(filtered_user_ids.intersection(all_sent_user_ids))
            except Exception as e:
                print(f"Error querying SMSSentHistory in sms_stats: {e}")
                already_sent_phones_count = 0
                already_sent_user_ids_count = 0
            
        return Response({
            'total_profiles': total_profiles,
            'total_unique_phones': total_unique_phones,
            'already_sent_phones': already_sent_phones_count,
            'already_sent_users': already_sent_user_ids_count,
        })

    @action(detail=True, methods=['post'])
    def reset_password(self, request, pk=None):
        user = self.get_object()
        new_password = request.data.get('new_password')
        if not new_password:
            return Response({'error': 'Пароль не может быть пустым'}, status=400)
        user.set_password(new_password)
        user.password_text = new_password
        user.save()
        return Response({'success': True, 'message': f'Пароль для {user.username} успешно обновлен'})


class RegistrationViewSet(viewsets.ModelViewSet):
    serializer_class = RegistrationSerializer
    permission_classes = (permissions.IsAuthenticated,)
    http_method_names = ['get', 'delete', 'patch', 'put']

    def perform_update(self, serializer):
        user = self.request.user
        if not (user.role in ['admin', 'superadmin']):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only administrators can update registration data.")
        
        # Mark as manually edited if payment_status changed
        old_instance = self.get_object()
        new_status = serializer.validated_data.get('payment_status')
        if new_status and new_status != old_instance.payment_status:
            serializer.validated_data['transaction_id'] = 'manual'
            
        serializer.save()

    def get_queryset(self):
        user = self.request.user
        # Cleanup expired registrations for current user if not admin
        if not user.role in ['admin', 'superadmin'] and not user.is_staff:
            Registration.objects.filter(
                user=user,
                payment_status=Registration.PaymentStatus.PENDING,
                payment_deadline__lt=timezone.now()
            ).update(payment_status=Registration.PaymentStatus.EXPIRED)
            return Registration.objects.filter(user=user).order_by('-registered_at')
        
        # Admins see everything
        return Registration.objects.all().order_by('-registered_at')

    def perform_destroy(self, instance):
        user = self.request.user
        is_admin = user.role in ['admin', 'superadmin']
        
        if not is_admin:
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


class GetClickLinkView(APIView):
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

        return_url = request.query_params.get('return_url') or "https://irnolympiad.uz/dashboard"
        link = get_click_link(registration.id, amount, return_url)
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
        is_admin = request.user.role in ['admin', 'superadmin'] or request.user.is_staff or request.user.is_superuser
        now = timezone.now()

        if not is_admin:
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

        if not is_admin and olympiad.max_participants > 0 and reg_count >= olympiad.max_participants:
            if not Registration.objects.filter(
                user=request.user, olympiad=olympiad,
                payment_status__in=['paid', 'free', 'pending']
            ).exists():
                return Response({'error': 'Мест больше нет'}, status=status.HTTP_400_BAD_REQUEST)

        if olympiad.is_free or olympiad.price == 0:
            initial_status = Registration.PaymentStatus.FREE
        else:
            initial_status = Registration.PaymentStatus.PENDING

        target_user = request.user
        if request.user.role in ['admin', 'superadmin'] and request.data.get('user_id'):
            target_user = generics.get_object_or_404(User, id=request.data.get('user_id'))

        registration, created = Registration.objects.get_or_create(
            user=target_user,
            olympiad=olympiad,
            defaults={
                'payment_status': initial_status,
                'price': olympiad.price,
                'teacher_name': target_user.teacher_name,
                'teacher_phone': target_user.teacher_phone,
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
            # Allow individual access if result already exists
            if not ExamResult.objects.filter(user=request.user, sub_olympiad_grade=session).exists():
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


logger = logging.getLogger('click_payments')


class ClickCallbackView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        data = request.data
        
        # Log request and response for auditing
        logger.info(f"Click callback request received: {data}")
        print(f"Click callback request received: {data}")

        click_trans_id = data.get('click_trans_id')
        service_id = data.get('service_id')
        click_paydoc_id = data.get('click_paydoc_id')
        merchant_trans_id = data.get('merchant_trans_id')
        amount = data.get('amount')
        action = data.get('action')
        error = data.get('error')
        error_note = data.get('error_note')
        sign_time = data.get('sign_time')
        sign_string = data.get('sign_string')
        merchant_prepare_id = data.get('merchant_prepare_id')

        # Check required fields
        if None in [click_trans_id, service_id, merchant_trans_id, amount, action, error, sign_time, sign_string]:
            logger.error("Click Request Missing Required Parameters")
            return Response({
                "error": -2,
                "error_note": "Incorrect parameters"
            })

        # Validate types
        try:
            action = int(action)
            error = int(error)
        except ValueError:
            logger.error("Click Request Invalid action/error type")
            return Response({
                "error": -2,
                "error_note": "Invalid action or error parameter"
            })

        # Verify signature
        secret_key = settings.CLICK_SECRET_KEY
        
        # Build candidate amount strings to handle varying formats sent by Click
        amount_candidates = [str(amount)]
        try:
            float_amount = float(amount)
            amount_candidates.append(f"{float_amount:.2f}")
            amount_candidates.append(f"{float_amount:.1f}")
            amount_candidates.append(f"{int(float_amount)}")
        except (ValueError, TypeError):
            pass

        # De-duplicate while preserving order
        unique_candidates = []
        for amt in amount_candidates:
            if amt not in unique_candidates:
                unique_candidates.append(amt)

        verified = False
        calculated_sign = ""
        
        for amt_candidate in unique_candidates:
            if action == 0:
                raw_sign = f"{click_trans_id}{service_id}{secret_key}{merchant_trans_id}{amt_candidate}{action}{sign_time}"
            elif action == 1:
                raw_sign = f"{click_trans_id}{service_id}{secret_key}{merchant_trans_id}{merchant_prepare_id}{amt_candidate}{action}{sign_time}"
            else:
                logger.error(f"Click Request Invalid Action: {action}")
                return Response({
                    "error": -3,
                    "error_note": "Action not found"
                })

            candidate_sign = hashlib.md5(raw_sign.encode('utf-8')).hexdigest()
            if candidate_sign == sign_string:
                verified = True
                calculated_sign = candidate_sign
                break
            if not calculated_sign:
                calculated_sign = candidate_sign

        if not verified:
            logger.error(f"Click Request Sign Verification Failed. Got: {sign_string}, Expected one of signature candidates. Sample: {calculated_sign}")
            return Response({
                "error": -1,
                "error_note": "SIGN CHECK FAILED"
            })

        # Check if the registration exists
        try:
            registration = Registration.objects.get(id=int(merchant_trans_id))
        except (Registration.DoesNotExist, ValueError):
            logger.error(f"Click Request Registration Not Found: {merchant_trans_id}")
            return Response({
                "error": -5,
                "error_note": "User/Registration not found"
            })

        # Check if the amount matches
        try:
            expected_amount = float(registration.price)
            received_amount = float(amount)
            if abs(expected_amount - received_amount) > 0.01:
                logger.error(f"Click Request Amount Mismatch. Expected: {expected_amount}, Received: {received_amount}")
                return Response({
                    "error": -2,
                    "error_note": "Incorrect parameter amount"
                })
        except ValueError:
            logger.error("Click Request Invalid Amount Type")
            return Response({
                "error": -2,
                "error_note": "Invalid amount"
            })

        if action == 0:
            # Prepare stage
            if registration.payment_status == Registration.PaymentStatus.PAID:
                logger.warning(f"Click Request Prepare failed: Registration {registration.id} is already paid")
                return Response({
                    "error": -4,
                    "error_note": "Already paid"
                })

            registration.transaction_id = f"CLICK_{click_trans_id}"
            registration.save(update_fields=['transaction_id'])
            
            # Log prepared transaction
            ClickTransactions.objects.update_or_create(
                transaction_id=str(click_trans_id),
                defaults={
                    'click_paydoc_id': str(click_paydoc_id) if click_paydoc_id else None,
                    'registration': registration,
                    'amount': amount,
                    'state': ClickTransactions.INITIATING
                }
            )
            
            logger.info(f"Click Prepare success for Registration {registration.id}")
            return Response({
                "click_trans_id": click_trans_id,
                "merchant_trans_id": merchant_trans_id,
                "merchant_prepare_id": registration.id,
                "error": 0,
                "error_note": "Success"
            })

        elif action == 1:
            # Complete stage
            if error < 0:
                logger.error(f"Click complete received error from Click: {error_note}")
                registration.payment_status = Registration.PaymentStatus.PENDING
                registration.save(update_fields=['payment_status'])

                # Log failed transaction
                ClickTransactions.objects.update_or_create(
                    transaction_id=str(click_trans_id),
                    defaults={
                        'click_paydoc_id': str(click_paydoc_id) if click_paydoc_id else None,
                        'registration': registration,
                        'amount': amount,
                        'state': ClickTransactions.CANCELED_DURING_INIT,
                        'cancel_reason': error_note or f"Error code: {error}",
                        'cancelled_at': timezone.now()
                    }
                )
                return Response({
                    "error": error,
                    "error_note": error_note or "Transaction failed"
                })

            if registration.payment_status == Registration.PaymentStatus.PAID:
                logger.info(f"Click Complete success (already paid) for Registration {registration.id}")
                # Log already paid/successful transaction
                ClickTransactions.objects.update_or_create(
                    transaction_id=str(click_trans_id),
                    defaults={
                        'click_paydoc_id': str(click_paydoc_id) if click_paydoc_id else None,
                        'registration': registration,
                        'amount': amount,
                        'state': ClickTransactions.SUCCESSFULLY,
                        'performed_at': timezone.now()
                    }
                )
                return Response({
                    "click_trans_id": click_trans_id,
                    "merchant_trans_id": merchant_trans_id,
                    "merchant_confirm_id": registration.id,
                    "error": 0,
                    "error_note": "Success"
                })

            registration.payment_status = Registration.PaymentStatus.PAID
            registration.transaction_id = f"CLICK_{click_trans_id}"
            registration.save(update_fields=['payment_status', 'transaction_id'])

            # Log successfully completed transaction
            ClickTransactions.objects.update_or_create(
                transaction_id=str(click_trans_id),
                defaults={
                    'click_paydoc_id': str(click_paydoc_id) if click_paydoc_id else None,
                    'registration': registration,
                    'amount': amount,
                    'state': ClickTransactions.SUCCESSFULLY,
                    'performed_at': timezone.now()
                }
            )

            logger.info(f"✅ Click Complete success: Registration {registration.id} marked as PAID")
            return Response({
                "click_trans_id": click_trans_id,
                "merchant_trans_id": merchant_trans_id,
                "merchant_confirm_id": registration.id,
                "error": 0,
                "error_note": "Success"
            })


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
            total_regs = oly.registrations.count()
            paid_count = oly.registrations.filter(
                models.Q(payment_status__in=['paid', 'free']) |
                models.Q(olympiad__olympiad_type='online')
            ).count()
            unpaid_count = total_regs - paid_count
            revenue = sum(r.price for r in oly.registrations.filter(payment_status='paid'))
            paid_free_count = oly.registrations.filter(payment_status__in=['paid', 'free']).count()
            oly_fill.append({
                'id': oly.id,
                'title_uz': oly.title_uz,
                'title_ru': oly.title_ru,
                'title_en': oly.title_en,
                'registered': total_regs,
                'paid_count': paid_count,
                'unpaid_count': unpaid_count,
                'max': oly.max_participants,
                'fill': round((paid_free_count / oly.max_participants * 100), 1) if oly.max_participants and oly.max_participants > 0 else 0,
                'type': oly.olympiad_type,
                'revenue': revenue
            })

        from django.db.models.functions import TruncMonth
        six_months_ago = timezone.now() - timezone.timedelta(days=180)
        trend = User.objects.filter(role=User.Role.PARTICIPANT, date_joined__gte=six_months_ago) \
            .annotate(month=TruncMonth('date_joined')) \
            .values('month') \
            .annotate(registrations=models.Count('id')) \
            .order_by('month')

        trend_data = [{'month': t['month'].strftime('%b'), 'registrations': t['registrations']} for t in trend]

        # Online users (active in last 5 minutes)
        five_mins_ago = timezone.now() - timezone.timedelta(minutes=5)
        online_users_qs = User.objects.filter(last_activity__gte=five_mins_ago)
        online_users_count = online_users_qs.count()
        online_users_list = [
            {
                'id': u.id,
                'full_name': f"{u.last_name} {u.first_name}",
                'participant_id': u.participant_id,
                'last_activity': u.last_activity
            } for u in online_users_qs.order_by('-last_activity')[:10] # Show top 10
        ]

        # Online Guests from Cache
        from django.core.cache import cache
        import time
        guests = cache.get('online_guests', {})
        current_ts = time.time()
        # Ensure we only count recent ones in case cleanup hasn't happened
        active_guests = {k: v for k, v in guests.items() if v > current_ts - 300}
        online_guests_count = len(active_guests)

        # Registration stats by date
        from datetime import timedelta
        try:
            today_date = timezone.localdate()
        except Exception:
            today_date = timezone.now().date()
        yesterday_date = today_date - timedelta(days=1)

        registered_today = User.objects.filter(role=User.Role.PARTICIPANT, date_joined__date=today_date).count()
        registered_yesterday = User.objects.filter(role=User.Role.PARTICIPANT, date_joined__date=yesterday_date).count()

        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        calendar_total = 0
        calendar_daily = []
        if start_date_str and end_date_str:
            try:
                from datetime import datetime
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                range_users = User.objects.filter(
                    role=User.Role.PARTICIPANT,
                    date_joined__date__range=(start_date, end_date)
                )
                calendar_total = range_users.count()
                daily_stats = range_users.values('date_joined__date').annotate(
                    count=models.Count('id')
                ).order_by('date_joined__date')
                calendar_daily = [
                    {
                        'date': item['date_joined__date'].strftime('%Y-%m-%d'),
                        'count': item['count']
                    }
                    for item in daily_stats if item['date_joined__date']
                ]
            except Exception as e:
                print(f"Error parsing dates for calendar registration count: {e}")

        return Response({
            'total_users': total_users,
            'total_participants': total_users,
            'online_users': online_users_count,
            'online_guests': online_guests_count,
            'total_online': online_users_count + online_guests_count,
            'online_users_list': online_users_list,
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
            'trend_data': trend_data,
            'registered_today': registered_today,
            'registered_yesterday': registered_yesterday,
            'calendar_total': calendar_total,
            'calendar_daily': calendar_daily
        })


class ResultAnalysisView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, olympiad_id=None, grade_session_id=None):
        lang = request.query_params.get('lang', 'ru')
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
            
        # Prioritize completed results if multiple exist
        my_result = query.order_by('-completed_at', '-id').first()
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
                'mistakes': res.mistakes or [],
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


class ResultsPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 50000


class AllResultsListView(APIView):
    permission_classes = (permissions.IsAuthenticated,)
    pagination_class = ResultsPagination

    def get(self, request):
        if request.user.role not in [User.Role.ADMIN, User.Role.COORDINATOR] and not request.user.is_superuser:
            return Response({'error': 'Forbidden'}, status=403)

        lang = request.query_params.get('lang', 'uz')

        get_filters = request.query_params.get('get_filters') == 'true'
        if get_filters:
            completed_results = ExamResult.objects.filter(completed_at__isnull=False)

            # Olympiads
            oly_ids = completed_results.values_list('olympiad_id', flat=True).distinct()
            olympiads = []
            for o in Olympiad.objects.filter(id__in=oly_ids):
                olympiads.append({
                    'id': o.id,
                    'title': o.get_translated('title', lang)
                })

            # Subjects (SubOlympiads)
            sub_ids = completed_results.exclude(sub_olympiad_grade__isnull=True).values_list('sub_olympiad_grade__sub_olympiad_id', flat=True).distinct()
            sub_ids_compat = completed_results.exclude(sub_olympiad__isnull=True).values_list('sub_olympiad_id', flat=True).distinct()
            all_sub_ids = list(set(sub_ids) | set(sub_ids_compat))
            
            subjects = []
            seen_sub_titles = set()
            for sub in SubOlympiad.objects.filter(id__in=all_sub_ids):
                title = sub.get_translated('title', lang)
                if title and title not in seen_sub_titles:
                    subjects.append(title)
                    seen_sub_titles.add(title)

            # Grades
            grades = list(completed_results.exclude(sub_olympiad_grade__isnull=True).values_list('sub_olympiad_grade__grade', flat=True).distinct())
            try:
                grades.sort(key=int)
            except ValueError:
                grades.sort()

            # Regions
            region_ids = completed_results.exclude(user__region__isnull=True).values_list('user__region_id', flat=True).distinct()
            regions = []
            for r in Region.objects.filter(id__in=region_ids):
                name = getattr(r, f'name_{lang}', None) or r.name_ru
                if name:
                    regions.append(name)
            regions.sort()

            return Response({
                'olympiads': olympiads,
                'subjects': subjects,
                'grades': grades,
                'regions': regions
            })

        queryset = ExamResult.objects.filter(
            completed_at__isnull=False
        ).select_related('user', 'olympiad', 'sub_olympiad_grade', 'sub_olympiad_grade__sub_olympiad').order_by('-completed_at')

        # 1. Search (user name or participant_id)
        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                models.Q(user__first_name__icontains=search) |
                models.Q(user__last_name__icontains=search) |
                models.Q(user__middle_name__icontains=search) |
                models.Q(user__participant_id__icontains=search)
            )

        # 2. Olympiad
        olympiads = request.query_params.getlist('olympiad') or request.query_params.getlist('olympiad[]')
        if not olympiads and 'olympiad' in request.query_params:
            olympiads = request.query_params.get('olympiad').split(',')
        if olympiads:
            olympiads = [o.strip() for o in olympiads if o.strip()]
            if olympiads:
                queryset = queryset.filter(olympiad__id__in=olympiads)

        # 3. Subject
        subjects = request.query_params.getlist('subject') or request.query_params.getlist('subject[]')
        if not subjects and 'subject' in request.query_params:
            subjects = request.query_params.get('subject').split(',')
        if subjects:
            subjects = [s.strip() for s in subjects if s.strip()]
            if subjects:
                queryset = queryset.filter(
                    models.Q(sub_olympiad_grade__sub_olympiad__title_ru__in=subjects) |
                    models.Q(sub_olympiad_grade__sub_olympiad__title_uz__in=subjects) |
                    models.Q(sub_olympiad_grade__sub_olympiad__title_en__in=subjects) |
                    models.Q(sub_olympiad__title_ru__in=subjects) |
                    models.Q(sub_olympiad__title_uz__in=subjects) |
                    models.Q(sub_olympiad__title_en__in=subjects)
                )

        # 4. Grade
        grades = request.query_params.getlist('grade') or request.query_params.getlist('grade[]')
        if not grades and 'grade' in request.query_params:
            grades = request.query_params.get('grade').split(',')
        if grades:
            grades = [g.strip() for g in grades if g.strip()]
            if grades:
                queryset = queryset.filter(sub_olympiad_grade__grade__in=grades)

        # 5. Region
        regions = request.query_params.getlist('region') or request.query_params.getlist('region[]')
        if not regions and 'region' in request.query_params:
            regions = request.query_params.get('region').split(',')
        if regions:
            regions = [r.strip() for r in regions if r.strip()]
            if regions:
                queryset = queryset.filter(
                    models.Q(user__region__name_ru__in=regions) |
                    models.Q(user__region__name_uz__in=regions) |
                    models.Q(user__region__name_en__in=regions) |
                    models.Q(user__region__id__in=[r for r in regions if r.isdigit()])
                )

        # 6. Sorting by score
        score_sort = request.query_params.get('score_sort')
        if score_sort == 'desc':
            queryset = queryset.order_by('-score', '-completed_at')
        elif score_sort == 'asc':
            queryset = queryset.order_by('score', '-completed_at')
        else:
            queryset = queryset.order_by('-completed_at')

        # Pagination
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)

        # Calculate stats for the entire filtered queryset
        from django.db.models import Max, Avg
        stats = queryset.aggregate(
            top_score=Max('score'),
            avg_score=Avg('score')
        )
        top_score = stats.get('top_score') or 0
        avg_score = round(stats.get('avg_score') or 0)
        total_count = queryset.count()

        data = []
        target_queryset = page if page is not None else queryset

        for res in target_queryset:
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
                'region_name': getattr(res.user.region, f'name_{lang}', '-') if res.user.region else '-',
                'school': res.user.school or '-',
                'olympiad_id': res.olympiad.id if res.olympiad else None,
                'olympiad_title': res.olympiad.get_translated('title', lang) if res.olympiad else 'Unknown',
                'session_id': session_id,
                'sub_olympiad_title': session_title,
                'grade': res.sub_olympiad_grade.grade if res.sub_olympiad_grade else None,
                'score': res.score,
                'completed_at': res.completed_at,
                'time_spent': (res.completed_at - res.start_time).total_seconds() // 60 if res.completed_at and res.start_time else 0
            })

        if page is not None:
            return Response({
                'count': total_count,
                'next': paginator.get_next_link(),
                'previous': paginator.get_previous_link(),
                'top_score': top_score,
                'avg_score': avg_score,
                'results': data
            })
        return Response(data)


class ExamResultViewSet(viewsets.ModelViewSet):
    queryset = ExamResult.objects.all().select_related('user', 'olympiad', 'sub_olympiad_grade')
    serializer_class = ExamResultSerializer
    permission_classes = (IsAdminOrCoordinatorReadOnly,)
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['sub_olympiad_grade', 'user', 'olympiad']

    @action(detail=True, methods=['post'])
    def reset(self, request, pk=None):
        result = self.get_object()
        result.delete()
        return Response({'success': True, 'message': 'Result reset successfully'})

    @action(detail=True, methods=['get', 'post'], permission_classes=[IsAdminOrCoordinatorReadOnly])
    def edit_answers(self, request, pk=None):
        result = self.get_object()
        
        if request.method == 'GET':
            test = None
            if result.sub_olympiad_grade:
                test = getattr(result.sub_olympiad_grade, 'test', None)
            else:
                test = getattr(result.olympiad, 'test', None)
            
            questions = []
            has_test = False
            if test:
                has_test = True
                for q in test.questions.all().order_by('id'):
                    questions.append({
                        'id': q.id,
                        'text_ru': q.text_ru,
                        'text_uz': q.text_uz,
                        'text_en': q.text_en,
                        'options': q.options,
                        'correct_option': str(q.correct_option) if q.correct_option is not None else None,
                        'image': request.build_absolute_uri(q.image.url) if q.image else None
                    })
            
            # Convert keys in answers to strings for consistency
            user_answers = result.answers_json or {}
            formatted_answers = {str(k): str(v) for k, v in user_answers.items()}
            
            return Response({
                'id': result.id,
                'user_name': f"{result.user.last_name} {result.user.first_name}",
                'answers': formatted_answers,
                'score': result.score,
                'questions': questions,
                'mistakes': result.mistakes or [],
                'has_test': has_test
            })

        # POST method
        if 'mistakes' in request.data:
            new_mistakes = request.data.get('mistakes', [])
            result.mistakes = new_mistakes
            
            # Recalculate score based on mistakes
            total_deducted = 0
            for m in new_mistakes:
                try:
                    total_deducted += int(m.get('minus_points', 0))
                except (ValueError, TypeError):
                    pass
            result.score = max(0, 100 - total_deducted)
            result.save()
            return Response({'success': True, 'score': result.score})

        new_answers = request.data.get('answers')
        if new_answers is None:
            return Response({'error': 'Answers or mistakes are required'}, status=400)
            
        result.answers_json = new_answers
        
        # Recalculate score
        test = None
        if result.sub_olympiad_grade:
            test = getattr(result.sub_olympiad_grade, 'test', None)
        else:
            test = getattr(result.olympiad, 'test', None)
            
        if test:
            questions = test.questions.all()
            if questions.exists():
                correct_count = 0
                for q in questions:
                    user_val = str(new_answers.get(str(q.id))) if new_answers.get(str(q.id)) is not None else None
                    correct_val = str(q.correct_option) if q.correct_option is not None else None
                    if user_val == correct_val:
                        correct_count += 1
                result.score = round((correct_count / questions.count()) * 100)
        
        result.save()
        return Response({'success': True, 'score': result.score})


class SupportTicketViewSet(viewsets.ModelViewSet):
    serializer_class = SupportTicketSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return SupportTicket.objects.all()
        return SupportTicket.objects.filter(user=user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if not request.user.is_staff and instance.user != request.user:
            return Response({'error': 'You cannot delete this ticket'}, status=403)
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def resolve(self, request, pk=None):
        ticket = self.get_object()
        ticket.status = SupportTicket.Status.RESOLVED
        ticket.save()
        return Response({'status': 'Ticket resolved'})

class TicketReplyViewSet(viewsets.ModelViewSet):
    serializer_class = TicketReplySerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        return TicketReply.objects.all()

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
        ticket = serializer.validated_data.get('ticket')
        if ticket:
            ticket.save() # update updated_at

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if not request.user.is_staff and instance.user != request.user:
            return Response({'error': 'You cannot delete this reply'}, status=403)
        return super().destroy(request, *args, **kwargs)


from .utils_eskiz import get_templates, add_template, send_sms, delete_template, get_balance, get_templates_debug, add_template_debug

class SMSTemplateView(APIView):
    permission_classes = (permissions.IsAdminUser,)

    def get(self, request):
        if request.query_params.get('debug') == '1':
            return Response(get_templates_debug())
        if request.query_params.get('debug_add') == '1':
            text = request.query_params.get('text', 'Bu Eskiz dan test')
            return Response(add_template_debug(text))
        if request.query_params.get('debug_env') == '1':
            from .utils_eskiz import ESKIZ_EMAIL
            return Response({"ESKIZ_EMAIL": ESKIZ_EMAIL})
        templates = get_templates()
        return Response(templates)

    def post(self, request):
        text = request.data.get('text')
        name = request.data.get('name', f"Tpl_{timezone.now().timestamp()}")
        if not text:
            return Response({'error': 'Text is required'}, status=400)
        
        result = add_template(name, text)
        return Response(result)

    def delete(self, request):
        template_id = request.query_params.get('id') or request.data.get('id')
        if not template_id:
            return Response({'error': 'Template ID is required'}, status=400)
        
        result = delete_template(template_id)
        if result.get('status') == 'error':
            return Response({'error': result.get('message')}, status=400)
        return Response(result)

class SMSSendView(APIView):
    permission_classes = (permissions.IsAdminUser,)

    def post(self, request):
        user_ids = request.data.get('user_ids', [])
        message = request.data.get('message')
        template_id = request.data.get('template_id')
        allow_resend = request.data.get('allow_resend', False)
        
        if not user_ids or not message:
            return Response({'error': 'Users and message are required'}, status=400)
        
        users = list(User.objects.filter(id__in=user_ids))
        results = []
        
        # 1. Fetch already sent users and phones for this template (if template_id is provided)
        already_sent_user_ids = set()
        already_sent_phones = set()
        if template_id and not allow_resend:
            try:
                already_sent_user_ids = set(
                    SMSSentHistory.objects.filter(template_id=template_id).values_list('user_id', flat=True)
                )
                raw_phones = User.objects.filter(sms_history__template_id=template_id).exclude(phone='').values_list('phone', flat=True)
                already_sent_phones = set(p.strip() for p in raw_phones if p)
            except Exception as e:
                print(f"Error querying SMSSentHistory in SMSSendView: {e}")

        history_to_create = []
        sent_in_this_batch = set()

        for user in users:
            if not user.phone:
                continue
            
            clean_phone = user.phone.strip()
            if not clean_phone:
                continue

            # Skip if user has already received this template in the past
            if not allow_resend and template_id and (user.id in already_sent_user_ids or clean_phone in already_sent_phones):
                results.append({
                    'user_id': user.id,
                    'phone': user.phone,
                    'result': {'status': 'skipped_already_sent', 'message': 'Already sent template to this user or phone'}
                })
                continue

            # If the phone was already processed in this batch:
            if clean_phone in sent_in_this_batch:
                # Skip sending another SMS to prevent duplicates, but still log history for this user
                # so that they are marked as sent.
                if template_id:
                    history_to_create.append(
                        SMSSentHistory(user=user, template_id=template_id)
                    )
                results.append({
                    'user_id': user.id,
                    'phone': user.phone,
                    'result': {'status': 'skipped_duplicate_phone', 'message': 'Duplicate phone number in current batch'}
                })
                continue

            # Send SMS
            res = send_sms(clean_phone, message)
            results.append({
                'user_id': user.id,
                'phone': user.phone,
                'result': res
            })

            if res.get('status') != 'error':
                sent_in_this_batch.add(clean_phone)
                if template_id:
                    history_to_create.append(
                        SMSSentHistory(user=user, template_id=template_id)
                    )

        if history_to_create:
            try:
                SMSSentHistory.objects.bulk_create(history_to_create, ignore_conflicts=True)
            except Exception as e:
                print(f"Error bulk_creating SMSSentHistory: {e}")

        return Response({'results': results})


class SMSSentHistoryView(APIView):
    permission_classes = (permissions.IsAdminUser,)

    def get(self, request):
        template_id = request.query_params.get('template_id')
        if not template_id:
            return Response({'error': 'Template ID is required'}, status=400)
        
        try:
            sent_user_ids = list(SMSSentHistory.objects.filter(template_id=template_id).values_list('user_id', flat=True))
            
            # Get phone numbers of users in sent history
            sent_phones = list(
                User.objects.filter(sms_history__template_id=template_id)
                .exclude(phone='')
                .values_list('phone', flat=True)
            )
            # Clean/trim phones and keep unique values
            sent_phones = list(set(p.strip() for p in sent_phones if p))
        except Exception as e:
            print(f"Error querying SMSSentHistoryView: {e}")
            sent_user_ids = []
            sent_phones = []
        
        return Response({
            'user_ids': sent_user_ids,
            'phones': sent_phones
        })


class SMSBalanceView(APIView):
    permission_classes = (permissions.IsAdminUser,)

    def get(self, request):
        result = get_balance()
        if result.get('status') == 'error':
            return Response({'error': result.get('message')}, status=503)
        return Response({'balance': result['balance']})


class TelegramWebhookView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request, bot_type):
        import requests
        import logging
        logger = logging.getLogger(__name__)

        if bot_type == 'academy':
            bot_token = '8825491984:AAHwzPFiTBtprdU4MRgzzioYHfnv1TRuUig'
        elif bot_type == 'olympiad':
            bot_token = '8698566396:AAHOi3nHbrR9slFoUNQDI34l5kEneTPmspE'
        else:
            return Response({'error': 'Invalid bot type'}, status=400)

        data = request.data
        callback_query = data.get('callback_query')
        if not callback_query:
            return Response({'ok': True, 'message': 'No callback query'})

        callback_query_id = callback_query.get('id')
        message = callback_query.get('message', {})
        chat_id = message.get('chat', {}).get('id')
        message_id = message.get('message_id')
        original_text = message.get('text', '')

        callback_data = callback_query.get('data')

        if callback_data == 'mark_answered' and chat_id and message_id:
            # Escape HTML characters to prevent Telegram parse errors
            escaped_text = original_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            
            if "Javob berildi" not in original_text:
                new_text = f"{escaped_text}\n\n✅ <b>Javob berildi!</b>"
            else:
                new_text = escaped_text

            # Update the message text and remove the inline keyboard
            edit_url = f"https://api.telegram.org/bot{bot_token}/editMessageText"
            edit_res = requests.post(edit_url, json={
                'chat_id': chat_id,
                'message_id': message_id,
                'text': new_text,
                'parse_mode': 'HTML'
            })
            logger.info(f"Telegram editMessageText response: {edit_res.text}")
            
            # Answer the callback query to dismiss loading indicator
            answer_url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
            requests.post(answer_url, json={
                'callback_query_id': callback_query_id,
                'text': 'Ariza javob berildi deb belgilandi! ✅'
            })

            return Response({'ok': True})
            
        return Response({'ok': True})


class EditRequestViewSet(viewsets.ModelViewSet):
    """
    Coordinators create edit requests.
    Admins list, approve, or reject them.
    """
    serializer_class = EditRequestSerializer
    permission_classes = (permissions.IsAuthenticated,)
    http_method_names = ['get', 'post', 'delete', 'head', 'options']

    def destroy(self, request, *args, **kwargs):
        user = request.user
        if user.role not in ['admin', 'superadmin']:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only admins can delete edit requests.")
        return super().destroy(request, *args, **kwargs)

    def get_queryset(self):
        user = self.request.user
        if user.role in ['admin', 'superadmin']:
            status_filter = self.request.query_params.get('status')
            qs = EditRequest.objects.all()
            if status_filter:
                qs = qs.filter(status=status_filter)
            return qs
        # Coordinators see only their own requests
        return EditRequest.objects.filter(coordinator=user)

    def perform_create(self, serializer):
        user = self.request.user
        if user.role not in ['coordinator', 'admin', 'superadmin']:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only coordinators can submit edit requests.")
        serializer.save(coordinator=user)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def approve(self, request, pk=None):
        edit_req = self.get_object()
        if edit_req.status != EditRequest.Status.PENDING:
            return Response(
                {'error': 'This request has already been reviewed.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            if edit_req.target_type == EditRequest.TargetType.USER:
                target = User.objects.get(pk=edit_req.target_id)
                allowed_fields = [
                    'first_name', 'last_name', 'middle_name', 'phone',
                    'school', 'grade', 'birth_date', 'region',
                    'teacher_name', 'teacher_phone', 'teachers'
                ]
                for field, value in edit_req.proposed_changes.items():
                    if field == 'new_password' and value:
                        target.set_password(value)
                        target.password_text = value
                    elif field == 'region':
                        target.region_id = value
                    elif field in allowed_fields:
                        setattr(target, field, value)
                target.save()

            elif edit_req.target_type == EditRequest.TargetType.RESULT:
                target = ExamResult.objects.get(pk=edit_req.target_id)
                allowed_fields = ['score', 'answers_json']
                for field, value in edit_req.proposed_changes.items():
                    if field in allowed_fields:
                        setattr(target, field, value)

                # Recalculate score when answers_json is updated
                if 'answers_json' in edit_req.proposed_changes:
                    test = None
                    if target.sub_olympiad_grade:
                        test = getattr(target.sub_olympiad_grade, 'test', None)
                    else:
                        test = getattr(target.olympiad, 'test', None)
                    if test:
                        questions = test.questions.all()
                        if questions.exists():
                            new_answers = target.answers_json or {}
                            correct_count = sum(
                                1 for q in questions
                                if str(new_answers.get(str(q.id))) == str(q.correct_option)
                            )
                            target.score = round((correct_count / questions.count()) * 100)
                target.save()

            elif edit_req.target_type == EditRequest.TargetType.REGISTRATION:
                if edit_req.target_id == 0:
                    user_id = edit_req.proposed_changes.get('_register_user_id')
                    olympiad_id = edit_req.proposed_changes.get('_register_olympiad_id')
                    payment_status = edit_req.proposed_changes.get('payment_status', 'pending')
                    
                    try:
                        user = User.objects.get(pk=user_id)
                        olympiad = Olympiad.objects.get(pk=olympiad_id)
                        target, created = Registration.objects.get_or_create(
                            user=user,
                            olympiad=olympiad,
                            defaults={'payment_status': payment_status}
                        )
                    except (User.DoesNotExist, Olympiad.DoesNotExist):
                        return Response({'error': 'User or Olympiad not found.'}, status=404)
                else:
                    target = Registration.objects.get(pk=edit_req.target_id)
                    allowed_fields = ['payment_status']
                    for field, value in edit_req.proposed_changes.items():
                        if field in allowed_fields:
                            setattr(target, field, value)
                    target.save()

            else:
                return Response({'error': 'Unknown target type'}, status=400)
        except (User.DoesNotExist, ExamResult.DoesNotExist, Registration.DoesNotExist):
            return Response({'error': 'Target record not found.'}, status=404)

        edit_req.status = EditRequest.Status.APPROVED
        edit_req.reviewed_by = request.user
        edit_req.admin_note = request.data.get('admin_note', '')
        edit_req.save()

        return Response({'success': True, 'status': 'approved'})

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def reject(self, request, pk=None):
        edit_req = self.get_object()
        if edit_req.status != EditRequest.Status.PENDING:
            return Response(
                {'error': 'This request has already been reviewed.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        edit_req.status = EditRequest.Status.REJECTED
        edit_req.reviewed_by = request.user
        edit_req.admin_note = request.data.get('admin_note', '')
        edit_req.save()

        return Response({'success': True, 'status': 'rejected'})


class BookViewSet(viewsets.ModelViewSet):
    queryset = Book.objects.all()
    serializer_class = BookSerializer
    permission_classes = (IsAdminUserOrReadOnly,)
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['book_type', 'is_active']
    search_fields = ['title_uz', 'title_ru', 'title_en', 'description_uz', 'description_ru', 'description_en']

    def get_queryset(self):
        queryset = Book.objects.all()
        user = self.request.user
        is_staff = user and user.is_authenticated and (user.is_staff or user.role in ['admin', 'superadmin'])
        if not is_staff:
            queryset = queryset.filter(is_active=True)
        return queryset


class TelegramUsersListView(APIView):
    permission_classes = (permissions.IsAdminUser,)

    def get(self, request):
        users = User.objects.filter(telegram_chat_id__isnull=False).exclude(telegram_chat_id='')
        serializer = UserSerializer(users, many=True, context={'request': request})
        return Response(serializer.data)


class TelegramBroadcastView(APIView):
    permission_classes = (permissions.IsAdminUser,)
    BOT_TOKEN = "7361972097:AAFOiy-yKvejKL_nG4r9b7ecmj6TzJC655A"

    @classmethod
    def _build_reply_markup(cls, buttons):
        """Lays link buttons out two per row, matching the bot's existing payment-menu style."""
        if not buttons:
            return None
        rows = []
        row = []
        for b in buttons:
            text = (b.get('text') or '').strip()
            url = (b.get('url') or '').strip()
            if not text or not url:
                continue
            row.append({"text": text, "url": url})
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        return {"inline_keyboard": rows} if rows else None

    @classmethod
    def _send_broadcast(cls, chat_ids, message, image_bytes, image_name, reply_markup):
        base_url = f"https://api.telegram.org/bot{cls.BOT_TOKEN}/"
        file_id = None  # reuse Telegram's file_id after the first upload instead of re-uploading bytes per user

        for chat_id in chat_ids:
            try:
                if image_bytes:
                    payload = {"chat_id": chat_id, "parse_mode": "HTML"}
                    if message:
                        payload["caption"] = message
                    if reply_markup:
                        payload["reply_markup"] = json.dumps(reply_markup)

                    if file_id:
                        payload["photo"] = file_id
                        res = requests.post(base_url + "sendPhoto", data=payload, timeout=10)
                    else:
                        files = {"photo": (image_name or "image.jpg", image_bytes)}
                        res = requests.post(base_url + "sendPhoto", data=payload, files=files, timeout=20)
                        result = res.json()
                        photos = result.get("result", {}).get("photo")
                        if photos:
                            file_id = photos[-1]["file_id"]
                else:
                    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
                    if reply_markup:
                        # requests(json=payload) already serializes the whole body to JSON,
                        # so reply_markup must stay a plain dict here — pre-stringifying it
                        # (like the multipart sendPhoto branch above needs) double-encodes it
                        # and Telegram silently drops the keyboard.
                        payload["reply_markup"] = reply_markup
                    requests.post(base_url + "sendMessage", json=payload, timeout=5)
            except Exception:
                pass

    def post(self, request):
        message = request.data.get('message', '').strip()
        image = request.FILES.get('image')

        buttons_raw = request.data.get('buttons')
        buttons = []
        if buttons_raw:
            try:
                buttons = json.loads(buttons_raw) if isinstance(buttons_raw, str) else buttons_raw
            except (TypeError, ValueError):
                buttons = []

        if not message and not image:
            return Response({'error': 'Message or image is required'}, status=400)

        reply_markup = self._build_reply_markup(buttons)

        user_ids_raw = request.data.get('user_ids')
        user_ids = []
        if user_ids_raw:
            try:
                user_ids = json.loads(user_ids_raw) if isinstance(user_ids_raw, str) else user_ids_raw
            except (TypeError, ValueError):
                user_ids = []

        recipients = User.objects.filter(telegram_chat_id__isnull=False).exclude(telegram_chat_id='')
        if user_ids:
            recipients = recipients.filter(id__in=user_ids)
        chat_ids = list(recipients.values_list('telegram_chat_id', flat=True))

        image_bytes = image.read() if image else None
        image_name = image.name if image else None

        # Sending one-by-one to hundreds of users inside the request/response cycle
        # was blowing past the gateway timeout (504). Run it in the background instead
        # and return immediately.
        threading.Thread(
            target=self._send_broadcast,
            args=(chat_ids, message, image_bytes, image_name, reply_markup),
            daemon=True
        ).start()

        return Response({
            'success': True,
            'message': f'Broadcast started for {len(chat_ids)} users. Sending in background.'
        })


class BookOrderViewSet(viewsets.ModelViewSet):
    queryset = BookOrder.objects.all().select_related('user', 'book')
    serializer_class = BookOrderSerializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'user', 'book']

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return BookOrder.objects.none()
        if user.is_staff or user.role in ['admin', 'superadmin']:
            return BookOrder.objects.all().select_related('user', 'book')
        return BookOrder.objects.filter(user=user).select_related('user', 'book')

    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        order = self.get_object()
        new_status = request.data.get('status')
        rejection_reason = request.data.get('rejection_reason', '')

        if not new_status or new_status not in BookOrder.Status.values:
            return Response({'error': 'Invalid status'}, status=400)

        old_status = order.status

        with transaction.atomic():
            # Stock was reserved (decremented) when the order was placed.
            # Releasing it back to stock only when the order newly becomes rejected,
            # and re-reserving it if a rejected order is reverted to another status.
            if new_status == 'rejected' and old_status != 'rejected':
                book = Book.objects.select_for_update().get(id=order.book_id)
                book.stock += order.amount
                book.save(update_fields=['stock'])
            elif old_status == 'rejected' and new_status != 'rejected':
                book = Book.objects.select_for_update().get(id=order.book_id)
                book.stock = max(0, book.stock - order.amount)
                book.save(update_fields=['stock'])

            order.status = new_status
            if new_status == 'rejected' and rejection_reason:
                order.rejection_reason = rejection_reason
            order.save()

        # Send telegram notification
        chat_id = order.user.telegram_chat_id
        if chat_id:
            book_title = order.book.title_ru or order.book.title_uz or order.book.title_en or 'Unknown Book'
            if new_status == BookOrder.Status.ACCEPTED:
                text = (
                    f"✅ <b>To'lovingiz qabul qilindi! / Ваша оплата принята!</b>\n\n"
                    f"📖 Kitob: {book_title}\n"
                    f"🔢 Soni: {order.amount} ta\n"
                    f"📦 Buyurtma holati: To'lov tasdiqlandi. Tez orada kitobingiz yetkazib beriladi.\n\n"
                    f"Статус заказа: Оплата подтверждена. Книга скоро будет доставлена."
                )
            elif new_status == BookOrder.Status.REJECTED:
                reason_str = f"Sababi: {rejection_reason}" if rejection_reason else "Sababi ko'rsatilmadi"
                reason_str_ru = f"Причина: {rejection_reason}" if rejection_reason else "Причина не указана"
                text = (
                    f"❌ <b>Buyurtmangiz rad etildi / Ваш заказ отклонен.</b>\n\n"
                    f"📖 Kitob: {book_title}\n"
                    f"⚠️ {reason_str}\n"
                    f"⚠️ {reason_str_ru}"
                )
            elif new_status == BookOrder.Status.DELIVERING:
                text = (
                    f"🚚 <b>Kitobingiz yo'lga chiqdi! / Ваша книга в пути!</b>\n\n"
                    f"📖 Kitob: {book_title}\n"
                    f"📦 Buyurtma holati: Yetkazib berish boshlandi.\n\n"
                    f"Статус заказа: Книга отправлена и находится в пути."
                )
            elif new_status == BookOrder.Status.DELIVERED:
                text = (
                    f"🎉 <b>Kitob muvaffaqiyatli etkazib berildi! / Книга успешно доставлена!</b>\n\n"
                    f"📖 Kitob: {book_title}\n"
                    f"Rahmat, bizni tanlaganingiz uchun! / Спасибо, что выбрали нас!"
                )
            else:
                text = f"📦 Buyurtma holati o'zgardi: {new_status} / Статус заказа изменен: {new_status}"

            BOT_TOKEN = "7361972097:AAFOiy-yKvejKL_nG4r9b7ecmj6TzJC655A"
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML"
            }
            try:
                requests.post(url, json=payload, timeout=5)
            except Exception:
                pass

        return Response({'success': True, 'status': order.status})


def _log_visa_action(applicant, actor, action, detail=''):
    VisaAuditLog.objects.create(applicant=applicant, actor=actor if actor and actor.is_authenticated else None, action=action, detail=detail[:500])


class VisaApplicantViewSet(viewsets.ModelViewSet):
    queryset = VisaApplicant.objects.all().select_related('assigned_to', 'olympiad', 'created_by', 'family_head').prefetch_related('documents', 'notes', 'tasks', 'audit_logs')
    permission_classes = (IsAdminOrCoordinator,)
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'country', 'assigned_to', 'olympiad']
    search_fields = ['first_name', 'last_name', 'middle_name', 'phone', 'passport_number', 'email']
    ordering_fields = ['created_at', 'updated_at', 'embassy_appointment_date']

    def get_serializer_class(self):
        if self.action == 'list':
            return VisaApplicantListSerializer
        return VisaApplicantDetailSerializer

    def perform_create(self, serializer):
        applicant = serializer.save(created_by=self.request.user)
        _log_visa_action(applicant, self.request.user, VisaAuditLog.Action.CREATED)

    def perform_update(self, serializer):
        old_status = serializer.instance.status
        applicant = serializer.save()
        if applicant.status != old_status:
            _log_visa_action(applicant, self.request.user, VisaAuditLog.Action.STATUS_CHANGED,
                              f"{old_status} -> {applicant.status}")
        else:
            _log_visa_action(applicant, self.request.user, VisaAuditLog.Action.UPDATED)

    @action(detail=False, methods=['post'])
    def bulk_update_status(self, request):
        ids = request.data.get('ids', [])
        new_status = request.data.get('status')
        if not ids or new_status not in VisaApplicant.Status.values:
            return Response({'detail': 'ids and a valid status are required'}, status=status.HTTP_400_BAD_REQUEST)
        applicants = VisaApplicant.objects.filter(id__in=ids)
        count = 0
        for applicant in applicants:
            old_status = applicant.status
            applicant.status = new_status
            applicant.save(update_fields=['status', 'updated_at'])
            _log_visa_action(applicant, request.user, VisaAuditLog.Action.STATUS_CHANGED, f"{old_status} -> {new_status}")
            count += 1
        return Response({'updated': count})

    @action(detail=False, methods=['post'])
    def bulk_assign(self, request):
        ids = request.data.get('ids', [])
        assigned_to_id = request.data.get('assigned_to')
        if not ids:
            return Response({'detail': 'ids is required'}, status=status.HTTP_400_BAD_REQUEST)
        count = VisaApplicant.objects.filter(id__in=ids).update(assigned_to_id=assigned_to_id or None)
        for applicant in VisaApplicant.objects.filter(id__in=ids):
            _log_visa_action(applicant, request.user, VisaAuditLog.Action.UPDATED, "Reassigned")
        return Response({'updated': count})

    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        rows = request.data.get('rows', [])
        created, errors = [], []
        for idx, row in enumerate(rows):
            serializer = VisaApplicantDetailSerializer(data=row, context={'request': request})
            if serializer.is_valid():
                applicant = serializer.save(created_by=request.user)
                _log_visa_action(applicant, request.user, VisaAuditLog.Action.CREATED, "Imported from Excel")
                created.append(applicant.id)
            else:
                errors.append({'row': idx, 'errors': serializer.errors})
        return Response({'created': created, 'errors': errors})


class VisaDocumentViewSet(viewsets.ModelViewSet):
    queryset = VisaDocument.objects.all().select_related('uploaded_by')
    serializer_class = VisaDocumentSerializer
    permission_classes = (IsAdminOrCoordinator,)
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['applicant', 'category', 'needs_replacement']

    def perform_create(self, serializer):
        applicant = serializer.validated_data.get('applicant')
        category = serializer.validated_data.get('category')
        previous = VisaDocument.objects.filter(applicant=applicant, category=category, superseded=False).first()
        document = serializer.save(uploaded_by=self.request.user, previous_version=previous)
        if previous:
            previous.superseded = True
            previous.save(update_fields=['superseded'])
        _log_visa_action(applicant, self.request.user, VisaAuditLog.Action.DOCUMENT_UPLOADED, document.get_category_display())

    def perform_destroy(self, instance):
        _log_visa_action(instance.applicant, self.request.user, VisaAuditLog.Action.DOCUMENT_DELETED, instance.get_category_display())
        instance.delete()

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        document = self.get_object()
        if not document.file:
            raise Http404
        return FileResponse(document.file.open('rb'), as_attachment=True, filename=document.file.name.split('/')[-1])


class VisaNoteViewSet(viewsets.ModelViewSet):
    queryset = VisaNote.objects.all().select_related('author')
    serializer_class = VisaNoteSerializer
    permission_classes = (IsAdminOrCoordinator,)
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['applicant']

    def perform_create(self, serializer):
        note = serializer.save(author=self.request.user)
        _log_visa_action(note.applicant, self.request.user, VisaAuditLog.Action.NOTE_ADDED, note.text[:200])


class VisaTaskViewSet(viewsets.ModelViewSet):
    queryset = VisaTask.objects.all().select_related('assigned_to')
    serializer_class = VisaTaskSerializer
    permission_classes = (IsAdminOrCoordinator,)
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['applicant', 'done']

    def perform_update(self, serializer):
        task = serializer.save()
        if task.done:
            _log_visa_action(task.applicant, self.request.user, VisaAuditLog.Action.TASK_DONE, task.title)


class VisaAuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = VisaAuditLog.objects.all().select_related('actor')
    serializer_class = VisaAuditLogSerializer
    permission_classes = (IsAdminOrCoordinator,)
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['applicant']


