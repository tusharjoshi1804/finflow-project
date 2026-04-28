"""URL patterns for the transactions app."""
from django.urls import path

from apps.transactions.views import (
    InternalTransactionStatusView,
    TransactionDetailView,
    TransactionListCreateView,
)

urlpatterns = [
    path("", TransactionListCreateView.as_view(), name="transaction-list-create"),
    path("<uuid:pk>/", TransactionDetailView.as_view(), name="transaction-detail"),
]

internal_urlpatterns = [
    path(
        "<uuid:pk>/",
        InternalTransactionStatusView.as_view(),
        name="internal-transaction-status",
    ),
]
