"""Babel execution via Emacs batch mode."""

import re
from pathlib import Path


def parse_header_args(header_args: str) -> dict[str, str]:
    """Parse org-babel header arguments into a dictionary.

    Args:
        header_args: String like ":file diagram.svg :exports results"

    Returns:
        Dictionary of argument names to values.
    """
    if not header_args:
        return {}

    result = {}
    # Match :key value pairs (value can be a path with dots/slashes)
    pattern = re.compile(r":(\w+)\s+([^\s:]+)")
    for match in pattern.finditer(header_args):
        key = match.group(1)
        value = match.group(2)
        result[key] = value

    return result


def extract_file_output(header_args: str, org_dir: Path) -> Path | None:
    """Extract the expected output file path from header args.

    Args:
        header_args: Babel header arguments string.
        org_dir: Directory containing the org file.

    Returns:
        Absolute path to expected output file, or None if no :file arg.
    """
    parsed = parse_header_args(header_args)
    file_arg = parsed.get("file")
    if not file_arg:
        return None

    file_path = Path(file_arg)
    if file_path.is_absolute():
        return file_path
    return org_dir / file_path
