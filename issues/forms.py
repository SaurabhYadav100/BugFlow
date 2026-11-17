import os
from django.core.exceptions import ValidationError

from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q

from core.forms import StyledFormMixin
from .models import Issue

User = get_user_model()

ALLOWED_FILES = {".jpg": b"\xff\xd8\xff", ".jpeg": b"\xff\xd8\xff",
                 ".png": b"\x89PNG\r\n\x1a\n", ".pdf": b"%PDF-"}   # extension -> real file signature
MAX_FILE_SIZE = 5 * 1024 * 1024   # 5 MB each
MAX_FILES = 5


def validate_attachment(f):
    ext = os.path.splitext(f.name)[1].lower()
    if ext not in ALLOWED_FILES:
        raise ValidationError(f"'{f.name}': only JPG, PNG and PDF files are allowed.")
    if f.size > MAX_FILE_SIZE:
        raise ValidationError(f"'{f.name}' is larger than 5 MB.")
    head = f.read(8)
    f.seek(0)
    if not head.startswith(ALLOWED_FILES[ext]):          # a renamed .exe or .txt is rejected here
        raise ValidationError(f"'{f.name}' is not a real {ext[1:].upper()} file.")


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """A file input that accepts several files; clean() returns a list of validated files."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput(attrs={"accept": ".jpg,.jpeg,.png,.pdf"}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        files = [f for f in (data if isinstance(data, (list, tuple)) else [data]) if f]
        if len(files) > MAX_FILES:
            raise ValidationError(f"You can attach at most {MAX_FILES} files at a time.")
        single_clean, cleaned, errors = super().clean, [], []
        for f in files:
            try:
                cleaned.append(single_clean(f, initial))
                validate_attachment(f)
            except ValidationError as exc:
                errors.extend(exc.error_list)
        if errors:
            raise ValidationError(errors)
        return cleaned


class AttachmentUploadForm(forms.Form):
    """Used by the Upload box on the issue page."""
    attachments = MultipleFileField(required=True, label="Attachments")


def developer_queryset(current_assignee_id=None):
    """Developers can be assigned issues; keep the current assignee selectable too."""
    return User.objects.filter(Q(role="developer", is_active=True) | Q(pk=current_assignee_id))


class DeveloperChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.name} ({obj.get_role_display()})"


class IssueForm(StyledFormMixin, forms.ModelForm):
    issue_id = forms.CharField(label="Issue ID", required=False, disabled=True)
    assignee = DeveloperChoiceField(queryset=User.objects.none(), required=False, empty_label="Select Developer", label="Assign To")
    attachments = MultipleFileField(required=False, label="Attachments",
                                    help_text="PNG, JPG or PDF. Max 5 MB each, up to 5 files.")

    class Meta:
        model = Issue
        fields = ("project", "title", "description", "issue_type", "severity", "priority", "module",
                  "assignee", "status", "sprint", "resolution_notes")
        labels = {"issue_type": "Issue Type"}
        widgets={"description":forms.Textarea(attrs={"rows":3}),       #By default row:4
                "resolution_notes":forms.Textarea(attrs={"rows":3}),}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        editing = bool(self.instance.pk)
        self.fields["description"].required = True
        self.fields["project"].empty_label = "Select Project"

        self.fields["module"].choices = [("", "Select Module")] + list(Issue.Module.choices)

        self.fields["sprint"].required = False
        self.fields["sprint"].empty_label = "No sprint"
        self.fields["assignee"].queryset = developer_queryset(self.instance.assignee_id)
        if editing:
            self.fields["issue_id"].initial = self.instance.key
            allowed = self.instance.allowed_statuses(user) if user else [self.instance.status]
            self.fields["status"].choices = [c for c in Issue.Status.choices if c[0] in allowed]
            if user and not user.can_manage:
                self.fields["assignee"].disabled = True  # only Admin / PM reassign
        else:
            del self.fields["issue_id"]
            del self.fields["resolution_notes"]
            self.fields["status"].disabled = True  # new issues always start Open
            self.fields["status"].initial = Issue.Status.OPEN
        order = ["issue_id", "project", "title", "description", "issue_type", "severity", "priority", "module",
                 "assignee", "status", "sprint", "resolution_notes"]
        self.order_fields([f for f in order if f in self.fields])


class QuickUpdateForm(StyledFormMixin, forms.Form):
    """Assign + change status + comment. Used by the Update page, the Assign modal and the status box."""

    assignee = DeveloperChoiceField(queryset=User.objects.none(), required=False, empty_label="Select Developer", label="Assign To")
    status = forms.ChoiceField(required=False, label="Status")
    comment = forms.CharField(required=False, label="Comments", widget=forms.Textarea(attrs={"rows": 4}))

    def __init__(self, *args, issue, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.issue, self.user = issue, user
        self.fields["status"].choices = [(v, l) for v, l in Issue.Status.choices if v in issue.allowed_statuses(user)]
        if user.can_manage:
            self.fields["assignee"].queryset = developer_queryset(issue.assignee_id)
        else:
            del self.fields["assignee"]
        self.initial.update(assignee=issue.assignee_id, status=issue.status)

    def clean(self):
        data = super().clean()
        if not data.get("status"):
            data["status"] = self.issue.status
        if "assignee" in self.fields and "assignee" not in self.data:
            data["assignee"] = self.issue.assignee  # field omitted (e.g. status-only form) -> keep as is
        return data

    def save(self):
        issue, actor, data = self.issue, self.user, self.cleaned_data
        notes = []
        if "assignee" in self.fields:
            new = data["assignee"]
            if (new.pk if new else None) != issue.assignee_id:
                issue.assignee = new
                notes.append(f"Assigned to {new.name}" if new else "Unassigned")
        if data["status"] != issue.status:
            old = issue.get_status_display()
            issue.status = data["status"]
            notes.append(f"Status changed from {old} to {issue.get_status_display()}")
        if notes:
            issue.save()
            for n in notes:
                issue.log(actor, n)
        if data.get("comment", "").strip():
            issue.comments.create(author=actor, body=data["comment"].strip())
        return notes
