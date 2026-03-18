import os
import django
import random
from django.utils import timezone
from datetime import timedelta

# Настройка окружения Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'src.settings')
django.setup()

from core.models import User, Olympiad, Registration, Region

def seed():
    print("Начинаю загрузку участников для аналитики...")
    
    # 1. Получаем регионы
    regions = list(Region.objects.all())
    if not regions:
        print("Ошибка: Регионы не найдены.")
        return

    # 2. Олимпиады
    olympiads = list(Olympiad.objects.all())
    if not olympiads:
        print("Ошибка: Олимпиады не найдены.")
        return

    grades = ["5", "6", "7", "8", "9", "10", "11", "11+"]

    # Создаем 30 участников
    for i in range(30):
        username = f"user_{i}_{random.randint(1000, 9999)}@example.com"
        first_names = ["Иван", "Азиз", "Дилшод", "Мария", "Елена", "Ботир", "Сардор", "Нигора"]
        last_names = ["Петров", "Каримов", "Абдуллаев", "Иванова", "Ташпулатова", "Юсупов", "Рахимов"]
        
        region = random.choice(regions)
        grade = random.choice(grades)
        
        user = User.objects.create_user(
            username=username,
            password="password123",
            first_name=random.choice(first_names),
            last_name=random.choice(last_names),
            phone=f"+99890{random.randint(100, 999)}{random.randint(10, 99)}{random.randint(10, 99)}",
            region=region,
            school=f"Школа №{random.randint(1, 200)}",
            grade=grade,
            role=User.Role.PARTICIPANT
        )
        
        # Регистрация на 1-2 случайные олимпиады
        for oly in random.sample(olympiads, k=random.randint(1, 2)):
            status = random.choice(['paid', 'pending', 'pending', 'paid'])
            if oly.is_free:
                status = 'free'
                
            Registration.objects.get_or_create(
                user=user,
                olympiad=oly,
                defaults={
                    "payment_status": status,
                    "price": oly.price,
                    "teacher_name": f"Учитель {random.choice(last_names)}",
                    "teacher_phone": f"+99891{random.randint(100, 999)}0000"
                }
            )
            
    print(f"Успешно создано 30 участников с регистрациями.")

if __name__ == "__main__":
    seed()
