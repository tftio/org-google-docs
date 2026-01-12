"""Tests for org to Google Docs converter."""

from pathlib import Path

from org_gdocs_sync.convert.org_to_gdocs import OrgToGDocsConverter
from org_gdocs_sync.models import NodeType, OrgDocument, OrgRenderedImage


def test_convert_rendered_image():
    """Test converting rendered image to insertInlineImage request."""
    doc = OrgDocument()
    doc.content = [
        OrgRenderedImage(
            type=NodeType.RENDERED_IMAGE,
            source_language="mermaid",
            local_path=Path("/tmp/diagram.svg"),
            header_args=":file diagram.svg",
            drive_url="https://drive.google.com/uc?id=abc123",
        ),
    ]

    converter = OrgToGDocsConverter()
    requests = converter.convert(doc)

    # Find the insertInlineImage request
    image_requests = [r for r in requests if "insertInlineImage" in r]
    assert len(image_requests) == 1

    img_req = image_requests[0]["insertInlineImage"]
    assert img_req["uri"] == "https://drive.google.com/uc?id=abc123"
    assert img_req["location"]["index"] == 1
