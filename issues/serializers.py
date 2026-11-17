from rest_framework import serializers

from .models import Issue


class IssueSerializer(serializers.ModelSerializer):
    class Meta:
        model = Issue
        fields = "__all__"
        # If your model has fields set automatically (e.g. created_at, reporter),
        # list them here so clients can't overwrite them:
        # read_only_fields = ["id", "created_at", "updated_at", "reporter"]
