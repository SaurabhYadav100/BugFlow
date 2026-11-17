from pathlib import Path

from django.core.management.base import BaseCommand

from core import exports


class Command(BaseCommand):
    help = "Write users.csv, projects.csv, issues.csv and workflow_states.csv into a folder."

    def add_arguments(self, parser):
        parser.add_argument("--out", default="exports", help="Output folder (default: ./exports)")

    def handle(self, *args, **opts):
        out = Path(opts["out"])
        out.mkdir(parents=True, exist_ok=True)
        for table, (filename, _) in exports.TABLES.items():
            (out / filename).write_bytes(exports.csv_bytes(table))
            self.stdout.write(f"wrote {out / filename}")
        self.stdout.write(self.style.SUCCESS(f"Done. Files are in {out.resolve()}"))
