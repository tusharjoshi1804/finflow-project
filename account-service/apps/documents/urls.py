"""URL patterns for the documents app."""
from django.urls import path

from apps.documents.views import (
    DocumentDownloadView,
    DocumentListView,
    DocumentUploadView,
)

urlpatterns = [
    path("", DocumentListView.as_view(), name="document-list"),
    path("upload/", DocumentUploadView.as_view(), name="document-upload"),
    path("<uuid:pk>/download/", DocumentDownloadView.as_view(), name="document-download"),
]
