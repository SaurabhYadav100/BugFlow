from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, UserCreationForm

from core.forms import StyledFormMixin
from .models import User


class LoginForm(AuthenticationForm):
    username = forms.EmailField(
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "Email address", "autofocus":True , "autocomplete": "email"})
    )
    password = forms.CharField(
        strip=False,
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Password", "autocomplete": "current-password"}),
    )


class RegisterForm(StyledFormMixin, UserCreationForm):
    class Meta:
        model = User
        fields = ("name", "email")
        labels = {"name": "Full Name", "email": "Email Address"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].widget.attrs.pop("autofocus", None)
        self.fields["name"].widget.attrs["autofocus"]=True
        self.fields["password1"].label = "Password"
        self.fields["password1"].help_text = ""
        self.fields["password2"].label = "Confirm Password"
        self.fields["password2"].help_text = ""
        for name, text in (("name", "Enter your full name"), ("email", "Enter your email"),
                           ("password1", "Create a password"), ("password2", "Re-enter your password")):
            self.fields[name].widget.attrs["placeholder"] = text


class UserForm(StyledFormMixin, forms.ModelForm):
    """Used by admins to add / edit users."""

    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Set a password for the new user",
    )

    class Meta:
        model = User
        fields = ("name", "email", "role", "is_active")

    def clean_password(self):
        pwd = self.cleaned_data.get("password")
        if not self.instance.pk and not pwd:
            raise forms.ValidationError("Set a password for the new user.")
        return pwd

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data.get("password"):
            user.set_password(self.cleaned_data["password"])     
        if commit:
            user.save()
        return user


class ProfileForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ("name", "email")


class StyledPasswordChangeForm(StyledFormMixin, PasswordChangeForm):
    pass
