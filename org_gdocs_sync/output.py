"""Output formatting for CLI - plist (sexpr) and JSON."""

import json
from typing import Any


def to_plist(data: Any, indent: int = 0) -> str:
    """Convert Python data to Elisp plist format.

    Supports:
    - dict -> plist with keyword keys (:key value ...)
    - list -> list (item1 item2 ...)
    - str -> "quoted string"
    - int/float -> number
    - bool -> t or nil
    - None -> nil

    Args:
        data: Python data structure to convert.
        indent: Current indentation level (for formatting).

    Returns:
        String in Elisp plist format.
    """
    if data is None:
        return "nil"

    if isinstance(data, bool):
        return "t" if data else "nil"

    if isinstance(data, (int, float)):
        return str(data)

    if isinstance(data, str):
        # Escape backslashes and double quotes
        escaped = data.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    if isinstance(data, dict):
        if not data:
            return "()"
        parts = []
        for key, value in data.items():
            # Convert key to keyword (e.g., "status" -> ":status")
            keyword = f":{_to_kebab_case(key)}"
            parts.append(f"{keyword} {to_plist(value)}")
        return "(" + " ".join(parts) + ")"

    if isinstance(data, (list, tuple)):
        if not data:
            return "()"
        parts = [to_plist(item) for item in data]
        return "(" + " ".join(parts) + ")"

    # Fallback: convert to string
    return to_plist(str(data))


def to_plist_pretty(data: Any, indent: int = 0) -> str:
    """Convert Python data to pretty-printed Elisp plist format.

    Similar to to_plist but with newlines for readability.
    """
    prefix = " " * indent

    if data is None:
        return "nil"

    if isinstance(data, bool):
        return "t" if data else "nil"

    if isinstance(data, (int, float)):
        return str(data)

    if isinstance(data, str):
        escaped = data.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    if isinstance(data, dict):
        if not data:
            return "()"
        lines = []
        for key, value in data.items():
            keyword = f":{_to_kebab_case(key)}"
            val_str = to_plist_pretty(value, indent + 1)
            lines.append(f"{keyword} {val_str}")
        inner = f"\n{prefix} ".join(lines)
        return f"({inner})"

    if isinstance(data, (list, tuple)):
        if not data:
            return "()"
        # For lists of dicts (common case), put each on own line
        if data and isinstance(data[0], dict):
            parts = [to_plist_pretty(item, indent + 1) for item in data]
            inner = f"\n{prefix} ".join(parts)
            return f"({inner})"
        parts = [to_plist_pretty(item, indent) for item in data]
        return "(" + " ".join(parts) + ")"

    return to_plist_pretty(str(data))


def _to_kebab_case(s: str) -> str:
    """Convert snake_case or camelCase to kebab-case.

    Examples:
        gdoc_id -> gdoc-id
        lastSync -> last-sync
        pendingComments -> pending-comments
    """
    result = []
    for i, char in enumerate(s):
        if char == "_":
            result.append("-")
        elif char.isupper():
            if i > 0:
                result.append("-")
            result.append(char.lower())
        else:
            result.append(char)
    return "".join(result)


def format_output(data: Any, *, use_json: bool = False, pretty: bool = True) -> str:
    """Format data for output based on format preference.

    Args:
        data: Data structure to format.
        use_json: If True, output JSON. Otherwise output plist.
        pretty: If True, use pretty-printing with newlines.

    Returns:
        Formatted string.
    """
    if use_json:
        if pretty:
            return json.dumps(data, indent=2)
        return json.dumps(data)

    if pretty:
        return to_plist_pretty(data)
    return to_plist(data)


def print_output(data: Any, *, use_json: bool = False, pretty: bool = True) -> None:
    """Print formatted output to stdout.

    Args:
        data: Data structure to output.
        use_json: If True, output JSON. Otherwise output plist.
        pretty: If True, use pretty-printing with newlines.
    """
    print(format_output(data, use_json=use_json, pretty=pretty))
