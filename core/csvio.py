import csv
from pathlib import Path

from django.core.management.base import CommandError


def read_rows(path, required):
    """Read a CSV (UTF-8, with or without BOM) into a list of dicts; fail with a clear message if columns are missing."""
    path = Path(path)
    if not path.exists():
        raise CommandError(f"File not found: {path}")
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        reader.fieldnames = [h.strip() for h in (reader.fieldnames or [])]
        missing = [c for c in required if c not in reader.fieldnames]
        if missing:
            raise CommandError(f"{path.name} is missing column(s): {', '.join(missing)}")
        rows = [{k: (v or "").strip() for k, v in r.items() if k} for r in reader]
    if not rows:
        raise CommandError(f"{path.name} has no data rows.")
    return rows


# ISO first (what the app exports), then the day-first formats Excel writes in India/UK/EU locales.
DATE_FORMATS = (
    "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d",
    "%d-%m-%Y %H:%M", "%d-%m-%Y %H:%M:%S", "%d-%m-%Y",
    "%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y",
)


def parse_date(text):
    """'2025-04-27 12:00' or '27-04-2025 12:00' or '27/04/2025' -> aware datetime, or None if blank.
    Slash and dash dates are read day-first (27-04-2025 = 27 April 2025)."""
    from datetime import datetime
    from django.utils import timezone

    text = (text or "").strip()
    if not text:
        return None
    for fmt in DATE_FORMATS:
        try:
            return timezone.make_aware(datetime.strptime(text, fmt))
        except ValueError:
            continue
    raise ValueError(f"unrecognised date '{text}' (use YYYY-MM-DD HH:MM, or DD-MM-YYYY HH:MM)")
