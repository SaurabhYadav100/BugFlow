from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import Issue
from .serializers import IssueSerializer


class IssueViewSet(viewsets.ModelViewSet):
    """
    GET     /api/issues        -> list all issues
    POST    /api/issues        -> create an issue
    GET     /api/issues/<id>   -> retrieve one issue
    PUT     /api/issues/<id>   -> full update
    PATCH   /api/issues/<id>   -> partial update
    DELETE  /api/issues/<id>   -> delete an issue
    """

    queryset = Issue.objects.all().order_by("-id")
    serializer_class = IssueSerializer
    permission_classes = [IsAuthenticated]

    # If your Issue model has a reporter/created_by field, uncomment:
    # def perform_create(self, serializer):
    #     serializer.save(reporter=self.request.user)
