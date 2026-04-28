"""
Tests for apps/documents — upload, list, download, ownership,
file validation, and MinIO client utilities (all MinIO mocked).
"""
import io
import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.documents.models import Document

User = get_user_model()

UPLOAD_URL = "/api/documents/upload/"
LIST_URL = "/api/documents/"


def download_url(pk):
    return f"/api/documents/{pk}/download/"


def make_auth_client(user):
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")
    return client


def make_file(name="test.pdf", content=b"dummy pdf content", content_type="application/pdf"):
    f = io.BytesIO(content)
    f.name = name
    f.content_type = content_type
    f.size = len(content)
    return f


@pytest.fixture
def user_a(db):
    return User.objects.create_user(
        email="doc_usera@example.com", password="Pass1234!",
        first_name="Doc", last_name="UserA"
    )


@pytest.fixture
def user_b(db):
    return User.objects.create_user(
        email="doc_userb@example.com", password="Pass1234!",
        first_name="Doc", last_name="UserB"
    )


@pytest.fixture
def client_a(user_a):
    return make_auth_client(user_a)


@pytest.fixture
def client_b(user_b):
    return make_auth_client(user_b)


@pytest.fixture
def doc_a(user_a):
    return Document.objects.create(
        user=user_a,
        file_name="kyc.pdf",
        object_name=f"kyc/{user_a.id}/test-obj.pdf",
        content_type="application/pdf",
        file_size=1024,
    )


# ---------------------------------------------------------------
# Document model tests
# ---------------------------------------------------------------
@pytest.mark.django_db
class TestDocumentModel:
    def test_str_representation(self, doc_a):
        assert "kyc.pdf" in str(doc_a)
        assert "doc_usera@example.com" in str(doc_a)

    def test_uuid_primary_key(self, doc_a):
        assert isinstance(doc_a.id, uuid.UUID)

    def test_soft_delete(self, doc_a):
        doc_a.soft_delete()
        assert doc_a.is_deleted is True
        assert doc_a.deleted_at is not None

    def test_object_name_is_unique(self, user_a, user_b):
        Document.objects.create(
            user=user_a, file_name="a.pdf",
            object_name="kyc/unique/001.pdf",
            content_type="application/pdf", file_size=100,
        )
        with pytest.raises(Exception):
            Document.objects.create(
                user=user_b, file_name="b.pdf",
                object_name="kyc/unique/001.pdf",
                content_type="application/pdf", file_size=200,
            )


# ---------------------------------------------------------------
# Upload  POST /api/documents/upload/
# ---------------------------------------------------------------
@pytest.mark.django_db
class TestDocumentUpload:
    @patch("apps.documents.views.upload_file", return_value=True)
    def test_upload_pdf_returns_201(self, mock_upload, client_a):
        f = make_file("kyc.pdf", b"pdf bytes", "application/pdf")
        res = client_a.post(UPLOAD_URL, {"file": f}, format="multipart")
        assert res.status_code == status.HTTP_201_CREATED
        assert res.data["file_name"] == "kyc.pdf"
        assert res.data["content_type"] == "application/pdf"

    @patch("apps.documents.views.upload_file", return_value=True)
    def test_upload_jpeg_returns_201(self, mock_upload, client_a):
        f = make_file("photo.jpg", b"jpeg bytes", "image/jpeg")
        res = client_a.post(UPLOAD_URL, {"file": f}, format="multipart")
        assert res.status_code == status.HTTP_201_CREATED

    @patch("apps.documents.views.upload_file", return_value=True)
    def test_upload_png_returns_201(self, mock_upload, client_a):
        f = make_file("photo.png", b"png bytes", "image/png")
        res = client_a.post(UPLOAD_URL, {"file": f}, format="multipart")
        assert res.status_code == status.HTTP_201_CREATED

    @patch("apps.documents.views.upload_file", return_value=True)
    def test_upload_creates_document_record(self, mock_upload, client_a, user_a):
        f = make_file("id.pdf", b"content", "application/pdf")
        client_a.post(UPLOAD_URL, {"file": f}, format="multipart")
        assert Document.objects.filter(user=user_a, file_name="id.pdf").exists()

    def test_upload_invalid_content_type_returns_400(self, client_a):
        f = make_file("malware.exe", b"bad", "application/octet-stream")
        res = client_a.post(UPLOAD_URL, {"file": f}, format="multipart")
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    def test_upload_too_large_returns_400(self, client_a):
        from apps.core.minio_client import MAX_FILE_SIZE_BYTES
        big_content = b"x" * (MAX_FILE_SIZE_BYTES + 1)
        f = make_file("big.pdf", big_content, "application/pdf")
        res = client_a.post(UPLOAD_URL, {"file": f}, format="multipart")
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    def test_upload_no_file_returns_400(self, client_a):
        res = client_a.post(UPLOAD_URL, {}, format="multipart")
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    def test_upload_unauthenticated_returns_401(self, api_client):
        f = make_file()
        res = api_client.post(UPLOAD_URL, {"file": f}, format="multipart")
        assert res.status_code == status.HTTP_401_UNAUTHORIZED

    @patch("apps.documents.views.upload_file", return_value=False)
    def test_upload_minio_failure_returns_502(self, mock_upload, client_a):
        f = make_file("fail.pdf", b"content", "application/pdf")
        res = client_a.post(UPLOAD_URL, {"file": f}, format="multipart")
        assert res.status_code == status.HTTP_502_BAD_GATEWAY

    @patch("apps.documents.views.upload_file", return_value=True)
    def test_upload_gif_returns_201(self, mock_upload, client_a):
        f = make_file("anim.gif", b"gif bytes", "image/gif")
        res = client_a.post(UPLOAD_URL, {"file": f}, format="multipart")
        assert res.status_code == status.HTTP_201_CREATED


# ---------------------------------------------------------------
# List  GET /api/documents/
# ---------------------------------------------------------------
@pytest.mark.django_db
class TestDocumentList:
    def test_list_returns_own_documents(self, client_a, doc_a):
        res = client_a.get(LIST_URL)
        assert res.status_code == status.HTTP_200_OK
        assert res.data["count"] == 1
        assert res.data["results"][0]["file_name"] == "kyc.pdf"

    def test_list_excludes_other_user_docs(self, client_a, user_b):
        Document.objects.create(
            user=user_b, file_name="other.pdf",
            object_name="kyc/other/001.pdf",
            content_type="application/pdf", file_size=512,
        )
        res = client_a.get(LIST_URL)
        assert res.status_code == status.HTTP_200_OK
        assert res.data["count"] == 0

    def test_list_excludes_soft_deleted(self, client_a, doc_a):
        doc_a.soft_delete()
        res = client_a.get(LIST_URL)
        assert res.data["count"] == 0

    def test_list_unauthenticated_returns_401(self, api_client):
        res = api_client.get(LIST_URL)
        assert res.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------
# Download  GET /api/documents/<id>/download/
# ---------------------------------------------------------------
@pytest.mark.django_db
class TestDocumentDownload:
    @patch("apps.documents.views.download_file", return_value=(b"pdf content", "application/pdf"))
    def test_download_own_document_returns_200(self, mock_dl, client_a, doc_a):
        res = client_a.get(download_url(doc_a.id))
        assert res.status_code == status.HTTP_200_OK
        assert res.content == b"pdf content"
        assert "attachment" in res["Content-Disposition"]

    @patch("apps.documents.views.download_file", return_value=(None, None))
    def test_download_minio_failure_returns_502(self, mock_dl, client_a, doc_a):
        res = client_a.get(download_url(doc_a.id))
        assert res.status_code == status.HTTP_502_BAD_GATEWAY

    def test_download_other_user_doc_returns_404(self, client_b, doc_a):
        res = client_b.get(download_url(doc_a.id))
        assert res.status_code == status.HTTP_404_NOT_FOUND

    def test_download_nonexistent_returns_404(self, client_a):
        res = client_a.get(download_url(uuid.uuid4()))
        assert res.status_code == status.HTTP_404_NOT_FOUND

    def test_download_unauthenticated_returns_401(self, api_client, doc_a):
        res = api_client.get(download_url(doc_a.id))
        assert res.status_code == status.HTTP_401_UNAUTHORIZED

    @patch("apps.documents.views.download_file", return_value=(b"data", "image/jpeg"))
    def test_download_sets_content_disposition_filename(self, mock_dl, client_a, doc_a):
        res = client_a.get(download_url(doc_a.id))
        assert doc_a.file_name in res["Content-Disposition"]


# ---------------------------------------------------------------
# MinIO client utility tests (no real MinIO)
# ---------------------------------------------------------------
class TestMinioClientUtils:
    def test_get_minio_client_returns_none_on_failure(self):
        from apps.core.minio_client import get_minio_client
        with patch("apps.core.minio_client.Minio", side_effect=Exception("no minio")):
            result = get_minio_client()
            assert result is None

    def test_upload_file_returns_false_when_no_client(self):
        from apps.core.minio_client import upload_file
        with patch("apps.core.minio_client.get_minio_client", return_value=None):
            result = upload_file("obj", io.BytesIO(b"x"), "application/pdf", 1)
            assert result is False

    def test_upload_file_returns_true_on_success(self):
        from apps.core.minio_client import upload_file
        mock_client = MagicMock()
        mock_client.bucket_exists.return_value = True
        with patch("apps.core.minio_client.get_minio_client", return_value=mock_client):
            result = upload_file("obj", io.BytesIO(b"data"), "application/pdf", 4)
            assert result is True
            mock_client.put_object.assert_called_once()

    def test_upload_file_creates_bucket_if_not_exists(self):
        from apps.core.minio_client import upload_file
        mock_client = MagicMock()
        mock_client.bucket_exists.return_value = False
        with patch("apps.core.minio_client.get_minio_client", return_value=mock_client):
            upload_file("obj", io.BytesIO(b"data"), "application/pdf", 4)
            mock_client.make_bucket.assert_called_once()

    def test_upload_file_returns_false_on_exception(self):
        from apps.core.minio_client import upload_file
        mock_client = MagicMock()
        mock_client.bucket_exists.return_value = True
        mock_client.put_object.side_effect = Exception("put failed")
        with patch("apps.core.minio_client.get_minio_client", return_value=mock_client):
            result = upload_file("obj", io.BytesIO(b"data"), "application/pdf", 4)
            assert result is False

    def test_download_file_returns_none_when_no_client(self):
        from apps.core.minio_client import download_file
        with patch("apps.core.minio_client.get_minio_client", return_value=None):
            data, ct = download_file("obj")
            assert data is None
            assert ct is None

    def test_download_file_returns_data_on_success(self):
        from apps.core.minio_client import download_file
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.read.return_value = b"file bytes"
        mock_response.headers = {"Content-Type": "application/pdf"}
        mock_client.get_object.return_value = mock_response
        with patch("apps.core.minio_client.get_minio_client", return_value=mock_client):
            data, ct = download_file("obj")
            assert data == b"file bytes"
            assert ct == "application/pdf"

    def test_download_file_returns_none_on_exception(self):
        from apps.core.minio_client import download_file
        mock_client = MagicMock()
        mock_client.get_object.side_effect = Exception("get failed")
        with patch("apps.core.minio_client.get_minio_client", return_value=mock_client):
            data, ct = download_file("obj")
            assert data is None
            assert ct is None

    def test_delete_file_returns_false_when_no_client(self):
        from apps.core.minio_client import delete_file
        with patch("apps.core.minio_client.get_minio_client", return_value=None):
            result = delete_file("obj")
            assert result is False

    def test_delete_file_returns_true_on_success(self):
        from apps.core.minio_client import delete_file
        mock_client = MagicMock()
        with patch("apps.core.minio_client.get_minio_client", return_value=mock_client):
            result = delete_file("obj")
            assert result is True

    def test_delete_file_returns_false_on_exception(self):
        from apps.core.minio_client import delete_file
        mock_client = MagicMock()
        mock_client.remove_object.side_effect = Exception("del failed")
        with patch("apps.core.minio_client.get_minio_client", return_value=mock_client):
            result = delete_file("obj")
            assert result is False

    def test_ensure_bucket_exists_returns_false_on_exception(self):
        from apps.core.minio_client import ensure_bucket_exists
        mock_client = MagicMock()
        mock_client.bucket_exists.side_effect = Exception("conn refused")
        result = ensure_bucket_exists(mock_client)
        assert result is False

    def test_allowed_content_types_set(self):
        from apps.core.minio_client import ALLOWED_CONTENT_TYPES
        assert "application/pdf" in ALLOWED_CONTENT_TYPES
        assert "image/jpeg" in ALLOWED_CONTENT_TYPES

    def test_max_file_size_is_10mb(self):
        from apps.core.minio_client import MAX_FILE_SIZE_BYTES
        assert MAX_FILE_SIZE_BYTES == 10 * 1024 * 1024
