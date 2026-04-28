"""URL patterns for the accounts app."""
from django.urls import path

from apps.accounts.views import AccountDetailView, AccountListCreateView

urlpatterns = [
    path("", AccountListCreateView.as_view(), name="account-list-create"),
    path("<uuid:pk>/", AccountDetailView.as_view(), name="account-detail"),
]
