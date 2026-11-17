from django.contrib import admin

from .models import Comment, Issue, IssueHistory, GitHubLink


class CommentInline(admin.TabularInline):
    model = Comment
    extra = 0


@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    list_display = ("key", "title", "project", "status", "priority", "severity", "assignee", "created_at")
    list_filter = ("status", "priority", "issue_type", "project")
    search_fields = ("title", "description")
    inlines = [CommentInline]


admin.site.register(IssueHistory)

@admin.register(GitHubLink)
class GitHubLinkAdmin(admin.ModelAdmin):
    list_display = ("issue", "repository_name", "commit_id", "linked_at")
    search_fields = ("issue__title", "repository_name", "commit_id")