from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

urlpatterns = [
    path("login/", views.UserLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("welcome/", views.LoginSuccessView.as_view(), name="login_success"),
    path("register/", views.RegisterView.as_view(), name="register"),
    path("users/", views.UserListView.as_view(), name="user_list"),
    path("users/add/", views.UserCreateView.as_view(), name="user_create"),
    path("users/<int:pk>/edit/", views.UserUpdateView.as_view(), name="user_edit"),
    path("users/<int:pk>/delete/", views.UserDeleteView.as_view(), name="user_delete"),
    path("settings/", views.SettingsView.as_view(), name="settings"),
    path("settings/password/", views.ChangePasswordView.as_view(), name="password_change"),
]
