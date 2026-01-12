"""Babel execution via Emacs batch mode."""

import re
import subprocess
from pathlib import Path

from .models import NodeType, OrgDocument, OrgNode, OrgSrcBlock


class BabelExecutionError(Exception):
    """Raised when Emacs babel execution fails."""

    pass


def execute_babel(org_path: Path) -> None:
    """Execute org-babel-execute-buffer via Emacs batch mode.

    Args:
        org_path: Path to the org file.

    Raises:
        BabelExecutionError: If Emacs exits with non-zero status.
    """
    org_path = Path(org_path).resolve()

    cmd = [
        "emacs",
        "--batch",
        "--eval", "(require 'org)",
        "--eval", "(setq org-confirm-babel-evaluate nil)",
        "--visit", str(org_path),
        "--eval", "(org-babel-execute-buffer)",
        "--kill",
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=org_path.parent,
    )

    if result.returncode != 0:
        raise BabelExecutionError(
            f"Emacs babel execution failed (exit {result.returncode}):\n"
            f"{result.stderr}"
        )


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


def find_babel_blocks(doc: OrgDocument) -> list[OrgSrcBlock]:
    """Find all source blocks with :file output.

    Args:
        doc: Parsed org document.

    Returns:
        List of OrgSrcBlock nodes that have :file header args.
    """
    blocks = []

    def walk(nodes: list[OrgNode]) -> None:
        for node in nodes:
            if node.type == NodeType.SRC_BLOCK:
                src = node if isinstance(node, OrgSrcBlock) else None
                if src and src.header_args:
                    parsed = parse_header_args(src.header_args)
                    if "file" in parsed:
                        blocks.append(src)
            if hasattr(node, "children"):
                walk(node.children)

    walk(doc.content)
    return blocks
