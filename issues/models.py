import os
import uuid

from django.db.models.signals import post_delete
from django.dispatch import receiver

from django.conf import settings
from django.db import models
from django.db.models import Max
from django.utils import timezone


class Issue(models.Model):
    class IssueType(models.TextChoices):
        BUG = "bug", "Bug"
        FEATURE = "feature", "Feature"
        TASK = "task", "Task"
        SUPPORT = "support", "Support"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        IN_PROGRESS = "in_progress", "In Progress"
        TESTING = "testing", "Testing"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    Severity = Priority  # same scale, separate field
        
    class Module(models.TextChoices):
        LOGIN = "login", "Login"
        DASHBOARD = "dashboard", "Dashboard"
        UI = "ui", "UI"
        SEARCH = "search", "Search"
        BACKEND = "backend", "Backend"
        DATABASE = "database", "Database"
        API = "api", "API"
        REPORTS = "reports", "Reports"
        OTHER = "other", "Other"

    # Which status an issue may move to next. Edit this to change the workflow.
    WORKFLOW = {
        "open": ["in_progress"],
        "in_progress": ["testing", "open"],
        "testing": ["resolved", "in_progress"],
        "resolved": ["closed", "open"],
        "closed": ["open"],
    }
    # Extra limit per role on the status they may *set* (Admins and Project Managers are unrestricted).
    ROLE_TARGETS = {
        "developer": {"open", "in_progress", "testing"},
        "tester": {"open", "in_progress", "resolved", "closed"},
    }
    KEY_PREFIX = {"bug": "BUG", "feature": "FEAT", "task": "TASK", "support": "SUP"}

    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="issues")
    sprint = models.ForeignKey("projects.Sprint", null=True, blank=True, on_delete=models.SET_NULL, related_name="issues")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    issue_type = models.CharField(max_length=10, choices=IssueType.choices, default=IssueType.BUG)
    number = models.PositiveIntegerField(editable=False, default=0)  # per-type counter -> BUG-001
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.OPEN)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    severity = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)

    module = models.CharField("Affected Module", max_length=20, choices=Module.choices, blank=True)
    
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reported_issues")
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_issues"
    )
    resolution_notes = models.TextField(blank=True, help_text="How was this fixed? Used later for resolution suggestions.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [models.UniqueConstraint(fields=["issue_type", "number"], name="unique_issue_key")]

    def __str__(self):
        return f"{self.key} {self.title}"

    @property
    def key(self):
        return f"{self.KEY_PREFIX.get(self.issue_type, 'ISS')}-{self.number:03d}"

    # ---- permissions ----
    def can_edit(self, user):
        """Full edit: Admin / Project Manager, or the Tester who reported it."""
        return user.can_manage or (user.is_tester and self.reporter_id == user.id)

    def can_update(self, user):
        """Status / assignment updates: managers, the assignee, or the reporting Tester."""
        return user.can_manage or self.assignee_id == user.id or (user.is_tester and self.reporter_id == user.id)

    def allowed_statuses(self, user):
        nxt = [self.status] + self.WORKFLOW.get(self.status, [])
        if user.can_manage:
            return nxt
        targets = self.ROLE_TARGETS.get(user.role, set())
        return [s for s in nxt if s == self.status or s in targets]

    # ---- history ----
    def log(self, actor, text):
        IssueHistory.objects.create(issue=self, actor=actor, text=text[:300])

    def save(self, *args, **kwargs):
        type_changed = self.pk and not Issue.objects.filter(pk=self.pk, issue_type=self.issue_type).exists()
        if not self.number or type_changed:
            last = Issue.objects.filter(issue_type=self.issue_type).aggregate(m=Max("number"))["m"] or 0
            self.number = last + 1
        if self.status in (self.Status.RESOLVED, self.Status.CLOSED):
            self.resolved_at = self.resolved_at or timezone.now()
        else:
            self.resolved_at = None
        super().save(*args, **kwargs)


class Comment(models.Model):
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="comments")
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.author} on {self.issue.key}"


class IssueHistory(models.Model):
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name="history")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    text = models.CharField(max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name_plural = "issue history"


def attachment_path(instance, filename):
    """Store under a random name so uploaded names can never clash or contain tricks."""
    ext = os.path.splitext(filename)[1].lower()
    return f"attachments/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{ext}"


class Attachment(models.Model):
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to=attachment_path)
    original_name = models.CharField(max_length=255)
    size = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at", "-id"]

    def __str__(self):
        return f"{self.original_name} ({self.issue.key})"


@receiver(post_delete, sender=Attachment)
def remove_file_from_disk(sender, instance, **kwargs):
    """Django does not delete files when a row is deleted (also runs when an issue is deleted)."""
    instance.file.delete(save=False)


class GitHubLink(models.Model):
    """GitHub repository/commit linked to an issue."""
    issue = models.OneToOneField(Issue, on_delete=models.CASCADE, related_name="github_link")
    repository_name = models.CharField(max_length=120)
    repository_url = models.URLField()
    commit_id = models.CharField(max_length=40, blank=True)
    commit_message = models.CharField(max_length=255, blank=True)
    commit_url = models.URLField(blank=True)
    linked_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.issue} -> {self.repository_name}"


class PipelineRun(models.Model):
    """One CI/CD (GitHub Actions) workflow run reported to BugFlow."""
    STATUS_CHOICES = [("running", "Running"), ("success", "Success"), ("failed", "Failed")]

    external_id = models.CharField(max_length=40, unique=True)      # GitHub run id
    run_number = models.PositiveIntegerField()                      # shown as #2457
    workflow_name = models.CharField(max_length=150, default="BugFlow CI/CD Pipeline")
    branch = models.CharField(max_length=100, default="main")
    commit_id = models.CharField(max_length=40, blank=True)
    commit_message = models.CharField(max_length=255, blank=True)
    run_url = models.URLField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="running")
    duration_seconds = models.PositiveIntegerField(default=0)
    # {"push": {"status": "success", "at": "<iso time>"}, "build": {...}, "tests": {...}, "deploy": {...}}
    stages = models.JSONField(default=dict, blank=True)
    issue = models.ForeignKey(Issue, null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="pipeline_runs")
    issue_note = models.CharField(max_length=255, blank=True)
    issue_status_after = models.CharField(max_length=50, blank=True)
    triggered_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-triggered_at", "-id"]

    def __str__(self):
        return f"#{self.run_number} {self.workflow_name} ({self.status})"


class PipelineTest(models.Model):
    run = models.ForeignKey(PipelineRun, on_delete=models.CASCADE, related_name="tests")
    name = models.CharField(max_length=200)
    passed = models.BooleanField(default=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.name} - {'passed' if self.passed else 'failed'}"