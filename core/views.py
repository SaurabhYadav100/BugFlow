from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.generic import TemplateView

from core.mixins import AdminRequiredMixin, PageMixin, UserPropMixin
from issues.models import Issue
from projects.models import Project

STATUS_COLORS = {
    "open": "#ef4444", "in_progress": "#f5a623", "testing": "#8b5cf6", "resolved": "#16a34a", "closed": "#64748b",
}
PRIORITY_COLORS = {"low": "#16a34a", "medium": "#f5a623", "high": "#f97316", "critical": "#e11d48"}
TYPE_COLORS = {"bug": "#ef4444", "feature": "#f5a623", "task": "#16a34a", "support": "#1570ef"}


def distribution(qs, field, choices, colors):
    """[{key,label,count,percent,color}] for a choice field over a queryset, in choice order."""
    counts = dict(qs.order_by().values_list(field).annotate(c=Count("id")))
    total = sum(counts.values())
    return [
        {"key": k, "label": l, "count": counts.get(k, 0), "color": colors.get(k, "#94a3b8"),
         "percent": round(counts.get(k, 0) * 100 / total) if total else 0}
        for k, l in choices
    ]


def conic(items):
    """CSS conic-gradient string for a donut chart."""
    total = sum(i["count"] for i in items)
    if not total:
        return "conic-gradient(#e5e7eb 0 100%)"
    stops, start = [], 0.0
    for i in items:
        if i["count"]:
            end = start + i["count"] * 100 / total
            stops.append(f'{i["color"]} {start:.2f}% {end:.2f}%')
            start = end
    return f'conic-gradient({", ".join(stops)})'


def require(prop):
    """Function-view decorator: signed-in users whose `prop` is false get a 403 (not a redirect to login)."""
    def deco(view):
        @login_required
        def wrapper(request, *args, **kwargs):
            if not getattr(request.user, prop):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapper
    return deco


def stat(label, value, tone, icon):
    return {"label": label, "value": value, "tone": tone, "icon": icon}


class DashboardView(PageMixin, TemplateView):
    """One URL, four dashboards: the content depends on the signed-in user's role."""

    template_name = "core/dashboard.html"
    page_title = "Dashboard"
    nav = "dashboard"
    MAIN = ("open", "in_progress", "resolved")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user, role = self.request.user, self.request.user.role_key
        ctx["role"] = role
        count = lambda qs, **f: qs.filter(**f).count()

        if role == "admin":
            qs = Issue.objects.all()
            statuses = distribution(qs, "status", Issue.Status.choices, STATUS_COLORS)
            statuses = [s for s in statuses if s["key"] in self.MAIN or s["count"]]
            ctx.update(
                heading="Dashboard",
                stats=[stat("Total Issues", qs.count(), "primary", "list"), stat("Open Issues", count(qs, status="open"), "danger", "inbox"),
                       stat("In Progress", count(qs, status="in_progress"), "warning", "clock"),
                       stat("Resolved", count(qs, status="resolved"), "success", "check-circle")],
                statuses=statuses, donut=conic(statuses), total=qs.count(),
                recent=qs.select_related("project")[:5],
                recent_users=get_user_model().objects.order_by("-created_at", "-id")[:4],
                user_total=get_user_model().objects.count(), project_total=Project.objects.count(),
            )
        elif role == "project_manager":
            projects = Project.objects.filter(manager=user)
            qs = Issue.objects.filter(project__in=projects)
            ctx.update(
                heading="Project Manager Dashboard",
                stats=[stat("My Projects", projects.count(), "primary", "folder"), stat("Total Issues", qs.count(), "primary", "list"),
                       stat("Open Issues", count(qs, status="open"), "danger", "inbox"),
                       stat("In Progress", count(qs, status="in_progress"), "warning", "clock")],
                overview=projects.annotate(
                    total=Count("issues", distinct=True),
                    open_n=Count("issues", filter=Q(issues__status="open"), distinct=True),
                    progress_n=Count("issues", filter=Q(issues__status="in_progress"), distinct=True)),
            )
        elif role == "developer":
            qs = Issue.objects.filter(assignee=user)
            ctx.update(
                heading="Developer Dashboard",
                stats=[stat("Assigned Issues", qs.count(), "primary", "list"), stat("In Progress", count(qs, status="in_progress"), "warning", "clock"),
                       stat("Resolved", count(qs, status="resolved"), "success", "check-circle"),
                       stat("Closed", count(qs, status="closed"), "secondary", "check")],
                my_issues=qs.select_related("project")[:6],
            )
        else:  # tester
            qs = Issue.objects.filter(reporter=user)
            ctx.update(
                heading="Tester Dashboard",
                stats=[stat("Reported Issues", qs.count(), "primary", "list"), stat("Testing", count(qs, status="testing"), "purple", "clipboard"),
                       stat("Resolved", count(qs, status="resolved"), "success", "check-circle"),
                       stat("Closed", count(qs, status="closed"), "secondary", "check")],
                reported=qs.select_related("project")[:6],
            )
        return ctx


# ---------------- reports ----------------
REPORT_TYPES = {
    "summary": ("Issue Summary Report", lambda qs: qs),
    "open": ("Open Issues Report", lambda qs: qs.filter(status="open")),
    "resolved": ("Resolved Issues Report", lambda qs: qs.filter(status__in=["resolved", "closed"])),
    "high": ("High Priority Report", lambda qs: qs.filter(priority__in=["high", "critical"])),
}


def report_queryset(user, report_type):
    """What a user may report on: Admin everything, PM their projects, Tester what they reported."""
    qs = Issue.objects.select_related("project", "assignee")
    if user.role_key == "project_manager":
        qs = qs.filter(project__manager=user)
    elif user.role_key == "tester":
        qs = qs.filter(reporter=user)
    return REPORT_TYPES.get(report_type, REPORT_TYPES["summary"])[1](qs)


class ReportsView(UserPropMixin, PageMixin, TemplateView):
    user_prop = "can_view_reports"
    template_name = "core/reports.html"
    page_title = "Reports"
    nav = "reports"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        rtype = self.request.GET.get("type", "summary")
        if rtype not in REPORT_TYPES:
            rtype = "summary"
        qs = report_queryset(self.request.user, rtype)
        by_type = [t for t in distribution(qs, "issue_type", Issue.IssueType.choices, TYPE_COLORS)]
        by_status = distribution(qs, "status", Issue.Status.choices, STATUS_COLORS)
        top = max([s["count"] for s in by_status] or [0]) or 1
        for s in by_status:
            s["height"] = round(s["count"] * 100 / top)
        ctx.update(
            report_types=[(k, v[0]) for k, v in REPORT_TYPES.items()], rtype=rtype, report_title=REPORT_TYPES[rtype][0],
            total=qs.count(), by_type=by_type, donut=conic(by_type), by_status=by_status,
            rows=qs[:25], more=max(qs.count() - 25, 0),
        )
        return ctx


@require("can_view_reports")
def report_export(request):
    """Download the selected report as a PDF."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    rtype = request.GET.get("type", "summary")
    rtype = rtype if rtype in REPORT_TYPES else "summary"
    title = REPORT_TYPES[rtype][0]
    qs = report_queryset(request.user, rtype)

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="bugflow-{rtype}-report.pdf"'
    doc = SimpleDocTemplate(response, pagesize=landscape(A4), leftMargin=28, rightMargin=28, topMargin=28, bottomMargin=28,
                            title=f"BugFlow - {title}")
    styles = getSampleStyleSheet()
    data = [["ID", "Title", "Project", "Type", "Priority", "Status", "Assigned To", "Created"]]
    for i in qs:
        data.append([i.key, i.title[:48], i.project.name[:24], i.get_issue_type_display(), i.get_priority_display(),
                     i.get_status_display(), i.assignee.name if i.assignee else "Unassigned", i.created_at.strftime("%b %d, %Y")])
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#10264a")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d3dcec")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f6fb")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    stamp = timezone.localtime().strftime("%b %d, %Y %H:%M")
    doc.build([
        Paragraph(f"BugFlow - {title}", styles["Title"]),
        Paragraph(f"Generated {stamp} by {request.user.name} - {qs.count()} issue(s)", styles["Normal"]),
        Spacer(1, 12), table,
    ])
    return response


# ---------------- database browser (admin) ----------------
class DatabaseView(AdminRequiredMixin, PageMixin, TemplateView):
    """Admin-only 'Database Tables' browser. Tabs: users (overview), projects, issues, workflow."""

    template_name = "core/database.html"
    page_title = "Database Tables"
    nav = "database"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        tab = self.request.GET.get("tab", "users")
        if tab not in ("users", "projects", "issues", "workflow"):
            tab = "users"
        counts = dict(Issue.objects.order_by().values_list("status").annotate(c=Count("id")))
        labels = dict(Issue.Status.choices)
        workflow = [
            {"key": key, "label": label, "count": counts.get(key, 0),
             "next": [labels[n] for n in Issue.WORKFLOW.get(key, [])]}
            for key, label in Issue.Status.choices
        ]
        ctx.update(
            tab=tab, users=get_user_model().objects.all(), projects=Project.objects.all(),
            issues=Issue.objects.select_related("assignee"), workflow=workflow,
        )
        return ctx


@require("is_admin_role")
def database_status(request):
    """Standalone 'Database Connected Successfully' page (admins only)."""
    db = settings.DATABASES["default"]
    vendor = connection.vendor
    error, version = None, ""
    try:
        connection.ensure_connection()
        with connection.cursor() as cur:
            cur.execute("SELECT version()" if vendor == "postgresql" else "SELECT sqlite_version()")
            version = cur.fetchone()[0]
    except Exception as exc:  # show the reason instead of a 500 page
        error = str(exc)
    return render(request, "core/database_status.html", {
        "connected": error is None, "error": error, "version": version,
        "db_type": "PostgreSQL" if vendor == "postgresql" else vendor.title(),
        "db_name": db.get("NAME"), "db_user": db.get("USER") or "-",
        "db_host": db.get("HOST") or "-", "db_port": db.get("PORT") or "-",
        "app_port": request.get_port(),
    })
