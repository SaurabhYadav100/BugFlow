from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Load users, projects and issues from the CSV files in the data folder, in the right order. Safe to re-run."

    def add_arguments(self, parser):
        parser.add_argument("--dir", default=str(Path(settings.BASE_DIR) / "data"), help="Folder with the CSV files.")
        parser.add_argument("--update", action="store_true", help="Also apply edits in the CSVs to existing users, projects and issues (matched by email / name / project+title).")
        parser.add_argument("--password", default="Password@123")
        parser.add_argument("--admin-password", default="Admin@123")

    def handle(self, *args, **opts):
        d = Path(opts["dir"])
        call_command("load_users", file=str(d / "users.csv"), update=opts["update"], password=opts["password"],
                     admin_password=opts["admin_password"], stdout=self.stdout)
        call_command("load_projects", file=str(d / "projects.csv"), update=opts["update"], stdout=self.stdout)
        call_command("load_dataset", file=str(d / "issues_dataset.csv"), update=opts["update"], stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS("All data loaded."))
