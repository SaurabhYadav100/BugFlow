import csv
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from issues.models import Issue
from projects.models import Project

REQUIRED = ["project", "title", "type", "priority", "severity", "status", "description", "resolution_notes"]


class Command(BaseCommand):
    help = ("Load the issue dataset (default: data/issues_dataset.csv) into the database. Safe to run twice. "
            "Use --update to push edited descriptions and resolution notes into issues that already exist.")

    def add_arguments(self, parser):
        parser.add_argument("--file", default=str(Path(settings.BASE_DIR) / "data" / "issues_dataset.csv"))
        parser.add_argument("--update", action="store_true",
                            help="Also update the description and resolution notes of existing issues (matched by project + title).")

    def handle(self, *args, **opts):
        path = Path(opts["file"])
        if not path.exists():
            raise CommandError(f"File not found: {path}")
        User = get_user_model()
        devs = list(User.objects.filter(role="developer", is_active=True).order_by("pk"))
        testers = list(User.objects.filter(role="tester", is_active=True).order_by("pk")) or list(
            User.objects.filter(is_active=True).order_by("pk")[:1])
        if not devs or not testers:
            raise CommandError("No developers/testers found. Run 'python manage.py load_users' first (or 'python manage.py load_data' to load everything).")

        with path.open(newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        if not rows or any(c not in rows[0] for c in REQUIRED):
            raise CommandError(f"The CSV must have these columns: {', '.join(REQUIRED)}")

        valid = {
            "type": {v for v, _ in Issue.IssueType.choices}, "status": {v for v, _ in Issue.Status.choices},
            "priority": {v for v, _ in Issue.Priority.choices}, "severity": {v for v, _ in Issue.Priority.choices},
        }
        for n, r in enumerate(rows, start=2):  # line 1 is the header
            for col, allowed in valid.items():
                if r[col] not in allowed:
                    raise CommandError(f"Line {n}: '{r[col]}' is not a valid {col} (use one of {sorted(allowed)}).")
            if not r["title"].strip() or not r["project"].strip():
                raise CommandError(f"Line {n}: project and title are required.")

        now, total, created, updated, skipped = timezone.now(), len(rows), 0, 0, 0
        with transaction.atomic():
            projects = {}
            for i, r in enumerate(rows):
                name = r["project"].strip()
                if name not in projects:
                    projects[name], _ = Project.objects.get_or_create(name=name)
                project = projects[name]
                existing = Issue.objects.filter(project=project, title=r["title"].strip()).first()
                if existing:
                    changed = [f for f, new in (("description", r["description"]), ("resolution_notes", r["resolution_notes"]))
                               if getattr(existing, f) != new]
                    if opts["update"] and changed:
                        for f in changed:
                            setattr(existing, f, r["description" if f == "description" else "resolution_notes"])
                        existing.save(update_fields=changed + ["updated_at"])
                        existing.log(None, "Updated " + " and ".join(c.replace("_", " ") for c in changed) + " from dataset")
                        updated += 1
                    else:
                        skipped += 1
                    continue
                issue = Issue.objects.create(
                    project=project, title=r["title"].strip(), description=r["description"], issue_type=r["type"],
                    priority=r["priority"], severity=r["severity"], status=r["status"],
                    resolution_notes=r["resolution_notes"], assignee=devs[i % len(devs)], reporter=testers[i % len(testers)],
                )
                # spread the issues over the last ~200 days, oldest first, so keys and dates read naturally
                made = now - timedelta(days=(total - 1 - i) * 2, hours=i % 7)
                fields = {"created_at": made}
                if r["status"] in ("resolved", "closed"):
                    fields["resolved_at"] = made + timedelta(days=1 + i % 5)
                Issue.objects.filter(pk=issue.pk).update(**fields)
                issue.log(issue.reporter, "Issue created")
                issue.log(issue.reporter, f"Assigned to {issue.assignee.name}")
                if r["status"] != "open":
                    issue.log(issue.assignee, f"Status changed from Open to {issue.get_status_display()}")
                created += 1
        self.stdout.write(self.style.SUCCESS(
            f"Loaded {created} issue(s); updated {updated}; skipped {skipped} that already existed."))
        if skipped and not opts["update"]:
            self.stdout.write("Tip: changed a description or resolution note in the CSV? Run again with --update to apply it.")
