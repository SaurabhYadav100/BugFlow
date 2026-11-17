from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.csvio import parse_date, read_rows
from projects.models import Project


class Command(BaseCommand):
    help = ("Create projects from data/projects.csv (columns: Name, Description, Project Manager, Created Date). "
            "Run load_users first. Existing projects are skipped unless you pass --update.")

    def add_arguments(self, parser):
        parser.add_argument("--file", default=str(Path(settings.BASE_DIR) / "data" / "projects.csv"))
        parser.add_argument("--update", action="store_true",
                            help="Also update description, project manager and created date of existing projects (matched by name).")

    def handle(self, *args, **opts):
        rows = read_rows(opts["file"], ["Name"])
        managers = {u.name.lower(): u for u in get_user_model().objects.filter(role="project_manager")}
        for n, r in enumerate(rows, start=2):
            try:
                parse_date(r.get("Created Date", ""))
            except ValueError as exc:
                raise CommandError(f"Line {n}: {exc}")

        created = updated = unchanged = 0
        with transaction.atomic():
            for r in rows:
                manager_name = r.get("Project Manager", "")
                manager = managers.get(manager_name.lower()) if manager_name else None
                if manager_name and not manager:
                    self.stdout.write(self.style.WARNING(f"'{r['Name']}': no Project Manager named '{manager_name}' - manager left as is."))
                made = parse_date(r.get("Created Date", ""))
                project = Project.objects.filter(name=r["Name"]).first()

                if project is None:
                    project = Project.objects.create(name=r["Name"], description=r.get("Description", ""), manager=manager)
                    if made:
                        Project.objects.filter(pk=project.pk).update(created_at=made)
                    created += 1
                    continue

                wanted = {"description": r.get("Description", "")}
                if manager:
                    wanted["manager"] = manager
                changed = [f for f, v in wanted.items() if getattr(project, f) != v]
                date_changed = bool(made and project.created_at != made)
                if opts["update"] and (changed or date_changed):
                    for f in changed:
                        setattr(project, f, wanted[f])
                    if changed:
                        project.save(update_fields=changed)
                    if date_changed:
                        Project.objects.filter(pk=project.pk).update(created_at=made)  # auto_now_add needs a queryset update
                    updated += 1
                else:
                    unchanged += 1
        self.stdout.write(self.style.SUCCESS(f"Projects: {created} created, {updated} updated, {unchanged} unchanged."))
        if unchanged and not opts["update"]:
            self.stdout.write("Tip: edited an existing project in the CSV? Run again with --update to apply it (the name is the key, so don't change it).")
