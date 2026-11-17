from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.messages.views import SuccessMessageMixin


class AdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Only users with the Admin role."""

    def test_func(self):
        return self.request.user.is_admin_role


class UserPropMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Allow access when `request.user.<user_prop>` is true (see accounts.models.User)."""

    user_prop = "can_manage"

    def test_func(self):
        return bool(getattr(self.request.user, self.user_prop))


class ManagerRequiredMixin(UserPropMixin):
    """Admins and Project Managers."""

    user_prop = "can_manage"


class PageMixin(LoginRequiredMixin):
    """Gives every page a title and the active sidebar key."""

    page_title = ""
    nav = ""

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(page_title=self.page_title, nav=self.nav)
        return ctx


class FormPageMixin(PageMixin, SuccessMessageMixin):
    """Shared behaviour for create/update pages using templates/crud/form.html."""

    template_name = "crud/form.html"
    submit_label = "Save"
    cancel_url = "/"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(submit_label=self.submit_label, cancel_url=self.cancel_url)
        return ctx


class DeletePageMixin(PageMixin):
    """Shared behaviour for delete pages using templates/crud/confirm_delete.html."""

    template_name = "crud/confirm_delete.html"
    cancel_url = "/"
    success_message = "Deleted."

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["cancel_url"] = self.cancel_url
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        from django.contrib import messages
        messages.success(self.request, self.success_message)
        return response
