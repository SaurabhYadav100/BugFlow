from django.urls import path

from . import views

urlpatterns = [
    path("projects/", views.ProjectListView.as_view(), name="project_list"),
    path("projects/add/", views.ProjectCreateView.as_view(), name="project_create"),
    path("projects/<int:pk>/edit/", views.ProjectUpdateView.as_view(), name="project_edit"),
    path("projects/<int:pk>/delete/", views.ProjectDeleteView.as_view(), name="project_delete"),
    path("sprints/", views.SprintListView.as_view(), name="sprint_list"),
    path("sprints/add/", views.SprintCreateView.as_view(), name="sprint_create"),

    path("sprints/<int:pk>/", views.SprintDetailView.as_view(), name="sprint_detail"),
    path("sprints/<int:pk>/assign/", views.SprintAssignView.as_view(), name="sprint_assign"),
    path("sprints/<int:pk>/remove/<int:issue_pk>/", views.SprintRemoveView.as_view(), name="sprint_remove_issue"),

    path("sprints/<int:pk>/edit/", views.SprintUpdateView.as_view(), name="sprint_edit"),
    path("sprints/<int:pk>/delete/", views.SprintDeleteView.as_view(), name="sprint_delete"),
]
