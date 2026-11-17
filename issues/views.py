import os
from django.http import FileResponse, Http404

import re

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, FormView, ListView, TemplateView, UpdateView
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

from core.mixins import DeletePageMixin, FormPageMixin, ManagerRequiredMixin, PageMixin, UserPropMixin
from projects.models import Project
from .forms import AttachmentUploadForm, IssueForm, QuickUpdateForm, developer_queryset
from .models import Attachment, Comment, Issue

User = get_user_model()


def safe_next(request, fallback):
    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and url_has_allowed_host_and_scheme(nxt, {request.get_host()}):
        return nxt
    return fallback

def attach_files(issue, files, user):
    """Save validated uploads on an issue and write one history line per file."""
    for f in files or []:
        name = os.path.basename(f.name)[:255]
        issue.attachments.create(file=f, original_name=name, size=f.size, uploaded_by=user)
        issue.log(user, f"Attachment added: {name}")

# ---------------- lists ----------------
class IssueListView(PageMixin, ListView):
    template_name = "issues/issue_list.html"
    context_object_name = "issues"
    page_title = "Issues"
    nav = "issues"
    paginate_by = 10

    def scope(self, qs):
        return qs

    def get_queryset(self):
        qs = self.scope(Issue.objects.select_related("project", "assignee"))
        g = self.request.GET
        for param, field in (("status", "status"), ("priority", "priority"), ("project", "project_id"), ("type", "issue_type")):
            if g.get(param):
                qs = qs.filter(**{field: g[param]})
        q = g.get("q", "").strip()
        if q:
            cond = Q(title__icontains=q) | Q(description__icontains=q)
            m = re.fullmatch(r"([A-Za-z]+)-?(\d+)", q)  # "BUG-002" or "bug2" finds the issue by ID
            if m:
                types = [t for t, p in Issue.KEY_PREFIX.items() if p == m.group(1).upper()]
                if types:
                    cond |= Q(issue_type=types[0], number=int(m.group(2)))
            qs = qs.filter(cond)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        issues = list(ctx["issues"])
        for i in issues:
            i.user_can_edit, i.user_can_update = i.can_edit(user), i.can_update(user)
        params = self.request.GET.copy()
        params.pop("page", None)
        page = ctx.get("page_obj")
        ctx.update(
            issues=issues,
            statuses=Issue.Status.choices, priorities=Issue.Priority.choices, types=Issue.IssueType.choices,
            projects=Project.objects.all(),
            developers=developer_queryset() if user.can_manage else [],
            querystring=params.urlencode(),
            has_filters=any(self.request.GET.get(k) for k in ("q", "project", "type", "status", "priority")),
            page_range=list(ctx["paginator"].get_elided_page_range(page.number, on_each_side=1, on_ends=1)) if page else [],
        )
        return ctx


class MyListView(IssueListView):
    """Developer 'My Issues', Tester 'Reported Issues' and 'My Tests' share one template."""

    template_name = "issues/my_list.html"
    heading = ""
    test_mode = False
    paginate_by = 10

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(page_title=self.heading, heading=self.heading, test_mode=self.test_mode)
        return ctx


class MyIssuesView(MyListView):
    nav, heading = "my_issues", "My Issues"

    def scope(self, qs):
        return qs.filter(assignee=self.request.user)


class ReportedIssuesView(MyListView):
    nav, heading = "reported", "Reported Issues"

    def scope(self, qs):
        return qs.filter(reporter=self.request.user)


class MyTestsView(MyListView):
    nav, heading, test_mode = "my_tests", "My Tests", True

    def scope(self, qs):
        return qs.filter(reporter=self.request.user, status=Issue.Status.TESTING)


class CommentListView(PageMixin, ListView):
    template_name = "issues/comment_list.html"
    context_object_name = "comments"
    page_title = "Comments"
    nav = "comments"
    paginate_by = 15

    def get_queryset(self):
        qs = Comment.objects.select_related("issue", "author").order_by("-created_at")
        u = self.request.user
        if u.can_manage:
            return qs
        return qs.filter(Q(issue__assignee=u) | Q(issue__reporter=u) | Q(author=u)).distinct()


# ---------------- detail ----------------
class IssueDetailView(PageMixin, DetailView):
    model = Issue
    template_name = "issues/issue_detail.html"
    context_object_name = "issue"
    nav = "issues"

    def get_queryset(self):
        return Issue.objects.select_related("project", "assignee", "reporter", "sprint")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        issue, user = self.object, self.request.user
        ctx.update(
            page_title=issue.key,
            comments=issue.comments.select_related("author"),
            history=issue.history.select_related("actor"),
            status_choices=[(v, l) for v, l in Issue.Status.choices if v in issue.allowed_statuses(user)],
            user_can_edit=issue.can_edit(user), user_can_update=issue.can_update(user),
            developers=developer_queryset(issue.assignee_id) if user.can_manage else [],

            attachments=issue.attachments.select_related("uploaded_by"),
            active_tab=self.request.GET.get("tab") if self.request.GET.get("tab") in ("comments", "history", "attachments") else "description",
        )
        return ctx


class IssueCommentView(LoginRequiredMixin, View):
    def post(self, request, pk):
        issue = get_object_or_404(Issue, pk=pk)
        body = request.POST.get("body", "").strip()
        if body:
            issue.comments.create(author=request.user, body=body)
            messages.success(request, "Comment added.")
        else:
            messages.error(request, "Write a comment before posting.")
        return redirect(f"{reverse('issue_detail', args=[pk])}?tab=comments")


# ---------------- create / edit / delete ----------------
class IssueFormUserMixin:
    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["user"] = self.request.user
        return kw


class IssueCreateView(UserPropMixin, IssueFormUserMixin, FormPageMixin, CreateView):
    user_prop = "can_report"
    model = Issue
    form_class = IssueForm
    template_name = "issues/issue_form.html"
    page_title = "Create New Issue"
    nav = "issues"
    submit_label = "Create Issue"
    cancel_url = reverse_lazy("issue_list")
    success_message = "Issue created."

    def get_initial(self):
        initial = super().get_initial()
        for key in ("project", "sprint"):          # e.g. /issues/add/?project=1&sprint=2 from the sprint board
            if self.request.GET.get(key, "").isdigit():
                initial[key] = int(self.request.GET[key])
        return initial
        
    def get_nav(self):
        return "reported" if self.request.user.is_tester else "issues"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["nav"] = self.get_nav()
        return ctx

    def form_valid(self, form):
        form.instance.reporter = self.request.user
        response = super().form_valid(form)
        self.object.log(self.request.user, "Issue created")
        if self.object.assignee:
            self.object.log(self.request.user, f"Assigned to {self.object.assignee.name}")

        attach_files(self.object, form.cleaned_data.get("attachments"), self.request.user)
        return response


    def get_success_url(self):
        return reverse("issue_detail", args=[self.object.pk])


class IssueUpdateView(IssueFormUserMixin, FormPageMixin, UserPassesTestMixin, UpdateView):
    model = Issue
    form_class = IssueForm
    template_name = "issues/issue_form.html"
    page_title = "Edit Issue"
    nav = "issues"
    submit_label = "Update Issue"
    success_message = "Issue updated."

    def test_func(self):
        return self.get_object().can_edit(self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["cancel_url"] = reverse("issue_detail", args=[self.object.pk])
        return ctx

    
    def form_valid(self, form):
        old = Issue.objects.get(pk=self.object.pk)

        response = super().form_valid(form)

        user = self.request.user
        other = []

        for name in form.changed_data:
            if name == "status":
                self.object.log(
                user,
                f"Status changed from {old.get_status_display()} "
                f"to {self.object.get_status_display()}"
                )

            elif name == "assignee":
                a = self.object.assignee
                self.object.log(
                user,
                f"Assigned to {a.name}" if a else "Unassigned"
                )

            elif name != "attachments":
                other.append(form.fields[name].label or name)

        if other:
            self.object.log(
            user,
            "Updated " + ", ".join(other)
            )

        # Upload files only when a new file was actually selected
        files = self.request.FILES.getlist("attachments")
        if files:
            attach_files(self.object, files, user)

        return response

    def get_success_url(self):
        return reverse("issue_detail", args=[self.object.pk])


class IssueQuickUpdateView(PageMixin, FormView):
    """'Update Issue' page; also the target of the Assign modal and the status box on the detail page."""

    form_class = QuickUpdateForm
    template_name = "issues/issue_quick_update.html"
    page_title = "Update Issue"
    nav = "issues"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        self.issue = get_object_or_404(Issue, pk=kwargs["pk"])
        if not self.issue.can_update(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw.update(issue=self.issue, user=self.request.user)
        return kw

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(issue=self.issue, cancel_url=reverse("issue_detail", args=[self.issue.pk]))
        return ctx

    def form_valid(self, form):
        notes = form.save()
        messages.success(self.request, "Issue updated." if notes else "No changes to save.")
        return redirect(safe_next(self.request, reverse("issue_detail", args=[self.issue.pk])))

    def form_invalid(self, form):
        messages.error(self.request, "Couldn't update the issue. Check the values and try again.")
        if "next" in self.request.POST:
            return redirect(safe_next(self.request, reverse("issue_detail", args=[self.issue.pk])))
        return super().form_invalid(form)


class IssueDeleteView(ManagerRequiredMixin, DeletePageMixin, DeleteView):
    model = Issue
    page_title = "Delete issue"
    nav = "issues"
    cancel_url = reverse_lazy("issue_list")
    success_url = reverse_lazy("issue_list")
    success_message = "Issue deleted."


class IssueBulkDeleteView(ManagerRequiredMixin, View):
    def post(self, request):
        ids = [i for i in request.POST.getlist("ids") if i.isdigit()]
        deleted, _ = Issue.objects.filter(pk__in=ids).delete() if ids else (0, None)
        if ids:
            messages.success(request, f"{len(ids)} issue(s) deleted.")
        return redirect(safe_next(request, reverse("issue_list")))


class IssueAttachView(LoginRequiredMixin, View):
    """The Upload box on the issue page."""

    def post(self, request, pk):
        issue = get_object_or_404(Issue, pk=pk)
        form = AttachmentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            attach_files(issue, form.cleaned_data["attachments"], request.user)
            messages.success(request, "File uploaded.")
        else:
            for errs in form.errors.values():
                for e in errs:
                    messages.error(request, e)
        return redirect(f"{reverse('issue_detail', args=[pk])}?tab=attachments")


class AttachmentDownloadView(LoginRequiredMixin, View):
    """Files are only ever served to signed-in users, and always as a download."""

    def get(self, request, pk):
        att = get_object_or_404(Attachment, pk=pk)
        try:
            handle = att.file.open("rb")
        except FileNotFoundError:
            raise Http404("This file is missing from the server.")
        return FileResponse(handle, as_attachment=True, filename=att.original_name)


class AttachmentDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        att = get_object_or_404(Attachment, pk=pk)
        if not (request.user.can_manage or att.uploaded_by_id == request.user.id):
            raise PermissionDenied
        issue, name = att.issue, att.original_name
        att.delete()
        issue.log(request.user, f"Attachment removed: {name}")
        messages.success(request, "Attachment removed.")
        return redirect(f"{reverse('issue_detail', args=[issue.pk])}?tab=attachments")