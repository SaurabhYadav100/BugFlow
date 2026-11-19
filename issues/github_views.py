from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from .models import GitHubLink, Issue

ALLOWED_ROLES = {"admin", "project_manager"}


def _role(user):
    key = getattr(user, "role_key", None) or getattr(user, "role", "")
    return str(key).strip().lower().replace(" ", "_")


def _value(obj, *names):
    """(raw value, display label) of the first attribute that exists on obj."""
    for name in names:
        if hasattr(obj, name):
            raw = getattr(obj, name)
            display = getattr(obj, f"get_{name}_display", None)
            return raw, (display() if callable(display) else raw)
    return "", ""


def _person(user):
    if not user:
        return "Unassigned"
    full = user.get_full_name() if hasattr(user, "get_full_name") else ""
    return full or getattr(user, "username", None) or str(user)


def _display_id(issue, issue_type):
    for name in ("issue_key", "key", "code", "ticket_id", "reference"):
        value = getattr(issue, name, None)
        if value:
            return str(value)
    prefix = "FEAT" if str(issue_type).lower() in ("feature", "feat", "enhancement") else "BUG"
    return f"{prefix}-{issue.pk:03d}"


def _slug(value):
    return str(value or "").strip().lower().replace(" ", "_")


def _comments(issue):
    manager = getattr(issue, "comments", None) or getattr(issue, "comment_set", None)
    if manager is None:
        return []
    items = []
    for c in manager.all():
        author = getattr(c, "author", None) or getattr(c, "user", None)
        items.append({
            "author": _person(author) if author else "Unknown",
            "text": _value(c, "text", "body", "content", "comment")[0],
            "when": getattr(c, "created_at", None),
        })
    return items


@login_required
def github_view(request, issue_id=None):
    # Only Admin and Project Manager may open this page
    if not (request.user.is_superuser or _role(request.user) in ALLOWED_ROLES):
        raise PermissionDenied

    linked_issues = (
        Issue.objects.filter(github_link__isnull=False)
        .order_by("-github_link__linked_at")
    )

    if issue_id is None:
        latest = linked_issues.first()
        if latest:
            return redirect("github_issue", issue_id=latest.pk)
        return render(request, "issues/github_detail.html", {"issue": None, "nav": "github"})

    issue = get_object_or_404(Issue, pk=issue_id)
    try:
        link = issue.github_link
    except ObjectDoesNotExist:
        link = None

    type_raw, type_label = _value(issue, "issue_type", "type", "kind")
    sev_raw, sev_label = _value(issue, "severity", "priority")
    status_raw, status_label = _value(issue, "status")
    comments = _comments(issue)

    context = {
        "nav": "github",
        "issue": issue,
        "link": link,
        "linked_issues": linked_issues,
        "display_id": _display_id(issue, type_raw),
        "issue_type": type_label or "Issue",
        "severity": sev_label,
        "severity_key": _slug(sev_raw),
        "status": status_label,
        "status_key": _slug(status_raw),
        "description": _value(issue, "description", "details")[0],
        "module": _value(issue, "module", "component")[1] or "-",
        "assignee": _person(getattr(issue, "assignee", None)),
        "created_on": _value(issue, "created_at", "created", "created_date")[0],
        "comments": comments,
    }
    return render(request, "issues/github_detail.html", context)