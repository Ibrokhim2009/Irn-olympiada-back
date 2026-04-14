import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'src.settings')
django.setup()

from core.models import Olympiad, SubOlympiad
from core.serializers import OlympiadSerializer
from django.utils import timezone
from datetime import timedelta

def test_serializer_calculation():
    now = timezone.now()
    data = {
        'title_ru': 'Test Multi Olympiad',
        'olympiad_type': 'online',
        'price': 1000,
        'subs': [
            {'title_ru': 'Sub 1', 'start_datetime': (now + timedelta(days=2)).isoformat(), 'duration_minutes': 30},
            {'title_ru': 'Sub 2', 'start_datetime': (now + timedelta(days=1)).isoformat(), 'duration_minutes': 45},
        ]
    }
    
    serializer = OlympiadSerializer(data=data)
    if serializer.is_valid():
        oly = serializer.save()
        print(f"Olympiad saved. ID: {oly.id}")
        print(f"Calculated start_datetime: {oly.start_datetime}")
        print(f"Calculated duration_minutes: {oly.duration_minutes}")
        
        # Verify min date
        expected_date = now + timedelta(days=1)
        # Compare approximate (ignoring micros)
        if oly.start_datetime.date() == expected_date.date():
            print("✅ Start date calculation correct (earliest chosen).")
        else:
            print(f"❌ Start date mismatch. Got {oly.start_datetime}, expected around {expected_date}")
            
        if oly.duration_minutes == 75:
            print("✅ Duration sum correct.")
        else:
            print(f"❌ Duration mismatch. Got {oly.duration_minutes}, expected 75")
            
        # Cleanup
        oly.delete()
    else:
        print(f"❌ Serializer invalid: {serializer.errors}")

if __name__ == "__main__":
    test_serializer_calculation()
