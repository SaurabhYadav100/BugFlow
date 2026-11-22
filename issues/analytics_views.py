from datetime import datetime, time, timedelta

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.db.models import (
    Avg, Count, DurationField, ExpressionWrapper, F, Q, Sum,
)
from django.db.models.functions import Lower, TruncMonth
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from projects.models import Project
from .models import Issue

# ---- Adjust these to match the values stored in your Issue model ----------
# (compared case-insensitively)
OPEN_VALUES = ["open", "new"]
IN_PROGRESS_VALUES = ["in_progress", "in progress", "in-progress", "inprogress"]
RESOLVED_VALUES = ["resolved", "closed", "done", "fixed"]
SEVERITIES = ["critical", "high", "medium", "low"]
ALLOWED_ROLES = {"admin", "project_manager"}
ISSUE_LIST_URL_NAMES = ["issue-list", "issue_list", "issues", "issues:list"]
# ---------------------------------------------------------------------------


def _role(user):
    key = getattr(user, "role_key", None) or getattr(user, "role", "")
    return str(key).strip().lower().replace(" ", "_")

def _pick(model, *names):
    """Return the first field name that exists on the model, else None."""
    existing = {f.name for f in model._meta.get_fields()}
    for name in names:
        if name in existing:
            return name
    return None


def _last_months(n=6):
    """First day of each of the last n months, oldest first."""
    today = timezone.localdate().replace(day=1)
    year, month, months = today.year, today.month, []
    for _ in range(n):
        months.append(today.replace(year=year, month=month))
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    return months[::-1]


def _issues_url():
    for name in ISSUE_LIST_URL_NAMES:
        try:
            return reverse(name)
        except NoReverseMatch:
            continue
    return "#"


@login_required
def analytics_view(request):
    # Only Admin and Project Manager may open this page
    if not (request.user.is_superuser or _role(request.user) in ALLOWED_ROLES):
        raise PermissionDenied

    # ---- Work out which optional fields exist -----------------------------
    created_f = _pick(Issue, "created_at", "created", "created_date", "date_created")
    if created_f is None:
        raise ImproperlyConfigured(
            "Issue needs a DateTimeField such as created_at for the analytics page."
        )
    updated_f = _pick(Issue, "updated_at", "updated", "modified_at") or created_f
    resolved_f = _pick(Issue, "resolved_at", "closed_at") or updated_f
    module_f = _pick(Issue, "module", "component")
    has_severity = _pick(Issue, "severity") is not None

    # ---- Filters (project + date range) -----------------------------------
    project_id = request.GET.get("project", "")
    try:
        days = int(request.GET.get("days", 365))
    except ValueError:
        days = 30
    since = timezone.now() - timedelta(days=days)

    base_qs = Issue.objects.annotate(status_l=Lower("status"))
    if has_severity:
        base_qs = base_qs.annotate(severity_l=Lower("severity"))
    if project_id.isdigit():
        base_qs = base_qs.filter(project_id=int(project_id))
    qs = base_qs.filter(**{f"{created_f}__gte": since})

    # ---- Stat cards + donut -----------------------------------------------
    counts = qs.order_by().aggregate(
        total=Count("id"),
        open=Count("id", filter=Q(status_l__in=OPEN_VALUES)),
        in_progress=Count("id", filter=Q(status_l__in=IN_PROGRESS_VALUES)),
        resolved=Count("id", filter=Q(status_l__in=RESOLVED_VALUES)),
    )
    total = counts["total"]

    # ---- Severity bar chart -----------------------------------------------
    if has_severity:
        sev = qs.order_by().aggregate(
            **{s: Count("id", filter=Q(severity_l=s)) for s in SEVERITIES}
        )
    else:
        sev = {s: 0 for s in SEVERITIES}

    # ---- Monthly defect trend (last 6 months) -----------------------------
    months = _last_months(6)
    start = timezone.make_aware(datetime.combine(months[0], time.min))
    created = {
        (r["m"].year, r["m"].month): r["c"]
        for r in base_qs.filter(**{f"{created_f}__gte": start}).order_by()
        .annotate(m=TruncMonth(created_f)).values("m")
        .annotate(c=Count("id")).order_by()
    }
    resolved = {
        (r["m"].year, r["m"].month): r["c"]
        for r in base_qs.filter(
            status_l__in=RESOLVED_VALUES, **{f"{resolved_f}__gte": start}
        ).order_by()
        .annotate(m=TruncMonth(resolved_f)).values("m")
        .annotate(c=Count("id")).order_by()
    }
    trend = {
        "months": [m.strftime("%b") for m in months],
        "total": [created.get((m.year, m.month), 0) for m in months],
        "resolved": [resolved.get((m.year, m.month), 0) for m in months],
    }

    # ---- Project quality metrics ------------------------------------------
    avg = qs.filter(
        status_l__in=RESOLVED_VALUES, **{f"{resolved_f}__isnull": False}
    ).order_by().aggregate(
        a=Avg(ExpressionWrapper(
            F(resolved_f) - F(created_f), output_field=DurationField()
        ))
    )["a"]
    avg_days = round(avg.total_seconds() / 86400, 1) if avg else 0

    resolution_rate = round(counts["resolved"] * 100 / total) if total else 0

    # Defect density needs a numeric `kloc` field on Project; shows N/A without it
    defect_density = "N/A"
    if _pick(Project, "kloc"):
        projects_qs = Project.objects.all()
        if project_id.isdigit():
            projects_qs = projects_qs.filter(pk=int(project_id))
        kloc = projects_qs.aggregate(k=Sum("kloc"))["k"]
        if kloc:
            defect_density = f"{total / float(kloc):.1f} / KLOC"

    # Backlog health = % of unresolved issues that are newer than 30 days
    unresolved = base_qs.exclude(status_l__in=RESOLVED_VALUES)
    unresolved_count = unresolved.count()
    recent_unresolved = unresolved.filter(
        **{f"{created_f}__gte": timezone.now() - timedelta(days=30)}
    ).count()
    backlog_health = (
        round(recent_unresolved * 100 / unresolved_count) if unresolved_count else 100
    )

    # ---- Top modules by defects (needs a `module` field on Issue) ---------
    top_modules = []
    if module_f:
        rows = (qs.order_by().values(module_f)
                .annotate(n=Count("id")).order_by("-n")[:5])
        for r in rows:
            top_modules.append({
                "name": r[module_f] or "Others",
                "total": r["n"],
                "share": round(r["n"] * 100 / total) if total else 0,
            })

    # ---- Recent activity ---------------------------------------------------
    activity = []
    for i in base_qs.order_by(f"-{updated_f}")[:4]:
        sev_value = str(getattr(i, "severity", "") or "")
        activity.append({
            "title": getattr(i, "title", None) or str(i),
            "key": sev_value.lower() or "low",
            "severity": sev_value.title() or "-",
            "when": getattr(i, updated_f),
        })

    context = {
        "projects": Project.objects.all(),
        "selected_project": project_id,
        "days": days,
        "counts": counts,
        "metrics": {
            "avg_days": avg_days,
            "resolution_rate": resolution_rate,
            "defect_density": defect_density,
            "backlog_health": backlog_health,
        },
        "top_modules": top_modules,
        "activity": activity,
        "issues_url": _issues_url(),
        "nav": "analytics",
        "chart_data": {
            "status": [counts["open"], counts["in_progress"], counts["resolved"]],
            "severity": [sev[s] for s in SEVERITIES],
            "trend": trend,
        },
    }
    return render(request, "issues/analytics.html", context)
