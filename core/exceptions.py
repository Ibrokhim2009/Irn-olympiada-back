from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
import logging

logger = logging.getLogger(__name__)

def custom_exception_handler(exc, context):
    # Сначала получаем стандартный ответ DRF
    response = exception_handler(exc, context)

    # Если DRF не смог обработать исключение (например, 500 ошибка)
    if response is None:
        logger.error(f"Unhandled Exception: {exc}", exc_info=True)
        return Response({
            'error': 'Внутренняя ошибка сервера',
            'detail': str(exc) if hasattr(exc, 'message') else 'Произошла непредвиденная ошибка на стороне сервера.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Приводим все ошибки к единому формату: { "error": "сообщение", "fields": { ... } }
    custom_data = {
        'error': 'Ошибка валидации или запроса',
        'fields': response.data if isinstance(response.data, dict) else {'detail': response.data}
    }

    # Если в ответе есть 'detail', выносим его в основной месседж
    if isinstance(response.data, dict) and 'detail' in response.data:
        custom_data['error'] = response.data['detail']

    response.data = custom_data
    return response
