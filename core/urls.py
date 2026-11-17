from django.urls import path

from . import views

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("reports/", views.ReportsView.as_view(), name="reports"),
    path("reports/export/", views.report_export, name="report_export"),
    path("database/", views.DatabaseView.as_view(), name="database"),
    path("database/status/", views.database_status, name="database_status"),
]
