"""Views for the users app — CRUD + soft-delete."""
import logging

from rest_framework import generics, permissions, status
from rest_framework.response import Response

from apps.users.models import User
from apps.users.serializers import (
    UserCreateSerializer,
    UserDetailSerializer,
    UserUpdateSerializer,
)

logger = logging.getLogger(__name__)


class UserCreateView(generics.CreateAPIView):
    """
    POST /api/users/
    Register a new user. No authentication required.
    """

    serializer_class = UserCreateSerializer
    permission_classes = [permissions.AllowAny]

    def perform_create(self, serializer):
        user = serializer.save()
        logger.info("New user registered", extra={"user_id": str(user.id)})


class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/users/<id>/  — retrieve own profile
    PATCH  /api/users/<id>/  — partial update own profile
    DELETE /api/users/<id>/  — soft-delete own account
    """

    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return User.objects.filter(is_deleted=False)

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return UserUpdateSerializer
        return UserDetailSerializer

    def get_object(self):
        """Users may only access their own record."""
        obj = super().get_object()
        if obj.id != self.request.user.id:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You can only access your own profile.")
        return obj

    def destroy(self, request, *args, **kwargs):
        """Soft-delete instead of hard delete."""
        user = self.get_object()
        user.soft_delete()
        logger.info("User soft-deleted", extra={"user_id": str(user.id)})
        return Response(
            {"detail": "Account deleted successfully."},
            status=status.HTTP_200_OK,
        )

    def update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return super().update(request, *args, **kwargs)
