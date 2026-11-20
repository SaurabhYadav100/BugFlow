from django.contrib import admin
from django.urls import include, path

from issues.analytics_views import analytics_view
from issues.github_views import github_view
from issues.cicd_views import cicd_view, cicd_webhook

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
    path("", include("projects.urls")),
    path("", include("issues.urls")),
    path("", include("core.urls")),
    path("api/", include("issues.api_urls")),
    path("analytics/", analytics_view, name="analytics"), 
    path("github/", github_view, name="github"),
    path("github/<int:issue_id>/", github_view, name="github_issue"),
    path("cicd/", cicd_view, name="cicd"),
    path("cicd/<int:run_id>/", cicd_view, name="cicd_run"),
    path("api/cicd/webhook/", cicd_webhook, name="cicd_webhook"),

]
