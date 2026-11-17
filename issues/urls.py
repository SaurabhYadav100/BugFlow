from django.urls import path

from . import views

urlpatterns = [
    path("issues/", views.IssueListView.as_view(), name="issue_list"),
    path("issues/add/", views.IssueCreateView.as_view(), name="issue_create"),
    path("issues/mine/", views.MyIssuesView.as_view(), name="my_issues"),
    path("issues/reported/", views.ReportedIssuesView.as_view(), name="reported_issues"),
    path("issues/tests/", views.MyTestsView.as_view(), name="my_tests"),
    path("issues/bulk-delete/", views.IssueBulkDeleteView.as_view(), name="issue_bulk_delete"),
    path("issues/<int:pk>/", views.IssueDetailView.as_view(), name="issue_detail"),
    path("issues/<int:pk>/edit/", views.IssueUpdateView.as_view(), name="issue_edit"),
    path("issues/<int:pk>/update/", views.IssueQuickUpdateView.as_view(), name="issue_update"),
    path("issues/<int:pk>/comment/", views.IssueCommentView.as_view(), name="issue_comment"),
    path("issues/<int:pk>/delete/", views.IssueDeleteView.as_view(), name="issue_delete"),
    path("comments/", views.CommentListView.as_view(), name="comment_list"),

    path("issues/<int:pk>/attach/", views.IssueAttachView.as_view(), name="issue_attach"),
    path("attachments/<int:pk>/download/", views.AttachmentDownloadView.as_view(), name="attachment_download"),
    path("attachments/<int:pk>/delete/", views.AttachmentDeleteView.as_view(), name="attachment_delete"),
]
