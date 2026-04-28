"""
Integration tests for MinIO document storage:

1. Upload KYC document (multipart) → MinIO
2. List user's documents
3. Download document from MinIO
4. Verify ownership and access control
5. Verify deletion cascades to MinIO
6. Verify audit trail
"""
import io
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.models import AuditLog
from apps.documents.models import Document

User = get_user_model()

UPLOAD_URL = "/api/documents/upload/"
LIST_URL = "/api/documents/"


def download_url(pk):
    return f"/api/documents/{pk}/download/"


def get_jwt_client(user):
    """Create an APIClient authenticated with JWT."""
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")
    return client


def make_file(name="test.pdf", content=b"dummy pdf content", content_type="application/pdf"):
    """Create a file-like object for upload."""
    f = io.BytesIO(content)
    f.name = name
    f.content_type = content_type
    f.size = len(content)
    return f


@pytest.mark.django_db
class TestMinIODocumentFlow:
    """End-to-end MinIO document flow tests."""

    def setup_method(self):
        """Create a test user."""
        self.user = User.objects.create_user(
            email="minio-test@example.com",
            password="Pass1234!",
            first_name="MinIO",
            last_name="Test",
        )
        self.client = get_jwt_client(self.user)

    def test_01_upload_document_returns_201(self):
        """Step 1: Uploading a valid document returns 201."""
        file = make_file(name="kyc_doc.pdf")
        
        with patch("apps.documents.views.upload_file", return_value=True):
            res = self.client.post(UPLOAD_URL, {"file": file}, format="multipart")
        
        assert res.status_code == status.HTTP_201_CREATED
        assert "id" in res.data
        assert res.data["file_name"] == "kyc_doc.pdf"
        assert res.data["content_type"] == "application/pdf"

    def test_02_upload_creates_database_record(self):
        """Step 1b: Upload creates a document record in DB."""
        file = make_file(name="kyc2.pdf")
        
        with patch("apps.documents.views.upload_file", return_value=True):
            res = self.client.post(UPLOAD_URL, {"file": file}, format="multipart")
        
        doc_id = res.data["id"]
        doc = Document.objects.get(id=doc_id)
        assert doc.user == self.user
        assert doc.file_name == "kyc2.pdf"
        assert doc.file_size == len(b"dummy pdf content")

    def test_03_upload_invalid_file_type_returns_400(self):
        """Invalid file types are rejected."""
        file = make_file(name="script.exe", content_type="application/x-msdownload")
        
        res = self.client.post(UPLOAD_URL, {"file": file}, format="multipart")
        
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert "Unsupported file type" in str(res.data)

    def test_04_upload_empty_file_returns_400(self):
        """Empty files are rejected."""
        file = make_file(name="empty.pdf", content=b"")
        
        res = self.client.post(UPLOAD_URL, {"file": file}, format="multipart")
        
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert "empty" in str(res.data).lower()

    def test_05_upload_oversized_file_returns_400(self):
        """Files exceeding 10 MB are rejected."""
        # Create a mock file with size > 10 MB
        large_content = b"x" * (11 * 1024 * 1024)  # 11 MB
        file = make_file(name="large.pdf", content=large_content)
        
        res = self.client.post(UPLOAD_URL, {"file": file}, format="multipart")
        
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert "too large" in str(res.data).lower()

    def test_06_list_documents_returns_own_only(self):
        """Users can only list their own documents."""
        # Create another user
        other_user = User.objects.create_user(
            email="other@example.com",
            password="Pass1234!",
            first_name="Other",
            last_name="User",
        )
        
        # Create documents for both users
        Document.objects.create(
            user=self.user,
            file_name="mine.pdf",
            object_name="kyc/user1/doc1.pdf",
            content_type="application/pdf",
            file_size=1024,
        )
        Document.objects.create(
            user=other_user,
            file_name="theirs.pdf",
            object_name="kyc/user2/doc2.pdf",
            content_type="application/pdf",
            file_size=2048,
        )
        
        res = self.client.get(LIST_URL)
        
        assert res.status_code == status.HTTP_200_OK
        assert res.data["count"] == 1
        assert res.data["results"][0]["file_name"] == "mine.pdf"

    def test_07_download_document_returns_file(self):
        """Step 3: Downloading a document returns file bytes."""
        # Create a document
        doc = Document.objects.create(
            user=self.user,
            file_name="download_test.pdf",
            object_name="kyc/user/doc.pdf",
            content_type="application/pdf",
            file_size=1024,
        )
        
        # Mock MinIO download
        with patch("apps.documents.views.download_file") as mock_download:
            mock_download.return_value = (b"pdf file content", "application/pdf")
            res = self.client.get(download_url(doc.id))
        
        assert res.status_code == status.HTTP_200_OK
        assert res["Content-Type"] == "application/pdf"
        assert res["Content-Disposition"] == 'attachment; filename="download_test.pdf"'
        assert b"pdf file content" in b"".join(res.streaming_content)

    def test_08_download_nonexistent_document_returns_404(self):
        """Downloading a nonexistent document returns 404."""
        import uuid
        fake_id = uuid.uuid4()
        
        res = self.client.get(download_url(fake_id))
        
        assert res.status_code == status.HTTP_404_NOT_FOUND

    def test_09_download_other_user_document_returns_404(self):
        """Users cannot download other users' documents."""
        # Create another user
        other_user = User.objects.create_user(
            email="other2@example.com",
            password="Pass1234!",
            first_name="Other",
            last_name="User",
        )
        
        # Create document for other user
        doc = Document.objects.create(
            user=other_user,
            file_name="secret.pdf",
            object_name="kyc/other/secret.pdf",
            content_type="application/pdf",
            file_size=512,
        )
        
        # Try to download as self.user
        res = self.client.get(download_url(doc.id))
        
        assert res.status_code == status.HTTP_404_NOT_FOUND

    def test_10_delete_document_removes_from_minio(self):
        """Step 5: Deleting a document removes it from MinIO."""
        doc = Document.objects.create(
            user=self.user,
            file_name="delete_test.pdf",
            object_name="kyc/user/delete.pdf",
            content_type="application/pdf",
            file_size=2048,
        )
        
        with patch("apps.documents.models.delete_file") as mock_delete:
            doc.soft_delete()
            mock_delete.assert_called_once_with("kyc/user/delete.pdf")
        
        # Verify document is marked as deleted
        doc.refresh_from_db()
        assert doc.is_deleted is True

    def test_11_upload_creates_audit_log(self):
        """Step 6: Uploading a document creates an audit log."""
        # Clear existing logs
        AuditLog.objects.all().delete()
        
        file = make_file(name="audit_test.pdf")
        
        with patch("apps.documents.views.upload_file", return_value=True):
            res = self.client.post(UPLOAD_URL, {"file": file}, format="multipart")
        
        # Verify audit log was created
        audit = AuditLog.objects.filter(action="DOCUMENT_UPLOADED").first()
        assert audit is not None
        assert audit.actor == self.user
        assert audit.resource == "Document"
        assert "file_size" in audit.new_data

    def test_12_download_creates_audit_log(self):
        """Downloading a document creates an audit log."""
        # Create and clear logs
        doc = Document.objects.create(
            user=self.user,
            file_name="audit_download.pdf",
            object_name="kyc/user/audit.pdf",
            content_type="application/pdf",
            file_size=512,
        )
        AuditLog.objects.all().delete()
        
        with patch("apps.documents.views.download_file") as mock_download:
            mock_download.return_value = (b"content", "application/pdf")
            self.client.get(download_url(doc.id))
        
        # Verify audit log
        audit = AuditLog.objects.filter(action="DOCUMENT_DOWNLOADED").first()
        assert audit is not None
        assert audit.actor == self.user

    def test_13_full_flow_upload_list_download(self):
        """Full integration flow: upload → list → download."""
        file = make_file(name="flow_test.pdf", content=b"test pdf content")
        
        # Step 1: Upload
        with patch("apps.documents.views.upload_file", return_value=True):
            upload_res = self.client.post(UPLOAD_URL, {"file": file}, format="multipart")
        
        assert upload_res.status_code == status.HTTP_201_CREATED
        doc_id = upload_res.data["id"]
        
        # Step 2: List
        list_res = self.client.get(LIST_URL)
        assert list_res.status_code == status.HTTP_200_OK
        assert list_res.data["count"] == 1
        assert list_res.data["results"][0]["id"] == doc_id
        
        # Step 3: Download
        with patch("apps.documents.views.download_file") as mock_download:
            mock_download.return_value = (b"test pdf content", "application/pdf")
            download_res = self.client.get(download_url(doc_id))
        
        assert download_res.status_code == status.HTTP_200_OK
        assert b"test pdf content" in b"".join(download_res.streaming_content)
