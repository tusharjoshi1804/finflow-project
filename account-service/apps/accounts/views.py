"""Views for the accounts app."""
import logging

from rest_framework import generics, permissions, status
from rest_framework.response import Response

from apps.accounts.models import Account
from apps.accounts.serializers import (
    AccountCreateSerializer,
    AccountSerializer,
    AccountUpdateSerializer,
)

logger = logging.getLogger(__name__)


class AccountListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/accounts/  — list authenticated user's accounts
    POST /api/accounts/  — create a new account
    """

    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Account.objects.filter(
            user=self.request.user, is_deleted=False
        )

    def get_serializer_class(self):
        if self.request.method == "POST":
            return AccountCreateSerializer
        return AccountSerializer

    def perform_create(self, serializer):
        account = serializer.save(user=self.request.user)
        logger.info("Account created", extra={"account_id": str(account.id)})


class AccountDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/accounts/<id>/  — retrieve
    PATCH  /api/accounts/<id>/  — partial update
    DELETE /api/accounts/<id>/  — soft-delete
    """

    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Account.objects.filter(
            user=self.request.user, is_deleted=False
        )

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return AccountUpdateSerializer
        return AccountSerializer

    def update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        account = self.get_object()
        account.soft_delete()
        logger.info("Account soft-deleted", extra={"account_id": str(account.id)})
        return Response(
            {"detail": "Account deleted successfully."},
            status=status.HTTP_200_OK,
        )
