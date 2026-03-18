import os
import django
import random
from django.utils import timezone
from datetime import timedelta

# Настройка окружения Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'src.settings')
django.setup()

from core.models import Olympiad, Test, Question, Region

def seed():
    print("Начинаю загрузку данных олимпиад...")
    
    # 1. Получаем все ID регионов для заполнения region_ids
    all_region_ids = list(Region.objects.values_list('id', flat=True))
    if not all_region_ids:
        print("Ошибка: Регионы не найдены в базе. Пожалуйста, сначала выполните миграции и сидирование регионов.")
        return

    # Данные для олимпиад
    olympiads_data = [
        {
            "title_uz": "Matematika bo'yicha Respublika olimpiadasi",
            "title_ru": "Республиканская олимпиада по математике",
            "title_en": "National Mathematics Olympiad",
            "type": "offline",
            "price": 50000,
            "is_free": False,
            "grades": ["5", "6", "7", "8", "9", "10", "11"],
            "max": 500
        },
        {
            "title_uz": "Ingliz tili - Global Speaker",
            "title_ru": "Английский язык - Global Speaker",
            "title_en": "English Language - Global Speaker",
            "type": "online",
            "price": 0,
            "is_free": True,
            "grades": ["3", "4", "5", "6"],
            "max": 1000
        },
        {
            "title_uz": "Informatika va IT-ga kirish",
            "title_ru": "Информатика и введение в IT",
            "title_en": "Computer Science and Intro to IT",
            "type": "online",
            "price": 35000,
            "is_free": False,
            "grades": ["9", "10", "11", "11+"],
            "max": 300
        },
        {
            "title_uz": "O'zbekiston tarixi bilimlari",
            "title_ru": "Знатоки истории Узбекистана",
            "title_en": "Experts of Uzbekistan History",
            "type": "offline",
            "price": 45000,
            "is_free": False,
            "grades": ["6", "7", "8", "9"],
            "max": 200
        },
        {
            "title_uz": "Yosh Fiziklar tanlovi",
            "title_ru": "Конкурс Юных Физиков",
            "title_en": "Young Physicists Contest",
            "type": "offline",
            "price": 0,
            "is_free": True,
            "grades": ["10", "11", "11+"],
            "max": 150
        }
    ]

    for data in olympiads_data:
        # Создаем олимпиаду
        oly, created = Olympiad.objects.get_or_create(
            title_ru=data["title_ru"],
            defaults={
                "title_uz": data["title_uz"],
                "title_en": data["title_en"],
                "olympiad_type": data["type"],
                "price": data["price"],
                "is_free": data["is_free"],
                "start_datetime": timezone.now() + timedelta(days=random.randint(5, 30)),
                "duration_minutes": random.choice([60, 90, 120]),
                "max_participants": data["max"],
                "grades": data["grades"],
                "region_ids": all_region_ids, # Доступна во всех регионах
                "is_active": True
            }
        )
        
        if created:
            print(f"Добавлена олимпиада: {oly.title_ru}")
            
            # Создаем тест для олимпиады
            test = Test.objects.create(
                olympiad=oly,
                title=f"Тест: {oly.title_ru}"
            )
            
            # Добавляем 5 вопросов к тесту
            for i in range(1, 6):
                Question.objects.create(
                    test=test,
                    text_ru=f"Вопрос №{i} по предмету {oly.title_ru}?",
                    text_uz=f"{oly.title_uz} bo'yicha {i}-savol?",
                    text_en=f"Question #{i} about {oly.title_en}?",
                    options=[
                        {"id": "A", "text": f"Вариант A для вопроса {i}"},
                        {"id": "B", "text": f"Вариант B для вопроса {i}"},
                        {"id": "C", "text": f"Вариант C для вопроса {i}"},
                        {"id": "D", "text": f"Вариант D для вопроса {i}"},
                    ],
                    correct_option=random.choice(["A", "B", "C", "D"])
                )
            print(f"  К олимпиаде '{oly.title_ru}' добавлено 5 вопросов.")
        else:
            print(f"Олимпиада '{oly.title_ru}' уже существует.")

    print("\nЗагрузка данных завершена успешно!")

if __name__ == "__main__":
    seed()
