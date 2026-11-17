from django import forms


class StyledFormMixin:
    """Gives every widget the right Bootstrap 5 class and marks invalid fields."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                css = "form-check-input"
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                css = "form-select"
            else:
                css = "form-control"
            widget.attrs["class"] = f'{widget.attrs.get("class", "")} {css}'.strip()
            if isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("rows", 4)

    def full_clean(self):
        super().full_clean()
        for name in self.errors:
            if name in self.fields:
                w = self.fields[name].widget
                if "is-invalid" not in w.attrs.get("class", ""):
                    w.attrs["class"] = f'{w.attrs.get("class", "")} is-invalid'.strip()
