"""Views for the transactions app."""
import logging

from django.conf import settings
from rest_framework import generics, permissions, status
from rest_framework.response import Response

from apps.core.kafka_producer import publish_event
from apps.transactions.models import Transaction
from apps.transactions.serializers import (
    TransactionCreateSerializer,
    TransactionSerializer,
    TransactionStatusUpdateSerializer,
)

logger = logging.getLogger(__name__)


class TransactionListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/transactions/  — list transactions for authenticated user
    POST /api/transactions/  — create a transaction (publishes Kafka event)
    """

    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Transaction.objects.filter(
            account__user=self.request.user,
            is_deleted=False,
        )

    def get_serializer_class(self):
        if self.request.method == "POST":
            return TransactionCreateSerializer
        return TransactionSerializer

    def perform_create(self, serializer):
        txn = serializer.save(status=Transaction.Status.PENDING)
        logger.info(
            "Transaction created",
            extra={"transaction_id": str(txn.id), "amount": str(txn.amount)},
        )
        publish_event(
            settings.KAFKA_TOPIC_CREATED,
            {
                "transaction_id": str(txn.id),
                "account_id": str(txn.account.id),
                "transaction_type": txn.transaction_type,
                "amount": str(txn.amount),
                "status": txn.status,
            },
        )


class TransactionDetailView(generics.RetrieveAPIView):
    """
    GET /api/transactions/<id>/  — retrieve a single transaction
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TransactionSerializer

    def get_queryset(self):
        return Transaction.objects.filter(
            account__user=self.request.user,
            is_deleted=False,
        )


class InternalTransactionStatusView(generics.UpdateAPIView):
    """
    PATCH /api/internal/transactions/<id>/
    Called by Processing Service — HMAC authenticated.
    Updates transaction status to COMPLETED or FAILED.
    """

    permission_classes = [permissions.AllowAny]  # Auth handled by HMAC check below
    serializer_class = TransactionStatusUpdateSerializer
    http_method_names = ["patch"]

    def get_queryset(self):
        return Transaction.objects.filter(is_deleted=False)

    def update(self, request, *args, **kwargs):
        from apps.core.hmac_middleware import verify_hmac_request
        valid, reason = verify_hmac_request(request)
        if not valid:
            return Response({"detail": f"HMAC auth failed: {reason}"}, status=status.HTTP_401_UNAUTHORIZED)
        txn = self.get_object()
        serializer = self.get_serializer(txn, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data["status"]

        if txn.status != Transaction.Status.PENDING:
            return Response(
                {"detail": f"Transaction already in terminal state: {txn.status}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        txn.status = new_status
        txn.save(update_fields=["status", "updated_at"])

        publish_event(
            settings.KAFKA_TOPIC_UPDATED,
            {
                "transaction_id": str(txn.id),
                "status": txn.status,
            },
        )
        logger.info(
            "Transaction status updated",
            extra={"transaction_id": str(txn.id), "status": txn.status},
        )
        return Response(TransactionSerializer(txn).data, status=status.HTTP_200_OK)
