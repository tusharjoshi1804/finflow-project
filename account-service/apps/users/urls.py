"""URL patterns for the users app."""
from django.urls import path

from apps.users.views import UserCreateView, UserDetailView

urlpatterns = [
    path("", UserCreateView.as_view(), name="user-create"),
    path("<uuid:pk>/", UserDetailView.as_view(), name="user-detail"),
]
