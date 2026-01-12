"""Tests for Google Docs client."""

from unittest.mock import MagicMock, patch

import httplib2
import pytest
from googleapiclient.errors import HttpError


def test_get_or_create_folder_exists():
    """Test getting existing folder."""
    with (
        patch("org_gdocs_sync.gdocs.client.get_credentials"),
        patch("org_gdocs_sync.gdocs.client.build") as mock_build,
    ):
        mock_drive = MagicMock()
        mock_build.return_value = mock_drive

        # Mock folder exists
        mock_drive.files().list().execute.return_value = {
            "files": [{"id": "folder123", "name": "Test_assets"}]
        }

        from org_gdocs_sync.gdocs.client import GoogleDocsClient

        client = GoogleDocsClient()
        folder_id = client.get_or_create_folder("Test_assets", "parent456")

        assert folder_id == "folder123"


def test_get_or_create_folder_creates():
    """Test creating folder when it doesn't exist."""
    with (
        patch("org_gdocs_sync.gdocs.client.get_credentials"),
        patch("org_gdocs_sync.gdocs.client.build") as mock_build,
    ):
        mock_drive = MagicMock()
        mock_build.return_value = mock_drive

        # Mock folder doesn't exist
        mock_drive.files().list().execute.return_value = {"files": []}
        # Mock folder creation
        mock_drive.files().create().execute.return_value = {"id": "newfolder789"}

        from org_gdocs_sync.gdocs.client import GoogleDocsClient

        client = GoogleDocsClient()
        folder_id = client.get_or_create_folder("Test_assets", "parent456")

        assert folder_id == "newfolder789"


def test_get_or_create_folder_with_special_chars():
    """Test folder names with special characters are escaped properly."""
    with (
        patch("org_gdocs_sync.gdocs.client.get_credentials"),
        patch("org_gdocs_sync.gdocs.client.build") as mock_build,
    ):
        mock_drive = MagicMock()
        mock_build.return_value = mock_drive

        # Mock: folder doesn't exist, will be created
        mock_drive.files().list().execute.return_value = {"files": []}
        mock_drive.files().create().execute.return_value = {"id": "new-folder-id"}

        from org_gdocs_sync.gdocs.client import GoogleDocsClient

        client = GoogleDocsClient()
        result = client.get_or_create_folder("Test's Folder", "parent-123")

        assert result == "new-folder-id"
        # Verify the query has escaped single quote
        list_call = mock_drive.files().list.call_args
        assert "Test\\'s Folder" in list_call.kwargs.get("q", "")


def test_get_or_create_folder_http_error():
    """Test that HttpError is caught and re-raised with context."""
    with (
        patch("org_gdocs_sync.gdocs.client.get_credentials"),
        patch("org_gdocs_sync.gdocs.client.build") as mock_build,
    ):
        mock_drive = MagicMock()
        mock_build.return_value = mock_drive

        # Mock: API throws HttpError
        resp = httplib2.Response({"status": 403})
        mock_drive.files().list().execute.side_effect = HttpError(resp, b"Forbidden")

        from org_gdocs_sync.gdocs.client import GoogleDocsClient

        client = GoogleDocsClient()

        with pytest.raises(Exception) as exc_info:
            client.get_or_create_folder("Test Folder", "parent-123")

        assert "Failed to get or create folder" in str(exc_info.value)


def test_upload_image(tmp_path):
    """Test uploading image to Drive."""
    # Create test image file
    test_image = tmp_path / "test.svg"
    test_image.write_text("<svg></svg>")

    with (
        patch("org_gdocs_sync.gdocs.client.get_credentials"),
        patch("org_gdocs_sync.gdocs.client.build") as mock_build,
    ):
        mock_drive = MagicMock()
        mock_build.return_value = mock_drive

        # Mock upload
        mock_drive.files().create().execute.return_value = {
            "id": "file123",
        }
        # Mock file doesn't exist
        mock_drive.files().list().execute.return_value = {"files": []}

        from org_gdocs_sync.gdocs.client import GoogleDocsClient

        client = GoogleDocsClient()
        file_id = client.upload_image(test_image, "folder456")

        assert file_id == "file123"


def test_upload_image_update_existing(tmp_path):
    """Test updating existing image in Drive."""
    test_image = tmp_path / "test.svg"
    test_image.write_text("<svg></svg>")

    with (
        patch("org_gdocs_sync.gdocs.client.get_credentials"),
        patch("org_gdocs_sync.gdocs.client.build") as mock_build,
    ):
        mock_drive = MagicMock()
        mock_build.return_value = mock_drive

        # Mock file exists
        mock_drive.files().list().execute.return_value = {
            "files": [{"id": "existing123"}]
        }
        # Mock update
        mock_drive.files().update().execute.return_value = {"id": "existing123"}

        from org_gdocs_sync.gdocs.client import GoogleDocsClient

        client = GoogleDocsClient()
        file_id = client.upload_image(test_image, "folder456")

        assert file_id == "existing123"


def test_get_parent_folder():
    """Test getting parent folder of a document."""
    with (
        patch("org_gdocs_sync.gdocs.client.get_credentials"),
        patch("org_gdocs_sync.gdocs.client.build") as mock_build,
    ):
        mock_drive = MagicMock()
        mock_build.return_value = mock_drive

        mock_drive.files().get().execute.return_value = {"parents": ["parent123"]}

        from org_gdocs_sync.gdocs.client import GoogleDocsClient

        client = GoogleDocsClient()
        parent_id = client.get_parent_folder("doc456")

        assert parent_id == "parent123"


def test_get_parent_folder_no_parent():
    """Test getting parent folder when file has no parent (returns root)."""
    with (
        patch("org_gdocs_sync.gdocs.client.get_credentials"),
        patch("org_gdocs_sync.gdocs.client.build") as mock_build,
    ):
        mock_drive = MagicMock()
        mock_build.return_value = mock_drive

        mock_drive.files().get().execute.return_value = {}

        from org_gdocs_sync.gdocs.client import GoogleDocsClient

        client = GoogleDocsClient()
        parent_id = client.get_parent_folder("doc456")

        assert parent_id == "root"


def test_get_parent_folder_http_error():
    """Test that HttpError is caught and re-raised with context."""
    with (
        patch("org_gdocs_sync.gdocs.client.get_credentials"),
        patch("org_gdocs_sync.gdocs.client.build") as mock_build,
    ):
        mock_drive = MagicMock()
        mock_build.return_value = mock_drive

        resp = httplib2.Response({"status": 404})
        mock_drive.files().get().execute.side_effect = HttpError(resp, b"Not Found")

        from org_gdocs_sync.gdocs.client import GoogleDocsClient

        client = GoogleDocsClient()

        with pytest.raises(Exception) as exc_info:
            client.get_parent_folder("doc456")

        assert "Failed to get parent folder" in str(exc_info.value)
