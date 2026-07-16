from django.core.management.base import BaseCommand
from core.models import Olympiad
from core.serializers import OlympiadSerializer


class Command(BaseCommand):
    help = (
        "Recomputes the `grades` field for every olympiad from its current "
        "grade sessions. Fixes olympiads left with grades=[] (open to every "
        "user's grade) because their grade sessions were previously dropped "
        "on save whenever no date was set yet."
    )

    def handle(self, *args, **options):
        serializer = OlympiadSerializer()
        fixed = 0
        for olympiad in Olympiad.objects.all():
            before = list(olympiad.grades or [])
            serializer._sync_olympiad_data(olympiad)
            olympiad.refresh_from_db(fields=['grades'])
            after = list(olympiad.grades or [])
            if before != after:
                fixed += 1
                self.stdout.write(self.style.SUCCESS(
                    f"Olympiad #{olympiad.id} ({olympiad.title_ru}): grades {before} -> {after}"
                ))

        if fixed == 0:
            self.stdout.write(self.style.SUCCESS("All olympiads already had correct grades."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Fixed {fixed} olympiad(s)."))
