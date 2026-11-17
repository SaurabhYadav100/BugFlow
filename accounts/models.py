from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("Email is required")
        user = self.model(email=self.normalize_email(email), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("role", User.Role.ADMIN)
        return self._create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        DEVELOPER = "developer", "Developer"
        TESTER = "tester", "Tester"
        PROJECT_MANAGER = "project_manager", "Project Manager"
        ADMIN = "admin", "Admin"

    name = models.CharField(max_length=120)
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.DEVELOPER)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    objects = UserManager()
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.name

    @property
    def initial(self):
        return (self.name or self.email)[:1].upper()

    @property
    def is_admin_role(self):
        return self.is_superuser or self.role == self.Role.ADMIN

    @property
    def role_key(self):
        """'admin', 'project_manager', 'developer' or 'tester' (superusers count as admin)."""
        return "admin" if self.is_admin_role else self.role

    @property
    def is_pm(self):
        return self.role == self.Role.PROJECT_MANAGER

    @property
    def is_developer(self):
        return self.role == self.Role.DEVELOPER

    @property
    def is_tester(self):
        return self.role == self.Role.TESTER

    @property
    def can_manage(self):
        """Admins and Project Managers: manage projects, assign and delete issues."""
        return self.is_admin_role or self.is_pm

    @property
    def can_report(self):
        """Who may create issues: Admin, Project Manager, Tester (not Developers)."""
        return self.can_manage or self.is_tester

    @property
    def can_view_reports(self):
        return not self.is_developer
