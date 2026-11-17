from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from issues.models import Comment, Issue
from projects.models import Project, Sprint

User = get_user_model()


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        mk = lambda e, n, r: User.objects.create_user(e, "Password@123", name=n, role=r)
        cls.admin = mk("admin@bugflow.com", "Admin", "admin")
        cls.pm = mk("pm@bugflow.com", "Arun S", "project_manager")
        cls.dev = mk("dev@bugflow.com", "Ravi Kumar", "developer")
        cls.dev2 = mk("dev2@bugflow.com", "Kartik P", "developer")
        cls.tester = mk("tester@bugflow.com", "Priya Sharma", "tester")
        cls.project = Project.objects.create(name="Shop", manager=cls.pm)
        cls.other_project = Project.objects.create(name="Other")
        make = lambda title, t, s, **kw: Issue.objects.create(
            project=cls.project, title=title, issue_type=t, status=s, reporter=cls.tester, assignee=cls.dev, **kw)
        cls.open_bug = make("Login broken", "bug", "open")
        cls.progress_bug = make("Payment failure", "bug", "in_progress")
        cls.feature = make("Dark mode", "feature", "open")
        cls.testing_bug = make("Crash", "bug", "testing")
        cls.resolved_bug = make("Wrong total", "bug", "resolved")
        Issue.objects.create(project=cls.other_project, title="Elsewhere", reporter=cls.admin)


class AuthTests(Base):
    def test_login_required(self):
        for name in ("dashboard", "issue_list", "project_list", "reports", "my_issues", "comment_list"):
            r = self.client.get(reverse(name))
            self.assertEqual(r.status_code, 302, name)
            self.assertIn("/login/", r["Location"])

    def test_login_lands_on_success_page_with_role(self):
        r = self.client.post(reverse("login"), {"username": "dev@bugflow.com", "password": "Password@123", "remember": "on"})
        self.assertRedirects(r, reverse("login_success"))
        page = self.client.get(reverse("login_success"))
        self.assertContains(page, "Login Successful!")
        self.assertContains(page, "Developer")

    def test_bad_login(self):
        self.assertContains(self.client.post(reverse("login"), {"username": "dev@bugflow.com", "password": "no"}), "incorrect")

    def test_register_creates_developer(self):
        r = self.client.post(reverse("register"), {"name": "New", "email": "new@x.com",
                                                    "password1": "Str0ng!pass99", "password2": "Str0ng!pass99"})
        self.assertRedirects(r, reverse("login_success"))
        self.assertEqual(User.objects.get(email="new@x.com").role, "developer")

    def test_register_password_mismatch(self):
        r = self.client.post(reverse("register"), {"name": "N", "email": "n@x.com", "password1": "Str0ng!pass99", "password2": "other"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.filter(email="n@x.com").exists())

    def test_logout_post(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("logout"))
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)


class RoleDashboardTests(Base):
    def dash(self, user):
        self.client.force_login(user)
        return self.client.get(reverse("dashboard"))

    def test_admin(self):
        r = self.dash(self.admin)
        self.assertEqual(r.context["role"], "admin")
        self.assertEqual([s["value"] for s in r.context["stats"]], [6, 3, 1, 1])
        self.assertContains(r, "Recent Users")

    def test_project_manager(self):
        r = self.dash(self.pm)
        self.assertEqual(r.context["heading"], "Project Manager Dashboard")
        self.assertEqual([s["value"] for s in r.context["stats"]], [1, 5, 2, 1])  # only their project's issues
        self.assertContains(r, "Project Overview")

    def test_developer(self):
        r = self.dash(self.dev)
        self.assertEqual([s["label"] for s in r.context["stats"]], ["Assigned Issues", "In Progress", "Resolved", "Closed"])
        self.assertContains(r, "My Assigned Issues")

    def test_tester(self):
        r = self.dash(self.tester)
        self.assertEqual(r.context["heading"], "Tester Dashboard")
        self.assertEqual(r.context["stats"][1]["value"], 1)  # Testing
        self.assertContains(r, "Recent Reported Issues")

    def test_sidebar_is_role_based(self):
        self.assertContains(self.dash(self.dev), "My Issues")
        self.assertNotContains(self.dash(self.dev), ">Users<")
        self.assertContains(self.dash(self.pm), "Sprints")
        self.assertContains(self.dash(self.tester), "My Tests")
        r = self.dash(self.admin)
        self.assertContains(r, ">Users<")
        self.assertContains(r, ">Database<")
        self.assertContains(r, "Logout")


class PermissionTests(Base):
    def status(self, user, name, *args):
        self.client.force_login(user)
        return self.client.get(reverse(name, args=args)).status_code

    def test_users_admin_only(self):
        self.assertEqual(self.status(self.admin, "user_list"), 200)
        for u in (self.pm, self.dev, self.tester):
            self.assertEqual(self.status(u, "user_list"), 403)

    def test_database_admin_only(self):
        self.assertEqual(self.status(self.admin, "database"), 200)
        self.assertEqual(self.status(self.pm, "database"), 403)

    def test_sprints_managers_only(self):
        self.assertEqual(self.status(self.pm, "sprint_list"), 200)
        self.assertEqual(self.status(self.dev, "sprint_list"), 403)

    def test_projects_view_for_all_manage_for_managers(self):
        self.assertEqual(self.status(self.dev, "project_list"), 200)
        self.assertEqual(self.status(self.dev, "project_create"), 403)
        self.assertEqual(self.status(self.pm, "project_create"), 200)

    def test_reports_not_for_developers(self):
        self.assertEqual(self.status(self.dev, "reports"), 403)
        self.assertEqual(self.status(self.tester, "reports"), 200)

    def test_developer_cannot_create_issue(self):
        self.assertEqual(self.status(self.dev, "issue_create"), 403)
        for u in (self.admin, self.pm, self.tester):
            self.assertEqual(self.status(u, "issue_create"), 200)

    def test_edit_and_delete_rules(self):
        i = self.open_bug.pk
        self.assertEqual(self.status(self.dev, "issue_edit", i), 403)      # assignee may only update status
        self.assertEqual(self.status(self.tester, "issue_edit", i), 200)   # reporter
        self.assertEqual(self.status(self.pm, "issue_edit", i), 200)
        self.assertEqual(self.status(self.dev, "issue_delete", i), 403)
        self.assertEqual(self.status(self.tester, "issue_delete", i), 403)

    def test_only_involved_users_can_update(self):
        self.assertEqual(self.status(self.dev, "issue_update", self.open_bug.pk), 200)
        self.assertEqual(self.status(self.dev2, "issue_update", self.open_bug.pk), 403)


class IssueFlowTests(Base):
    def test_keys_per_type(self):
        self.assertEqual(self.open_bug.key, "BUG-001")
        self.assertEqual(self.feature.key, "FEAT-001")
        self.assertEqual(self.resolved_bug.key, "BUG-004")

    def test_create_issue(self):
        self.client.force_login(self.tester)
        r = self.client.post(reverse("issue_create"), {
            "project": self.project.pk, "title": "New bug", "description": "It breaks", "issue_type": "support",
            "severity": "high", "priority": "high", "assignee": self.dev.pk})
        issue = Issue.objects.get(title="New bug")
        self.assertRedirects(r, reverse("issue_detail", args=[issue.pk]))
        self.assertEqual((issue.key, issue.reporter, issue.status), ("SUP-001", self.tester, "open"))
        self.assertTrue(issue.history.filter(text="Issue created").exists())

    def test_description_required(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse("issue_create"), {"project": self.project.pk, "title": "x", "issue_type": "bug",
                                                       "severity": "low", "priority": "low"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Issue.objects.filter(title="x").exists())

    def test_assign_via_modal_endpoint(self):
        self.client.force_login(self.pm)
        self.client.post(reverse("issue_update", args=[self.open_bug.pk]),
                         {"assignee": self.dev2.pk, "comment": "Please check gateway logs", "next": "/issues/"})
        self.open_bug.refresh_from_db()
        self.assertEqual(self.open_bug.assignee, self.dev2)
        self.assertTrue(self.open_bug.history.filter(text="Assigned to Kartik P").exists())
        self.assertEqual(Comment.objects.filter(issue=self.open_bug).count(), 1)

    def test_status_only_form_keeps_assignee(self):
        self.client.force_login(self.pm)
        self.client.post(reverse("issue_update", args=[self.open_bug.pk]), {"status": "in_progress"})
        self.open_bug.refresh_from_db()
        self.assertEqual((self.open_bug.status, self.open_bug.assignee), ("in_progress", self.dev))
        self.assertTrue(self.open_bug.history.filter(text="Status changed from Open to In Progress").exists())

    def test_workflow_blocks_skipping_steps(self):
        self.client.force_login(self.pm)
        self.client.post(reverse("issue_update", args=[self.open_bug.pk]), {"status": "resolved"})
        self.open_bug.refresh_from_db()
        self.assertEqual(self.open_bug.status, "open")

    def test_developer_can_move_to_testing_but_not_resolve(self):
        self.client.force_login(self.dev)
        self.client.post(reverse("issue_update", args=[self.progress_bug.pk]), {"status": "testing"})
        self.progress_bug.refresh_from_db()
        self.assertEqual(self.progress_bug.status, "testing")
        self.client.post(reverse("issue_update", args=[self.progress_bug.pk]), {"status": "resolved"})
        self.progress_bug.refresh_from_db()
        self.assertEqual(self.progress_bug.status, "testing")

    def test_tester_pass_resolves(self):
        self.client.force_login(self.tester)
        self.client.post(reverse("issue_update", args=[self.testing_bug.pk]), {"status": "resolved"})
        self.testing_bug.refresh_from_db()
        self.assertEqual(self.testing_bug.status, "resolved")
        self.assertIsNotNone(self.testing_bug.resolved_at)

    def test_delete_and_bulk_delete(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("issue_delete", args=[self.feature.pk]))
        self.assertFalse(Issue.objects.filter(pk=self.feature.pk).exists())
        self.client.post(reverse("issue_bulk_delete"), {"ids": [self.open_bug.pk, self.progress_bug.pk]})
        self.assertEqual(Issue.objects.filter(pk__in=[self.open_bug.pk, self.progress_bug.pk]).count(), 0)

    def test_comments(self):
        self.client.force_login(self.dev)
        self.client.post(reverse("issue_comment", args=[self.open_bug.pk]), {"body": "On it"})
        self.assertEqual(self.open_bug.comments.get().author, self.dev)
        self.assertContains(self.client.get(reverse("issue_detail", args=[self.open_bug.pk])), "On it")
        self.assertContains(self.client.get(reverse("comment_list")), "On it")

    def test_detail_tabs_and_history(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("issue_detail", args=[self.open_bug.pk]))
        for text in ("Description", "Comments", "History", "Update Status", "Created Date", "Updated Date"):
            self.assertContains(r, text)

    def test_edit_logs_changes(self):
        self.client.force_login(self.pm)
        self.client.post(reverse("issue_edit", args=[self.open_bug.pk]), {
            "project": self.project.pk, "title": "Login broken v2", "description": "d", "issue_type": "bug",
            "severity": "high", "priority": "critical", "assignee": self.dev.pk, "status": "open"})
        self.assertTrue(self.open_bug.history.filter(text__startswith="Updated").exists())

    def test_search_by_id_title_and_filters(self):
        self.client.force_login(self.admin)
        get = lambda **p: [i.pk for i in self.client.get(reverse("issue_list"), p).context["issues"]]
        self.assertEqual(get(q="BUG-001"), [self.open_bug.pk])
        self.assertEqual(get(q="feat-1"), [self.feature.pk])
        self.assertEqual(get(q="payment"), [self.progress_bug.pk])
        self.assertEqual(len(get(type="bug")), 5)
        self.assertEqual(len(get(status="open", project=self.project.pk)), 2)

    def test_my_lists(self):
        self.client.force_login(self.dev)
        self.assertEqual(len(self.client.get(reverse("my_issues")).context["issues"]), 5)
        self.client.force_login(self.tester)
        self.assertEqual(len(self.client.get(reverse("reported_issues")).context["issues"]), 5)
        self.assertEqual([i.pk for i in self.client.get(reverse("my_tests")).context["issues"]], [self.testing_bug.pk])


class ReportAndPageTests(Base):
    def test_reports_page_and_types(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("reports"), {"type": "open"})
        self.assertEqual(r.context["total"], 3)
        self.assertContains(r, "Issues by Type")
        self.assertContains(r, "Export PDF")

    def test_report_scope_for_tester_and_pm(self):
        self.client.force_login(self.tester)
        self.assertEqual(self.client.get(reverse("reports")).context["total"], 5)
        self.client.force_login(self.pm)
        self.assertEqual(self.client.get(reverse("reports")).context["total"], 5)

    def test_pdf_export(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("report_export"), {"type": "summary"})
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertTrue(b"".join(r.streaming_content if r.streaming else [r.content]).startswith(b"%PDF"))
        self.client.force_login(self.dev)
        self.assertEqual(self.client.get(reverse("report_export")).status_code, 403)

    def test_all_pages_render_for_admin(self):
        self.client.force_login(self.admin)
        names = ["dashboard", "issue_list", "project_list", "user_list", "reports", "settings", "issue_create", "project_create",
                 "user_create", "database", "database_status", "password_change", "sprint_list", "sprint_create",
                 "my_issues", "reported_issues", "my_tests", "comment_list", "login_success"]
        for name in names:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        for tab in ("users", "projects", "issues", "workflow"):
            self.assertEqual(self.client.get(reverse("database"), {"tab": tab}).status_code, 200, tab)
        self.assertContains(self.client.get(reverse("database_status")), "Database Connected Successfully!")

    def test_sprint_crud(self):
        self.client.force_login(self.pm)
        r = self.client.post(reverse("sprint_create"), {"project": self.project.pk, "name": "S1", "goal": "g",
                                                         "start_date": "2025-05-01", "end_date": "2025-05-14"})
        self.assertRedirects(r, reverse("sprint_list"))
        bad = self.client.post(reverse("sprint_create"), {"project": self.project.pk, "name": "S2",
                                                           "start_date": "2025-05-10", "end_date": "2025-05-01"})
        self.assertContains(bad, "end date")
        self.assertEqual(Sprint.objects.count(), 1)

    def test_admin_cannot_delete_self(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("user_delete", args=[self.admin.pk]))
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())
