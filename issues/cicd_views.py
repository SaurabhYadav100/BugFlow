import hmac
import json
import re

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .github_views import _display_id, _role, _slug, _value
from .models import Issue, PipelineRun, PipelineTest

# ---- Adjust to the status values stored in your Issue model ----------------
OPEN_VALUES = {"open", "new"}
IN_PROGRESS_VALUE = "in_progress"
# ---------------------------------------------------------------------------
ALLOWED_ROLES = {"admin", "project_manager"}
STAGE_KEYS = ("push", "build", "tests", "deploy")
STEPS = [
    ("push", "Code Push", "github"),
    ("build", "Build & Test", "settings"),
    ("tests", "Tests Passed", "clipboard"),
    ("deploy", "Deployment", "rocket"),
]


# ============================ helpers ======================================
def _norm_stage(value):
    v = str(value or "").strip().lower()
    if v in ("success", "passed", "pass", "completed", "ok"):
        return "success"
    if v in ("failure", "failed", "fail", "error", "cancelled", "canceled"):
        return "failure"
    if v in ("running", "in_progress", "queued"):
        return "running"
    return "pending"          # includes "skipped"


def _norm_status(value):
    v = _norm_stage(value)
    return {"success": "success", "failure": "failed", "running": "running"}.get(v)


def _truthy(value):
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "passed", "pass", "ok")
    return bool(value)


def _clip(value, field):
    return str(value)[: PipelineRun._meta.get_field(field).max_length]


def _fmt_duration(seconds):
    if not seconds:
        return "-"
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m {secs:02d}s" if minutes else f"{secs}s"


def _apply_issue_update(run):
    """Move a linked 'open' issue to 'in progress' after a successful deployment."""
    issue = run.issue
    if issue is None:
        return

    def label():
        display = getattr(issue, "get_status_display", None)
        return display() if callable(display) else str(issue.status)

    if run.status == "success":
        current = str(issue.status).strip().lower().replace(" ", "_")
        if current in OPEN_VALUES:
            issue.status = IN_PROGRESS_VALUE
            issue.save()
            run.issue_status_after = label()
            run.issue_note = f"Code fix deployed and issue moved to {run.issue_status_after}."
        else:
            run.issue_status_after = label()
            run.issue_note = f"Code fix deployed. Issue status stays {run.issue_status_after}."
    elif run.status == "failed":
        run.issue_status_after = label()
        run.issue_note = "Pipeline failed. Issue status unchanged."


# ============================ webhook ======================================
@csrf_exempt
@require_POST
def cicd_webhook(request):
    """Receives workflow results from GitHub Actions (see the workflow file)."""
    token = getattr(settings, "CICD_WEBHOOK_TOKEN", "")
    sent = request.headers.get("X-BugFlow-Token", "")
    if not token or not hmac.compare_digest(sent.encode(), token.encode()):
        return JsonResponse({"detail": "Invalid or missing token."}, status=403)

    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"detail": "Invalid JSON."}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({"detail": "JSON object expected."}, status=400)

    external_id = str(data.get("run_id") or "").strip()
    if not external_id:
        return JsonResponse({"detail": "run_id is required."}, status=400)
    try:
        run_number = int(data.get("run_number"))
    except (TypeError, ValueError):
        return JsonResponse({"detail": "run_number must be a number."}, status=400)

    now = timezone.now()
    with transaction.atomic():
        triggered = parse_datetime(str(data.get("triggered_at") or "")) or now
        if timezone.is_naive(triggered):
            triggered = timezone.make_aware(triggered)
        run, created = PipelineRun.objects.get_or_create(
            external_id=external_id[:40],
            defaults={"run_number": run_number, "triggered_at": triggered},
        )
        previous_status = None if created else run.status
        run.run_number = run_number

        for field, key in (("workflow_name", "workflow"), ("branch", "branch"),
                           ("commit_id", "commit_id"), ("commit_message", "commit_message"),
                           ("run_url", "run_url")):
            if data.get(key):
                setattr(run, field, _clip(data[key], field))

        # Stages: record the time each stage first reaches a new state
        stages = dict(run.stages or {})
        for key, value in (data.get("stages") or {}).items():
            if key in STAGE_KEYS:
                state = _norm_stage(value)
                old = stages.get(key, {})
                if old.get("status") != state or "at" not in old:
                    stages[key] = {"status": state, "at": now.isoformat()}

        # Overall status: explicit value, otherwise worked out from the stages
        status = _norm_status(data.get("status"))
        if status is None:
            states = [stages.get(k, {}).get("status") for k in STAGE_KEYS]
            if "failure" in states:
                status = "failed"
            elif all(s == "success" for s in states):
                status = "success"
            else:
                status = "running"
        run.status = status
        if status == "success":                      # a finished run has every stage done
            for key in STAGE_KEYS:
                if stages.get(key, {}).get("status") != "success":
                    stages[key] = {"status": "success", "at": now.isoformat()}
        run.stages = stages

        try:
            duration = int(data.get("duration_seconds") or 0)
        except (TypeError, ValueError):
            duration = 0
        if duration > 0:
            run.duration_seconds = duration
        elif status in ("success", "failed") and not run.duration_seconds:
            run.duration_seconds = max(int((now - run.triggered_at).total_seconds()), 0)

        # Link to an issue: "issue_id" in the payload, or "#<id>" in the commit message
        issue_ref = data.get("issue_id")
        if not issue_ref:
            match = re.search(r"#(\d+)", run.commit_message or "")
            issue_ref = match.group(1) if match else None
        if issue_ref and str(issue_ref).isdigit():
            issue = Issue.objects.filter(pk=int(issue_ref)).first()
            if issue:
                run.issue = issue

        if run.status != previous_status and run.status in ("success", "failed"):
            _apply_issue_update(run)
        run.save()

        tests = data.get("tests")
        if isinstance(tests, list):
            run.tests.all().delete()
            PipelineTest.objects.bulk_create([
                PipelineTest(run=run, name=str(t["name"])[:200], passed=_truthy(t.get("passed")))
                for t in tests[:300] if isinstance(t, dict) and t.get("name")
            ])

    return JsonResponse(
        {"ok": True, "id": run.pk, "status": run.status, "created": created},
        status=201 if created else 200,
    )


# ============================== page =======================================
@login_required
def cicd_view(request, run_id=None):
    # Only Admin and Project Manager may open this page
    if not (request.user.is_superuser or _role(request.user) in ALLOWED_ROLES):
        raise PermissionDenied

    runs = PipelineRun.objects.select_related("issue")
    run = get_object_or_404(runs, pk=run_id) if run_id else runs.first()
    if run is None:
        return render(request, "cicd.html", {"run": None, "nav": "cicd"})

    steps = []
    for key, label, icon_name in STEPS:
        info = (run.stages or {}).get(key, {})
        at = parse_datetime(info["at"]) if info.get("at") else None
        steps.append({"key": key, "label": label, "icon": icon_name,
                      "state": info.get("status", "pending"), "at": at})

    tests = list(run.tests.all())
    total = len(tests)
    passed = sum(1 for t in tests if t.passed)
    failed = total - passed
    pct = round(passed * 100 / total) if total else 0
    ring = "#22a95b" if total and not failed else ("#f59e0b" if pct >= 50 else "#ef4444")

    issue = run.issue
    issue_info = None
    if issue:
        type_raw = _value(issue, "issue_type", "type", "kind")[0]
        issue_info = {
            "obj": issue,
            "display_id": _display_id(issue, type_raw),
            "status_label": run.issue_status_after or _value(issue, "status")[1],
            "status_key": _slug(run.issue_status_after or _value(issue, "status")[0]),
        }

    context = {
        "nav": "cicd",
        "run": run,
        "runs": PipelineRun.objects.all()[:20],
        "steps": steps,
        "tests": tests,
        "total_tests": total,
        "failed_tests": failed,
        "pct": pct,
        "ring": ring,
        "duration": _fmt_duration(run.duration_seconds),
        "issue_info": issue_info,
    }
    return render(request, "cicd.html", context)