import os
import django

# Настройка окружения Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'src.settings')
django.setup()

from core.models import Region

def seed():
    print("Начинаю загрузку регионов...")
    regions = [
        {"name_uz": "Toshkent shahri", "name_ru": "г. Ташкент", "name_en": "Tashkent City"},
        {"name_uz": "Toshkent viloyati", "name_ru": "Ташкентская область", "name_en": "Tashkent Region"},
        {"name_uz": "Andijon viloyati", "name_ru": "Андижанская область", "name_en": "Andijan Region"},
        {"name_uz": "Buxoro viloyati", "name_ru": "Бухарская область", "name_en": "Bukhara Region"},
        {"name_uz": "Farg'ona viloyati", "name_ru": "Ферганская область", "name_en": "Fergana Region"},
        {"name_uz": "Jizzax viloyati", "name_ru": "Джизакская область", "name_en": "Jizzakh Region"},
        {"name_uz": "Namangan viloyati", "name_ru": "Наманганская область", "name_en": "Namangan Region"},
        {"name_uz": "Navoiy viloyati", "name_ru": "Навоийская область", "name_en": "Navoi Region"},
        {"name_uz": "Qashqadaryo viloyati", "name_ru": "Кашкадарьинская область", "name_en": "Kashkadarya Region"},
        {"name_uz": "Samarqand viloyati", "name_ru": "Самаркандская область", "name_en": "Samarkand Region"},
        {"name_uz": "Sirdaryo viloyati", "name_ru": "Сырдарьинская область", "name_en": "Syrdarya Region"},
        {"name_uz": "Surxondaryo viloyati", "name_ru": "Сурхандарьинская область", "name_en": "Surkhandarya Region"},
        {"name_uz": "Xorazm viloyati", "name_ru": "Хорезмская область", "name_en": "Khorezm Region"},
        {"name_uz": "Qoraqalpog'iston Respublikasi", "name_ru": "Респ. Каракалпакстан", "name_en": "Rep. Karakalpakstan"},
    ]

    for reg_data in regions:
        region, created = Region.objects.get_or_create(
            name_ru=reg_data["name_ru"],
            defaults={
                "name_uz": reg_data["name_uz"],
                "name_en": reg_data["name_en"],
            }
        )
        if created:
            print(f"Добавлен регион: {region.name_ru}")
        else:
            print(f"Регион '{region.name_ru}' уже существует.")

    print("\nЗагрузка регионов завершена!")

if __name__ == "__main__":
    seed()
