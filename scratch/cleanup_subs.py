import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'src.settings')
django.setup()

from core.models import SubOlympiad
from django.db.models import Count

def cleanup_duplicates():
    # Find combinations of olympiad, title, and start date that appear more than once
    duplicates = SubOlympiad.objects.values('olympiad', 'title_ru', 'start_datetime').annotate(
        count=Count('id')
    ).filter(count__gt=1)
    
    deleted_total = 0
    for dup in duplicates:
        # Get all records for this combination
        subs = SubOlympiad.objects.filter(
            olympiad=dup['olympiad'],
            title_ru=dup['title_ru'],
            start_datetime=dup['start_datetime']
        ).order_by('id')
        
        # Keep the first one, delete the rest
        to_delete = subs[1:]
        count = to_delete.count()
        to_delete.delete()
        deleted_total += count
        print(f"Deleted {count} duplicates for subject '{dup['title_ru']}' in olympiad {dup['olympiad']}")

    print(f"Total deleted: {deleted_total}")

if __name__ == "__main__":
    cleanup_duplicates()
