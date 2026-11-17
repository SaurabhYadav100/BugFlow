from django import forms
from django.contrib.auth import get_user_model

from core.forms import StyledFormMixin
from .models import Project, Sprint


class ProjectForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Project
        fields = ("name", "description", "manager")
        labels = {"manager": "Project Manager"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["manager"].queryset = get_user_model().objects.filter(role="project_manager", is_active=True)
        self.fields["manager"].empty_label = "Select Project Manager"


class SprintForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Sprint
        fields = ("project", "name", "goal", "start_date", "end_date")
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "end_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def clean(self):
        data = super().clean()
        if data.get("start_date") and data.get("end_date") and data["end_date"] < data["start_date"]:
            self.add_error("end_date", "The end date must be on or after the start date.")
        return data
