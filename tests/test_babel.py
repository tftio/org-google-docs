"""Tests for babel execution module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from org_gdocs_sync.babel import (
    BabelExecutionError,
    BabelOutputError,
    execute_babel,
    extract_file_output,
    find_babel_blocks,
    parse_header_args,
    verify_babel_outputs,
)
from org_gdocs_sync.models import NodeType, OrgDocument, OrgHeading, OrgSrcBlock


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


def test_execute_babel_success(tmp_path):
    """Test successful babel execution."""
    org_file = tmp_path / "test.org"
    org_file.write_text("#+BEGIN_SRC python :file out.txt\nprint('hi')\n#+END_SRC")

    with patch("org_gdocs_sync.babel.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        execute_babel(org_file)

    mock_run.assert_called_once()
    call_args = mock_run.call_args
    assert "emacs" in call_args[0][0][0]
    assert "--batch" in call_args[0][0]


def test_execute_babel_failure(tmp_path):
    """Test babel execution failure raises error."""
    org_file = tmp_path / "test.org"
    org_file.write_text("#+BEGIN_SRC bad\n#+END_SRC")

    with patch("org_gdocs_sync.babel.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="Babel error")
        with pytest.raises(BabelExecutionError) as exc_info:
            execute_babel(org_file)

    assert "Babel error" in str(exc_info.value)


def test_verify_babel_outputs_all_present(tmp_path):
    """Test verification passes when all files exist."""
    (tmp_path / "diagram.svg").write_text("<svg></svg>")
    (tmp_path / "graph.png").write_bytes(b"PNG")

    expected = [
        tmp_path / "diagram.svg",
        tmp_path / "graph.png",
    ]

    # Should not raise
    verify_babel_outputs(expected)


def test_verify_babel_outputs_missing_file(tmp_path):
    """Test verification fails when file is missing."""
    expected = [tmp_path / "missing.svg"]

    with pytest.raises(BabelOutputError) as exc_info:
        verify_babel_outputs(expected)

    assert "missing.svg" in str(exc_info.value)
