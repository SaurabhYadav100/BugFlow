from django.contrib import messages
from django.contrib.auth import login
from django.shortcuts import redirect
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin

from core.mixins import AdminRequiredMixin, DeletePageMixin, FormPageMixin, PageMixin
from .forms import LoginForm, ProfileForm, RegisterForm, StyledPasswordChangeForm, UserForm
from .models import User


class UserLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        if not self.request.POST.get("remember"):
            self.request.session.set_expiry(0)  # expire when the browser closes
        return response


class RegisterView(CreateView):
    template_name = "accounts/register.html"
    form_class = RegisterForm
    success_url = reverse_lazy("login_success")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.save()
        login(self.request, user)
        return redirect(self.success_url)


class LoginSuccessView(LoginRequiredMixin, TemplateView):
    """'Login Successful!' screen: shows the role the system identified before opening the dashboard."""

    template_name = "accounts/login_success.html"


# ---- User management (list for everyone, changes for admins) ----
class UserListView(AdminRequiredMixin, PageMixin, ListView):
    model = User
    template_name = "accounts/user_list.html"
    context_object_name = "users"
    page_title = "Users"
    nav = "users"


class UserCreateView(AdminRequiredMixin, FormPageMixin, CreateView):
    model = User
    form_class = UserForm
    page_title = "Add user"
    nav = "users"
    submit_label = "Add user"
    cancel_url = reverse_lazy("user_list")
    success_url = reverse_lazy("user_list")
    success_message = "User added."


class UserUpdateView(AdminRequiredMixin, FormPageMixin, UpdateView):
    model = User
    form_class = UserForm
    page_title = "Edit user"
    nav = "users"
    cancel_url = reverse_lazy("user_list")
    success_url = reverse_lazy("user_list")
    success_message = "User updated."


class UserDeleteView(AdminRequiredMixin, DeletePageMixin, DeleteView):
    model = User
    page_title = "Delete user"
    nav = "users"
    cancel_url = reverse_lazy("user_list")
    success_url = reverse_lazy("user_list")
    success_message = "User deleted."

    def form_valid(self, form):
        if self.object == self.request.user:
            messages.error(self.request, "You can't delete your own account.")
            return redirect(self.success_url)
        return super().form_valid(form)


# ---- Own profile ----
class SettingsView(FormPageMixin, UpdateView):
    form_class = ProfileForm
    page_title = "Settings"
    nav = "settings"
    template_name = "accounts/settings.html"
    success_url = reverse_lazy("settings")
    success_message = "Profile updated."

    def get_object(self, queryset=None):
        return self.request.user


class ChangePasswordView(FormPageMixin, PasswordChangeView):
    form_class = StyledPasswordChangeForm
    page_title = "Change password"
    nav = "settings"
    submit_label = "Update password"
    cancel_url = reverse_lazy("settings")
    success_url = reverse_lazy("settings")
    success_message = "Password updated."
