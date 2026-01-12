"""Tests for data models."""

from pathlib import Path

from org_gdocs_sync.models import NodeType, OrgRenderedImage


def test_rendered_image_creation():
    """Test OrgRenderedImage can be created with required fields."""
    img = OrgRenderedImage(
        type=NodeType.RENDERED_IMAGE,
        source_language="mermaid",
        local_path=Path("/tmp/diagram.svg"),
        header_args=":file diagram.svg :exports results",
    )
    assert img.source_language == "mermaid"
    assert img.local_path == Path("/tmp/diagram.svg")
    assert img.header_args == ":file diagram.svg :exports results"
    assert img.drive_url is None


def test_rendered_image_with_drive_url():
    """Test OrgRenderedImage with drive_url set."""
    img = OrgRenderedImage(
        type=NodeType.RENDERED_IMAGE,
        source_language="dot",
        local_path=Path("/tmp/graph.png"),
        header_args=":file graph.png",
        drive_url="https://drive.google.com/uc?id=abc123",
    )
    assert img.drive_url == "https://drive.google.com/uc?id=abc123"


def test_rendered_image_auto_type():
    """Test OrgRenderedImage auto-assigns type via __post_init__."""
    img = OrgRenderedImage(source_language="mermaid")
    assert img.type == NodeType.RENDERED_IMAGE
