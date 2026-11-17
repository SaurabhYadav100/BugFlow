from django.utils import timezone

from django.conf import settings
from django.db import models


class Project(models.Model):
    name = models.CharField(max_length=150, unique=True)
    description = models.CharField(max_length=300, blank=True)
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="managed_projects"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.name


class Sprint(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="sprints")
    name = models.CharField(max_length=100)
    goal = models.CharField(max_length=300, blank=True)
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        ordering = ["-start_date", "-id"]

    def __str__(self):
        return f"{self.project.name} - {self.name}"

    @property
    def state(self):
        """planned / active / completed, worked out from today's date (nothing to keep in sync)."""
        today = timezone.localdate()
        if today < self.start_date:
            return "planned"
        return "completed" if today > self.end_date else "active"

    @property
    def duration_days(self):
        return (self.end_date - self.start_date).days + 1

    @property
    def duration_label(self):
        d = self.duration_days
        return f"{d // 7} Week{'s' if d // 7 != 1 else ''}" if d % 7 == 0 else f"{d} Days"
