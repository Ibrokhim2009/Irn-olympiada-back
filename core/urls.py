from django.urls import path, include, re_path
from rest_framework.routers import DefaultRouter
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from .views import (
    OlympiadViewSet, SubOlympiadViewSet, RegisterForOlympiadView, 
    ExamView, SubmitResultView, ResultAnalysisView, PersonalResultsListView,
    RegisterView,LoginView,UserProfileView,
    TestViewSet, QuestionViewSet, UserViewSet,
    RegistrationViewSet, PaymeCallbackView, ClickCallbackView, GetPaymeLinkView,
    NotificationViewSet, SeedNotificationsView, SendNotificationView, AdminStatsView, RegionViewSet
)

schema_view = get_schema_view(
   openapi.Info(
      title="IRN Olympiad API",
      default_version='v1',
      description="Документация для проекта IRN Olympiad",
      contact=openapi.Contact(email="contact@irn.uz"),
   ),
   public=True,
   permission_classes=(permissions.AllowAny,),
)

router = DefaultRouter()
router.register(r'olympiads', OlympiadViewSet)
router.register(r'subs', SubOlympiadViewSet)
router.register(r'tests', TestViewSet)
router.register(r'questions', QuestionViewSet)
router.register(r'users', UserViewSet, basename='users_list')
router.register(r'registrations', RegistrationViewSet, basename='user_registrations')
router.register(r'notifications', NotificationViewSet, basename='notifications')
router.register(r'regions', RegionViewSet, basename='regions')

urlpatterns = [
    path('auth/register/', RegisterView.as_view(), name='register'),
    path('auth/login/', LoginView.as_view(), name='login_custom'),
    path('auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/profile/', UserProfileView.as_view(), name='profile'),
    
    path('notifications/seed/', SeedNotificationsView.as_view(), name='notifications-seed'),
    path('notifications/send/', SendNotificationView.as_view(), name='notifications-send'),
    path('admin/stats/', AdminStatsView.as_view(), name='admin-stats'),

    path('', include(router.urls)),
    path('olympiads/<int:pk>/register/', RegisterForOlympiadView.as_view(), name='olympiad-register'),
    path('exams/<int:sub_olympiad_id>/questions/', ExamView.as_view(), name='exam-questions'),
    path('exams/<int:sub_olympiad_id>/submit/', SubmitResultView.as_view(), name='exam-submit'),
    path('exams/<int:olympiad_id>/analysis/', ResultAnalysisView.as_view(), name='exam-analysis'),
    path('exams/personal-results/', PersonalResultsListView.as_view(), name='personal-results'),

    path('payments/payme/', PaymeCallbackView.as_view(), name='payme-callback'),
    path('payments/click/', ClickCallbackView.as_view(), name='click-callback'),
    path('payments/payme/get-link/<int:registration_id>/', GetPaymeLinkView.as_view(), name='get-payme-link'),

    re_path(r'^docs(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('docs/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
]
