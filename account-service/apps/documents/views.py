"""Views for the documents app — upload, list, download."""
import logging
import uuid

from django.http import HttpResponse
from rest_framework import generics, parsers, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import AuditLog
from apps.core.minio_client import download_file, upload_file
from apps.documents.models import Document
from apps.documents.serializers import DocumentSerializer, DocumentUploadSerializer

logger = logging.getLogger(__name__)


class DocumentListView(generics.ListAPIView):
    """GET /api/documents/ — list authenticated user's documents."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = DocumentSerializer

    def get_queryset(self):
        return Document.objects.filter(user=self.request.user, is_deleted=False)


class DocumentUploadView(APIView):
    """POST /api/documents/upload/ — upload a KYC document to MinIO."""

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]

    def post(self, request):
        serializer = DocumentUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        file = serializer.validated_data["file"]
        ext = file.name.rsplit(".", 1)[-1] if "." in file.name else "bin"
        object_name = f"kyc/{request.user.id}/{uuid.uuid4()}.{ext}"

        success = upload_file(
            object_name=object_name,
            file_obj=file,
            content_type=file.content_type,
            size=file.size,
        )

        if not success:
            return Response(
                {"detail": "File upload to storage failed. Please try again."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        doc = Document.objects.create(
            user=request.user,
            file_name=file.name,
            object_name=object_name,
            content_type=file.content_type,
            file_size=file.size,
        )
        
        # Audit: document uploaded (scrub filename)
        AuditLog.log(
            action="DOCUMENT_UPLOADED",
            resource="Document",
            resource_id=str(doc.id),
            actor=request.user,
            new_data={"file_size": file.size, "content_type": file.content_type},
        )
        
        logger.info(
            "Document uploaded",
            extra={"document_id": str(doc.id), "file_size": file.size},
        )
        return Response(DocumentSerializer(doc).data, status=status.HTTP_201_CREATED)


class DocumentDownloadView(APIView):
    """GET /api/documents/<id>/download/ — download a document from MinIO."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        try:
            doc = Document.objects.get(pk=pk, user=request.user, is_deleted=False)
        except Document.DoesNotExist:
            return Response(
                {"detail": "Document not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        data, content_type = download_file(doc.object_name)
        if data is None:
            return Response(
                {"detail": "File could not be retrieved from storage."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # Audit: document downloaded
        AuditLog.log(
            action="DOCUMENT_DOWNLOADED",
            resource="Document",
            resource_id=str(doc.id),
            actor=request.user,
            new_data={"file_size": doc.file_size},
        )

        response = HttpResponse(data, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{doc.file_name}"'
        return response
