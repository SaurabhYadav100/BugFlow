from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.csvio import parse_date, read_rows

User = get_user_model()


def norm(text):
    return text.strip().lower().replace("_", " ")


class Command(BaseCommand):
    help = ("Create users from data/users.csv (columns: Name, Email, Role, Active, Created Date). "
            "Existing emails are skipped unless you pass --update.")

    def add_arguments(self, parser):
        parser.add_argument("--file", default=str(Path(settings.BASE_DIR) / "data" / "users.csv"))
        parser.add_argument("--update", action="store_true",
                            help="Also update name, role, active status and created date of existing users (matched by email). Passwords are never changed.")
        parser.add_argument("--password", default="Password@123", help="Password given to NEW users (the CSV has none).")
        parser.add_argument("--admin-password", default="Admin@123", help="Password given to NEW Admin users.")

    def handle(self, *args, **opts):
        roles = {norm(label): value for value, label in User.Role.choices}
        roles.update({norm(value): value for value, _ in User.Role.choices})
        rows = read_rows(opts["file"], ["Name", "Email", "Role"])

        for n, r in enumerate(rows, start=2):  # validate everything before writing anything
            if "@" not in r["Email"] or not r["Name"]:
                raise CommandError(f"Line {n}: a name and a valid email are required.")
            if norm(r["Role"]) not in roles:
                raise CommandError(f"Line {n}: unknown role '{r['Role']}' (use {', '.join(l for _, l in User.Role.choices)}).")
            try:
                parse_date(r.get("Created Date", ""))
            except ValueError as exc:
                raise CommandError(f"Line {n}: {exc}")

        created = updated = unchanged = 0
        with transaction.atomic():
            for r in rows:
                email = r["Email"].lower()
                role = roles[norm(r["Role"])]
                is_admin = role == User.Role.ADMIN
                active = r.get("Active", "Yes").lower() not in ("no", "false", "0")
                made = parse_date(r.get("Created Date", ""))
                existing = User.objects.filter(email__iexact=email).first()

                if existing is None:
                    user = User(email=email, name=r["Name"], role=role, is_active=active, is_staff=is_admin,
                                is_superuser=is_admin, created_at=made or timezone.now())
                    user.set_password(opts["admin_password"] if is_admin else opts["password"])
                    user.save()
                    created += 1
                    continue

                wanted = {"name": r["Name"], "role": role, "is_active": active,
                          "is_staff": is_admin, "is_superuser": is_admin}
                if made:
                    wanted["created_at"] = made
                changed = [f for f, v in wanted.items() if getattr(existing, f) != v]
                if opts["update"] and changed:
                    for f in changed:
                        setattr(existing, f, wanted[f])
                    existing.save(update_fields=changed)
                    updated += 1
                else:
                    unchanged += 1

            # Safety net: never let a CSV edit lock everyone out of the admin pages.
            if opts["update"] and not User.objects.filter(is_active=True).filter(role=User.Role.ADMIN).exists():
                raise CommandError("This update would leave no active Admin user, so nothing was changed. "
                                   "Keep at least one active Admin row in users.csv.")

        self.stdout.write(self.style.SUCCESS(f"Users: {created} created, {updated} updated, {unchanged} unchanged."))
        if unchanged and not opts["update"]:
            self.stdout.write("Tip: edited an existing user in the CSV? Run again with --update to apply it (the email is the key, so don't change it).")
        if created:
            self.stdout.write("New users have the default password from --password / --admin-password. Ask everyone to change it.")
