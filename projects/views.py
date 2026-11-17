from django.db.models import Count
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from core.mixins import DeletePageMixin, FormPageMixin, ManagerRequiredMixin, PageMixin
from .forms import ProjectForm
from .models import Project


class ProjectListView(PageMixin, ListView):
    model = Project
    template_name = "projects/project_list.html"
    context_object_name = "projects"
    page_title = "Projects"
    nav = "projects"

    def get_queryset(self):
        return Project.objects.select_related("manager").annotate(issue_count=Count("issues", distinct=True))


class ProjectCreateView(ManagerRequiredMixin, FormPageMixin, CreateView):
    model = Project
    form_class = ProjectForm
    page_title = "Add project"
    nav = "projects"
    submit_label = "Add project"
    cancel_url = reverse_lazy("project_list")
    success_url = reverse_lazy("project_list")
    success_message = "Project added."


class ProjectUpdateView(ManagerRequiredMixin, FormPageMixin, UpdateView):
    model = Project
    form_class = ProjectForm
    page_title = "Edit project"
    nav = "projects"
    cancel_url = reverse_lazy("project_list")
    success_url = reverse_lazy("project_list")
    success_message = "Project updated."


class ProjectDeleteView(ManagerRequiredMixin, DeletePageMixin, DeleteView):
    model = Project
    page_title = "Delete project"
    nav = "projects"
    cancel_url = reverse_lazy("project_list")
    success_url = reverse_lazy("project_list")
    success_message = "Project deleted."


# ---------------- Sprints (Project Managers and Admins) ----------------
from collections import Counter  # noqa: E402

from django.contrib import messages  # noqa: E402
from django.db.models import Q  # noqa: E402
from django.shortcuts import get_object_or_404, redirect  # noqa: E402
from django.urls import reverse  # noqa: E402
from django.utils.http import url_has_allowed_host_and_scheme  # noqa: E402
from django.views import View  # noqa: E402
from django.views.generic import DetailView  # noqa: E402

from issues.models import Issue  # noqa: E402
from .forms import SprintForm  # noqa: E402
from .models import Sprint  # noqa: E402

FINISHED = ("resolved", "closed")
# Board columns: key, title, issue statuses shown in it, Bootstrap colour
BOARD_COLUMNS = [
    ("todo", "To Do", ("open",), "primary"),
    ("progress", "In Progress", ("in_progress", "testing"), "warning"),
    ("done", "Done", ("resolved", "closed"), "success"),
]


def back_to(request, fallback):
    nxt = request.POST.get("next")
    return nxt if nxt and url_has_allowed_host_and_scheme(nxt, {request.get_host()}) else fallback


class SprintListView(ManagerRequiredMixin, PageMixin, ListView):
    template_name = "projects/sprint_list.html"
    context_object_name = "sprints"
    page_title = "Sprints"
    nav = "sprints"

    def get_queryset(self):
        return Sprint.objects.select_related("project").annotate(
            issue_count=Count("issues", distinct=True),
            done_count=Count("issues", filter=Q(issues__status__in=FINISHED), distinct=True))


class SprintDetailView(ManagerRequiredMixin, PageMixin, DetailView):
    """Sprint header + the board (backlog | To Do | In Progress | Done), a backlog tab and a details tab."""

    template_name = "projects/sprint_detail.html"
    context_object_name = "sprint"
    nav = "sprints"

    def get_queryset(self):
        return Sprint.objects.select_related("project", "project__manager")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sprint, user = self.object, self.request.user
        labels = dict(Issue.Status.choices)
        issues = list(sprint.issues.select_related("assignee"))
        for i in issues:   # the "Move to ..." menu offers only moves the workflow allows for this user
            i.move_options = [(v, labels[v]) for v in i.allowed_statuses(user) if v != i.status] if i.can_update(user) else []
        columns = [{"key": k, "title": t, "colour": c, "issues": [i for i in issues if i.status in st]} for k, t, st, c in BOARD_COLUMNS]
        by_col = {c["key"]: len(c["issues"]) for c in columns}
        types = dict(Issue.IssueType.choices)
        counts = Counter(i.issue_type for i in issues)
        ctx.update(
            page_title=sprint.name, columns=columns,
            stats={"total": len(issues), "completed": by_col["done"], "in_progress": by_col["progress"], "remaining": by_col["todo"]},
            backlog=list(Issue.objects.filter(project=sprint.project, sprint__isnull=True).exclude(status__in=FINISHED)
                         .select_related("assignee")[:100]),
            by_type=[(label, counts[t]) for t, label in types.items() if counts[t]],
            active_tab=self.request.GET.get("tab") if self.request.GET.get("tab") in ("backlog", "details") else "board",
        )
        return ctx


class SprintAssignView(ManagerRequiredMixin, View):
    """'Add to Sprint' (one issue) and 'Assign to Sprint' (ticked issues on the Backlog tab)."""

    def post(self, request, pk):
        sprint = get_object_or_404(Sprint, pk=pk)
        ids = {i for i in request.POST.getlist("ids") if i.isdigit()}
        issues = list(Issue.objects.filter(pk__in=ids, project=sprint.project, sprint__isnull=True))
        for issue in issues:
            issue.sprint = sprint
            issue.save(update_fields=["sprint", "updated_at"])
            issue.log(request.user, f"Added to {sprint.name}")
        if not ids:
            messages.error(request, "Tick at least one issue first.")
        elif issues:
            messages.success(request, f"{len(issues)} issue(s) added to {sprint.name}.")
        if ids and len(issues) < len(ids):
            messages.warning(request, "Some issues were skipped: they belong to another project or are already in a sprint.")
        return redirect(back_to(request, reverse("sprint_detail", args=[pk])))


class SprintRemoveView(ManagerRequiredMixin, View):
    """Take an issue out of the sprint; it goes back to the backlog."""

    def post(self, request, pk, issue_pk):
        sprint = get_object_or_404(Sprint, pk=pk)
        issue = get_object_or_404(Issue, pk=issue_pk, sprint=sprint)
        issue.sprint = None
        issue.save(update_fields=["sprint", "updated_at"])
        issue.log(request.user, f"Removed from {sprint.name}")
        messages.success(request, f"{issue.key} moved back to the backlog.")
        return redirect(back_to(request, reverse("sprint_detail", args=[pk])))


class SprintCreateView(ManagerRequiredMixin, FormPageMixin, CreateView):
    model = Sprint
    form_class = SprintForm
    page_title = "Create Sprint"
    nav = "sprints"
    submit_label = "Create Sprint"
    cancel_url = reverse_lazy("sprint_list")
    success_message = "Sprint created. Add issues from the backlog."

    def get_success_url(self):
        return reverse("sprint_detail", args=[self.object.pk])


class SprintUpdateView(ManagerRequiredMixin, FormPageMixin, UpdateView):
    model = Sprint
    form_class = SprintForm
    page_title = "Edit Sprint"
    nav = "sprints"
    cancel_url = reverse_lazy("sprint_list")
    success_message = "Sprint updated."

    def get_success_url(self):
        return reverse("sprint_detail", args=[self.object.pk])


class SprintDeleteView(ManagerRequiredMixin, DeletePageMixin, DeleteView):
    model = Sprint
    page_title = "Delete sprint"
    nav = "sprints"
    cancel_url = reverse_lazy("sprint_list")
    success_url = reverse_lazy("sprint_list")
    success_message = "Sprint deleted. Its issues are back in the backlog."
