"""Tests for babel execution module."""

from pathlib import Path

from org_gdocs_sync.babel import parse_header_args, extract_file_output


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
