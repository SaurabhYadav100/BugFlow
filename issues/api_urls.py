from rest_framework.routers import DefaultRouter

from .api_views import IssueViewSet

# trailing_slash=False so the URL is /api/issues (matches your Postman request)
router = DefaultRouter(trailing_slash=False)
router.register(r"issues", IssueViewSet, basename="issue")

urlpatterns = router.urls
