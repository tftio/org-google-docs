"""Tests for push workflow."""

import pytest
from unittest.mock import MagicMock, patch

from org_gdocs_sync.models import NodeType, OrgDocument, OrgSrcBlock


def test_process_babel_blocks(tmp_path):
    """Test processing babel blocks replaces them with rendered images."""
    from org_gdocs_sync.sync.push import process_babel_blocks

    # Create mock document with babel block
    doc = OrgDocument(path=str(tmp_path / "test.org"))
    doc.content = [
        OrgSrcBlock(
            type=NodeType.SRC_BLOCK,
            language="mermaid",
            content="graph TD\n    A --> B",
            header_args=":file diagram.svg :exports results",
            start_line=0,
            end_line=3,
        ),
    ]

    # Create the expected output file
    (tmp_path / "diagram.svg").write_text("<svg>test</svg>")

    with (
        patch("org_gdocs_sync.sync.push.execute_babel"),
        patch("org_gdocs_sync.sync.push.GoogleDocsClient") as mock_client_cls,
    ):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.get_parent_folder.return_value = "parent123"
        mock_client.get_document_title.return_value = "Test Doc"
        mock_client.get_or_create_folder.return_value = "assets456"
        mock_client.upload_image.return_value = "file789"

        result = process_babel_blocks(doc, "gdoc123", mock_client)

    # Original block should be replaced with rendered image
    assert len(result.content) == 1
    assert result.content[0].type == NodeType.RENDERED_IMAGE
    assert result.content[0].drive_url == "https://drive.google.com/uc?id=file789"


def test_process_babel_blocks_no_babel_blocks(tmp_path):
    """Test that documents without babel blocks are returned unchanged."""
    from org_gdocs_sync.sync.push import process_babel_blocks

    # Create mock document without babel blocks
    doc = OrgDocument(path=str(tmp_path / "test.org"))
    doc.content = [
        OrgSrcBlock(
            type=NodeType.SRC_BLOCK,
            language="python",
            content="print('hello')",
            header_args="",  # No :file argument
            start_line=0,
            end_line=2,
        ),
    ]

    mock_client = MagicMock()
    result = process_babel_blocks(doc, "gdoc123", mock_client)

    # Document should be returned unchanged
    assert len(result.content) == 1
    assert result.content[0].type == NodeType.SRC_BLOCK


def test_process_babel_blocks_in_heading(tmp_path):
    """Test babel blocks nested in headings are processed."""
    from org_gdocs_sync.models import OrgHeading
    from org_gdocs_sync.sync.push import process_babel_blocks

    # Create mock document with babel block inside heading
    babel_block = OrgSrcBlock(
        type=NodeType.SRC_BLOCK,
        language="mermaid",
        content="graph TD\n    A --> B",
        header_args=":file nested.svg :exports results",
        start_line=2,
        end_line=5,
    )
    heading = OrgHeading(
        type=NodeType.HEADING,
        level=1,
        title="Test Section",
        children=[babel_block],
    )
    doc = OrgDocument(path=str(tmp_path / "test.org"))
    doc.content = [heading]

    # Create the expected output file
    (tmp_path / "nested.svg").write_text("<svg>test</svg>")

    with patch("org_gdocs_sync.sync.push.execute_babel"):
        mock_client = MagicMock()
        mock_client.get_parent_folder.return_value = "parent123"
        mock_client.get_document_title.return_value = "Test Doc"
        mock_client.get_or_create_folder.return_value = "assets456"
        mock_client.upload_image.return_value = "file789"

        result = process_babel_blocks(doc, "gdoc123", mock_client)

    # Heading should still exist, but child should be replaced
    assert len(result.content) == 1
    assert result.content[0].type == NodeType.HEADING
    assert len(result.content[0].children) == 1
    assert result.content[0].children[0].type == NodeType.RENDERED_IMAGE


def test_process_babel_blocks_no_path():
    """Test that processing fails gracefully when doc has no path."""
    from org_gdocs_sync.sync.push import process_babel_blocks

    doc = OrgDocument(path=None)  # No path
    doc.content = [
        OrgSrcBlock(
            type=NodeType.SRC_BLOCK,
            language="mermaid",
            content="graph TD",
            header_args=":file diagram.svg",
            start_line=0,
            end_line=2,
        ),
    ]

    with pytest.raises(ValueError, match="document has no file path"):
        process_babel_blocks(doc, "gdoc123", MagicMock())
