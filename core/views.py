from rest_framework import generics, status, permissions, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.utils import timezone
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from rest_framework import response, filters
from rest_framework.permissions import AllowAny
from payme import Payme
from payme.views import PaymeWebHookAPIView
from payme.exceptions.webhook import AccountDoesNotExist, TransactionAlreadyExists
from payme.models import PaymeTransactions
from payme.types import response as payme_response
from payme.util import time_to_payme

from .serializers import (
    RegisterSerializer, UserSerializer, LoginRequestSerializer,
    OlympiadSerializer, QuestionSerializer, RegistrationSerializer,
    TestSerializer
)
from .models import User, Olympiad, Registration, ExamResult, Test, Question
from .permissions import IsAdminUserOrReadOnly
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.pagination import PageNumberPagination
from .utils_payme import get_payme_link


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

        user = authenticate(username=username_input, password=password)

        if not user:
            try:
                found_user = User.objects.get(email=username_input)
                if found_user.check_password(password):
                    user = found_user
            except User.DoesNotExist:
                pass

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
        return Registration.objects.filter(user=self.request.user).order_by('-registered_at')


class GetPaymeLinkView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, registration_id):
        registration = generics.get_object_or_404(Registration, id=registration_id, user=request.user)
        if registration.payment_status in ['paid', 'free']:
            return Response({'error': 'Already paid'}, status=status.HTTP_400_BAD_REQUEST)
        link = get_payme_link(registration.id, registration.price)
        return Response({'link': link})


class PaymeCallbackView(PaymeWebHookAPIView):
    permission_classes = [AllowAny]

    def handle_pre_payment(self, params, result, *args, **kwargs):
        """
        CheckPerformTransaction muvaffaqiyatli o'tgandan keyin chaqiriladi.
        Faqat account mavjudligi va holati tekshiriladi.
        """
        account = params.get('account', {})
        reg_id = account.get('registration_id')

        try:
            registration = Registration.objects.get(id=reg_id)
        except Registration.DoesNotExist:
            raise AccountDoesNotExist()

        if registration.payment_status in ['paid', 'free']:
            raise TransactionAlreadyExists()

    def handle_successfully_payment(self, params, result, *args, **kwargs):
        reg_id = params.get('account', {}).get('registration_id')

        if not reg_id:
            try:
                trans = PaymeTransactions.objects.get(
                    transaction_id=params.get('id')
                )
                reg_id = trans.account_id
            except Exception:
                pass

        try:
            registration = Registration.objects.get(id=reg_id)
            registration.payment_status = Registration.PaymentStatus.PAID
            registration.save()
            print(f"Registration {reg_id} marked as PAID")
        except Registration.DoesNotExist:
            print(f"Registration {reg_id} not found")


class ClickCallbackView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        return Response({"result": "not_implemented_yet"})


class OlympiadViewSet(viewsets.ModelViewSet):
    queryset = Olympiad.objects.all()
    serializer_class = OlympiadSerializer
    permission_classes = (IsAdminUserOrReadOnly,)

    def get_queryset(self):
        if self.request.user.is_authenticated and self.request.user.role in ['admin', 'superadmin']:
            return Olympiad.objects.all()
        return Olympiad.objects.filter(is_active=True)


class RegisterForOlympiadView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @swagger_auto_schema(
        responses={201: RegistrationSerializer, 400: 'Ошибка (нет мест и т.д.)'}
    )
    def post(self, request, pk):
        olympiad = generics.get_object_or_404(Olympiad, pk=pk)

        reg_count = olympiad.registrations.filter(payment_status__in=['paid', 'free']).count()
        if reg_count >= olympiad.max_participants:
            return Response({'error': 'Мест больше нет'}, status=status.HTTP_400_BAD_REQUEST)

        if olympiad.is_free or olympiad.price == 0:
            initial_status = Registration.PaymentStatus.FREE
            deadline = None
        else:
            initial_status = Registration.PaymentStatus.PENDING
            deadline = timezone.now() + timezone.timedelta(minutes=15)

        registration, created = Registration.objects.get_or_create(
            user=request.user,
            olympiad=olympiad,
            defaults={
                'payment_status': initial_status,
                'price': olympiad.price,
                'payment_deadline': deadline
            }
        )
        if not created:
            return Response({'error': 'Вы уже зарегистрированы'}, status=status.HTTP_400_BAD_REQUEST)

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
        return Response({'success': True, 'score': score})