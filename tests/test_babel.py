"""Tests for babel execution module."""

from pathlib import Path

from org_gdocs_sync.babel import parse_header_args, extract_file_output, find_babel_blocks
from org_gdocs_sync.models import OrgDocument, OrgSrcBlock, OrgHeading, NodeType


def test_parse_header_args_with_file():
    """Test parsing header args with :file."""
    args = ":file diagram.svg :exports results"
    parsed = parse_header_args(args)
    assert parsed["file"] == "diagram.svg"
    assert parsed["exports"] == "results"


def test_parse_header_args_empty():
    """Test parsing empty header args."""
    parsed = parse_header_args("")
    assert parsed == {}


def test_parse_header_args_with_complex_file():
    """Test parsing header args with path in :file."""
    args = ":file ./images/flow.svg :exports results"
    parsed = parse_header_args(args)
    assert parsed["file"] == "./images/flow.svg"


def test_extract_file_output_with_file():
    """Test extracting file output path."""
    header_args = ":file diagram.svg :exports results"
    org_dir = Path("/home/user/docs")
    result = extract_file_output(header_args, org_dir)
    assert result == Path("/home/user/docs/diagram.svg")


def test_extract_file_output_no_file():
    """Test extracting file output when no :file present."""
    header_args = ":exports code"
    org_dir = Path("/home/user/docs")
    result = extract_file_output(header_args, org_dir)
    assert result is None


def test_find_babel_blocks_with_file():
    """Test finding blocks that have :file output."""
    doc = OrgDocument()
    doc.content = [
        OrgSrcBlock(
            type=NodeType.SRC_BLOCK,
            language="mermaid",
            content="graph TD\n    A --> B",
            header_args=":file diagram.svg :exports results",
            start_line=0,
            end_line=3,
        ),
        OrgSrcBlock(
            type=NodeType.SRC_BLOCK,
            language="python",
            content="print('hello')",
            header_args="",
            start_line=5,
            end_line=7,
        ),
    ]

    blocks = find_babel_blocks(doc)
    assert len(blocks) == 1
    assert blocks[0].language == "mermaid"


def test_find_babel_blocks_nested_in_heading():
    """Test finding blocks nested under headings."""
    heading = OrgHeading(
        type=NodeType.HEADING,
        level=1,
        title="Test",
        children=[
            OrgSrcBlock(
                type=NodeType.SRC_BLOCK,
                language="dot",
                content="digraph { A -> B }",
                header_args=":file graph.png",
                start_line=2,
                end_line=4,
            ),
        ],
    )
    doc = OrgDocument()
    doc.content = [heading]

    blocks = find_babel_blocks(doc)
    assert len(blocks) == 1
    assert blocks[0].language == "dot"
