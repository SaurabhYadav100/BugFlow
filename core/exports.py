"""CSV export for the four database tables: users, projects, issues, workflow states."""
import csv
import io

from django.contrib.auth import get_user_model
from django.db.models import Count
from django.utils import timezone

from issues.models import Issue
from projects.models import Project


def safe(value):
    """Blank for None; neutralise spreadsheet formulas (=, +, -, @) so a title can't run code in Excel."""
    if value is None:
        return ""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def stamp(value):
    return timezone.localtime(value).strftime("%Y-%m-%d %H:%M") if value else ""


def users_rows():
    yield ["ID", "Name", "Email", "Role", "Active", "Created Date"]  # never exports password hashes
    for u in get_user_model().objects.all():
        yield [u.pk, u.name, u.email, u.get_role_display(), "Yes" if u.is_active else "No", stamp(u.created_at)]


def projects_rows():
    yield ["ID", "Name", "Description", "Project Manager", "Total Issues", "Created Date"]
    for p in Project.objects.select_related("manager").annotate(n=Count("issues")):
        yield [p.pk, p.name, p.description, p.manager.name if p.manager else "", p.n, stamp(p.created_at)]


def issues_rows():
    yield ["ID", "Title", "Project", "Affected Module", "Type", "Status", "Priority", "Severity", "Assigned To", "Reported By",
           "Sprint", "Created Date", "Updated Date", "Resolved Date", "Description", "Resolution Notes"]
    for i in Issue.objects.select_related("project", "assignee", "reporter", "sprint").order_by("issue_type", "number"):
        yield [i.key, i.title, i.project.name, i.get_module_display(), i.get_issue_type_display(), i.get_status_display(),
               i.get_priority_display(), i.get_severity_display(), i.assignee.name if i.assignee else "",
               i.reporter.name, i.sprint.name if i.sprint else "", stamp(i.created_at), stamp(i.updated_at),
               stamp(i.resolved_at), i.description, i.resolution_notes]


def workflow_rows():
    yield ["State", "Can Move To", "Issues In State"]
    labels, counts = dict(Issue.Status.choices), dict(Issue.objects.order_by().values_list("status").annotate(n=Count("id")))
    for key, label in Issue.Status.choices:
        yield [label, ", ".join(labels[n] for n in Issue.WORKFLOW.get(key, [])), counts.get(key, 0)]


TABLES = {
    "users": ("users.csv", users_rows),
    "projects": ("projects.csv", projects_rows),
    "issues": ("issues.csv", issues_rows),
    "workflow": ("workflow_states.csv", workflow_rows),
}


def csv_bytes(table):
    """One table as UTF-8 CSV (with a BOM so Excel shows accented characters correctly)."""
    buf = io.StringIO(newline="")
    writer = csv.writer(buf)
    for row in TABLES[table][1]():
        writer.writerow([safe(c) for c in row])
    return buf.getvalue().encode("utf-8-sig")
