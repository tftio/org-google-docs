# Babel Image Rendering Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Render org-babel source blocks with `:file` headers via Emacs batch mode and insert resulting images into Google Docs.

**Architecture:** During push, scan for `:file` headers → invoke `emacs --batch` to execute babel → upload rendered images to Drive → insert inline images in Google Docs.

**Tech Stack:** Python subprocess (Emacs), google-api-python-client (Drive upload), existing converter infrastructure.

---

## Task 1: Add OrgRenderedImage Model

**Files:**
- Modify: `org_gdocs_sync/models.py:18-26` (add to NodeType enum)
- Modify: `org_gdocs_sync/models.py:96` (add new dataclass after OrgSrcBlock)
- Test: `tests/test_models.py` (new file)

**Step 1: Write the failing test**

Create `tests/test_models.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models.py -v`
Expected: FAIL with "cannot import name 'OrgRenderedImage'"

**Step 3: Add RENDERED_IMAGE to NodeType enum**

In `org_gdocs_sync/models.py`, after line 18 (`SRC_BLOCK = "src_block"`), add:

```python
    RENDERED_IMAGE = "rendered_image"
```

**Step 4: Add OrgRenderedImage dataclass**

In `org_gdocs_sync/models.py`, after OrgSrcBlock class (after line 96), add:

```python
@dataclass
class OrgRenderedImage(OrgNode):
    """A babel block that was rendered to an image file."""

    source_language: str = ""
    local_path: Path | None = None
    header_args: str = ""
    drive_url: str | None = None

    def __post_init__(self):
        if self.type is None:
            self.type = NodeType.RENDERED_IMAGE
```

Add `from pathlib import Path` to imports at top of file.

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_models.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add org_gdocs_sync/models.py tests/test_models.py
git commit -m "feat: add OrgRenderedImage model for babel-rendered images"
```

---

## Task 2: Update Parser to Capture Header Args

**Files:**
- Modify: `org_gdocs_sync/org/parser.py:24` (update regex)
- Modify: `org_gdocs_sync/org/parser.py:173-196` (capture header args)
- Modify: `org_gdocs_sync/models.py:87-96` (add header_args to OrgSrcBlock)
- Test: `tests/test_parser.py` (add tests)

**Step 1: Write the failing test**

Add to `tests/test_parser.py`:

```python
def test_src_block_with_file_header():
    """Test parsing source block with :file header argument."""
    content = '''#+BEGIN_SRC mermaid :file diagram.svg :exports results
graph TD
    A --> B
#+END_SRC
'''
    parser = OrgParser()
    doc = parser.parse_string(content)

    assert len(doc.content) == 1
    src = doc.content[0]
    assert src.type == NodeType.SRC_BLOCK
    assert src.language == "mermaid"
    assert src.header_args == ":file diagram.svg :exports results"
    assert "graph TD" in src.content


def test_src_block_without_header_args():
    """Test parsing source block without header arguments."""
    content = '''#+BEGIN_SRC python
print("hello")
#+END_SRC
'''
    parser = OrgParser()
    doc = parser.parse_string(content)

    src = doc.content[0]
    assert src.header_args == ""
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_parser.py::test_src_block_with_file_header -v`
Expected: FAIL with "OrgSrcBlock has no attribute 'header_args'"

**Step 3: Add header_args to OrgSrcBlock**

In `org_gdocs_sync/models.py`, modify OrgSrcBlock:

```python
@dataclass
class OrgSrcBlock(OrgNode):
    """#+BEGIN_SRC ... #+END_SRC."""

    language: str | None = None
    content: str = ""
    header_args: str = ""

    def __post_init__(self):
        if self.type is None:
            self.type = NodeType.SRC_BLOCK
```

**Step 4: Update parser regex to capture header args**

In `org_gdocs_sync/org/parser.py`, line 24, change:

```python
SRC_BEGIN_RE = re.compile(r"^#\+BEGIN_SRC\s*(\w*)\s*$", re.IGNORECASE)
```

To:

```python
SRC_BEGIN_RE = re.compile(r"^#\+BEGIN_SRC\s*(\w*)\s*(.*)$", re.IGNORECASE)
```

**Step 5: Update parser to capture header args**

In `org_gdocs_sync/org/parser.py`, in `_parse_content` method around line 173-196, change:

```python
            # Source block
            src_begin_match = SRC_BEGIN_RE.match(line)
            if src_begin_match:
                language = src_begin_match.group(1) or None
                content_lines = []
                block_start = i
                i += 1
                while i < len(lines):
                    block_line = lines[i].rstrip("\n\r")
                    if SRC_END_RE.match(block_line):
                        break
                    content_lines.append(block_line)
                    i += 1

                src_block = OrgSrcBlock(
                    type=NodeType.SRC_BLOCK,
                    language=language,
                    content="\n".join(content_lines),
                    start_line=start_line + block_start,
                    end_line=start_line + i,
                )
```

To:

```python
            # Source block
            src_begin_match = SRC_BEGIN_RE.match(line)
            if src_begin_match:
                language = src_begin_match.group(1) or None
                header_args = src_begin_match.group(2).strip()
                content_lines = []
                block_start = i
                i += 1
                while i < len(lines):
                    block_line = lines[i].rstrip("\n\r")
                    if SRC_END_RE.match(block_line):
                        break
                    content_lines.append(block_line)
                    i += 1

                src_block = OrgSrcBlock(
                    type=NodeType.SRC_BLOCK,
                    language=language,
                    content="\n".join(content_lines),
                    header_args=header_args,
                    start_line=start_line + block_start,
                    end_line=start_line + i,
                )
```

**Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_parser.py -v`
Expected: PASS

**Step 7: Commit**

```bash
git add org_gdocs_sync/models.py org_gdocs_sync/org/parser.py tests/test_parser.py
git commit -m "feat: capture header args when parsing source blocks"
```

---

## Task 3: Create Babel Header Args Parser

**Files:**
- Create: `org_gdocs_sync/babel.py`
- Test: `tests/test_babel.py` (new file)

**Step 1: Write the failing test**

Create `tests/test_babel.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_babel.py -v`
Expected: FAIL with "No module named 'org_gdocs_sync.babel'"

**Step 3: Create babel.py with header arg parsing**

Create `org_gdocs_sync/babel.py`:

```python
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
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_babel.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add org_gdocs_sync/babel.py tests/test_babel.py
git commit -m "feat: add babel header argument parsing"
```

---

## Task 4: Add Babel Block Detection

**Files:**
- Modify: `org_gdocs_sync/babel.py`
- Test: `tests/test_babel.py`

**Step 1: Write the failing test**

Add to `tests/test_babel.py`:

```python
from org_gdocs_sync.babel import find_babel_blocks
from org_gdocs_sync.models import OrgDocument, OrgSrcBlock, NodeType


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
    from org_gdocs_sync.models import OrgHeading

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
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_babel.py::test_find_babel_blocks_with_file -v`
Expected: FAIL with "cannot import name 'find_babel_blocks'"

**Step 3: Implement find_babel_blocks**

Add to `org_gdocs_sync/babel.py`:

```python
from .models import NodeType, OrgDocument, OrgNode, OrgSrcBlock


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
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_babel.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add org_gdocs_sync/babel.py tests/test_babel.py
git commit -m "feat: add babel block detection with :file header"
```

---

## Task 5: Add Emacs Batch Execution

**Files:**
- Modify: `org_gdocs_sync/babel.py`
- Test: `tests/test_babel.py`

**Step 1: Write the failing test**

Add to `tests/test_babel.py`:

```python
import subprocess
from unittest.mock import patch, MagicMock

from org_gdocs_sync.babel import execute_babel, BabelExecutionError


def test_execute_babel_success(tmp_path):
    """Test successful babel execution."""
    org_file = tmp_path / "test.org"
    org_file.write_text("#+BEGIN_SRC python :file out.txt\nprint('hi')\n#+END_SRC")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        execute_babel(org_file)

    mock_run.assert_called_once()
    call_args = mock_run.call_args
    assert "emacs" in call_args[0][0][0]
    assert "--batch" in call_args[0][0]


def test_execute_babel_failure(tmp_path):
    """Test babel execution failure raises error."""
    import pytest

    org_file = tmp_path / "test.org"
    org_file.write_text("#+BEGIN_SRC bad\n#+END_SRC")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="Babel error")
        with pytest.raises(BabelExecutionError) as exc_info:
            execute_babel(org_file)

    assert "Babel error" in str(exc_info.value)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_babel.py::test_execute_babel_success -v`
Expected: FAIL with "cannot import name 'execute_babel'"

**Step 3: Implement execute_babel**

Add to `org_gdocs_sync/babel.py`:

```python
import subprocess


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
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_babel.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add org_gdocs_sync/babel.py tests/test_babel.py
git commit -m "feat: add Emacs batch babel execution"
```

---

## Task 6: Add Output File Verification

**Files:**
- Modify: `org_gdocs_sync/babel.py`
- Test: `tests/test_babel.py`

**Step 1: Write the failing test**

Add to `tests/test_babel.py`:

```python
from org_gdocs_sync.babel import verify_babel_outputs, BabelOutputError


def test_verify_babel_outputs_all_present(tmp_path):
    """Test verification passes when all files exist."""
    # Create expected output files
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
    import pytest

    expected = [
        tmp_path / "missing.svg",
    ]

    with pytest.raises(BabelOutputError) as exc_info:
        verify_babel_outputs(expected)

    assert "missing.svg" in str(exc_info.value)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_babel.py::test_verify_babel_outputs_all_present -v`
Expected: FAIL with "cannot import name 'verify_babel_outputs'"

**Step 3: Implement verify_babel_outputs**

Add to `org_gdocs_sync/babel.py`:

```python
class BabelOutputError(Exception):
    """Raised when expected babel output files are missing."""

    pass


def verify_babel_outputs(expected_files: list[Path]) -> None:
    """Verify all expected output files exist.

    Args:
        expected_files: List of expected output file paths.

    Raises:
        BabelOutputError: If any expected file is missing.
    """
    missing = [f for f in expected_files if not f.exists()]
    if missing:
        missing_str = "\n  ".join(str(f) for f in missing)
        raise BabelOutputError(
            f"Babel failed to produce expected output files:\n  {missing_str}"
        )
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_babel.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add org_gdocs_sync/babel.py tests/test_babel.py
git commit -m "feat: add babel output file verification"
```

---

## Task 7: Add Drive Folder Management

**Files:**
- Modify: `org_gdocs_sync/gdocs/client.py`
- Test: `tests/test_client.py` (new file)

**Step 1: Write the failing test**

Create `tests/test_client.py`:

```python
"""Tests for Google Docs client."""

from unittest.mock import MagicMock, patch


def test_get_or_create_folder_exists():
    """Test getting existing folder."""
    with patch("org_gdocs_sync.gdocs.client.get_credentials"):
        with patch("org_gdocs_sync.gdocs.client.build") as mock_build:
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
    with patch("org_gdocs_sync.gdocs.client.get_credentials"):
        with patch("org_gdocs_sync.gdocs.client.build") as mock_build:
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
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_client.py -v`
Expected: FAIL with "GoogleDocsClient has no attribute 'get_or_create_folder'"

**Step 3: Implement get_or_create_folder**

Add to `org_gdocs_sync/gdocs/client.py`, after `get_file_metadata` method (around line 384):

```python
    def get_or_create_folder(self, name: str, parent_id: str) -> str:
        """Get or create a folder in Google Drive.

        Args:
            name: Folder name.
            parent_id: Parent folder ID.

        Returns:
            Folder ID.
        """
        # Check if folder exists
        query = (
            f"name='{name}' and "
            f"'{parent_id}' in parents and "
            f"mimeType='application/vnd.google-apps.folder' and "
            f"trashed=false"
        )
        response = (
            self.drive_service.files()
            .list(q=query, fields="files(id,name)", pageSize=1)
            .execute()
        )

        files = response.get("files", [])
        if files:
            return files[0]["id"]

        # Create folder
        file_metadata = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        folder = (
            self.drive_service.files()
            .create(body=file_metadata, fields="id")
            .execute()
        )
        return folder["id"]
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_client.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add org_gdocs_sync/gdocs/client.py tests/test_client.py
git commit -m "feat: add Drive folder management"
```

---

## Task 8: Add Image Upload to Drive

**Files:**
- Modify: `org_gdocs_sync/gdocs/client.py`
- Test: `tests/test_client.py`

**Step 1: Write the failing test**

Add to `tests/test_client.py`:

```python
from pathlib import Path


def test_upload_image(tmp_path):
    """Test uploading image to Drive."""
    # Create test image file
    test_image = tmp_path / "test.svg"
    test_image.write_text("<svg></svg>")

    with patch("org_gdocs_sync.gdocs.client.get_credentials"):
        with patch("org_gdocs_sync.gdocs.client.build") as mock_build:
            mock_drive = MagicMock()
            mock_build.return_value = mock_drive

            # Mock upload
            mock_drive.files().create().execute.return_value = {
                "id": "file123",
            }

            from org_gdocs_sync.gdocs.client import GoogleDocsClient

            client = GoogleDocsClient()
            file_id = client.upload_image(test_image, "folder456")

            assert file_id == "file123"


def test_upload_image_update_existing(tmp_path):
    """Test updating existing image in Drive."""
    test_image = tmp_path / "test.svg"
    test_image.write_text("<svg></svg>")

    with patch("org_gdocs_sync.gdocs.client.get_credentials"):
        with patch("org_gdocs_sync.gdocs.client.build") as mock_build:
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
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_client.py::test_upload_image -v`
Expected: FAIL with "GoogleDocsClient has no attribute 'upload_image'"

**Step 3: Implement upload_image**

Add import at top of `org_gdocs_sync/gdocs/client.py`:

```python
from googleapiclient.http import MediaFileUpload
```

Add method after `get_or_create_folder`:

```python
    def upload_image(self, local_path: Path, folder_id: str) -> str:
        """Upload or update an image file in Drive.

        Args:
            local_path: Path to local image file.
            folder_id: ID of folder to upload to.

        Returns:
            File ID of uploaded/updated file.
        """
        from pathlib import Path

        local_path = Path(local_path)
        filename = local_path.name

        # Determine mimetype
        suffix = local_path.suffix.lower()
        mimetypes = {
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
        }
        mimetype = mimetypes.get(suffix, "application/octet-stream")

        # Check if file exists
        query = (
            f"name='{filename}' and "
            f"'{folder_id}' in parents and "
            f"trashed=false"
        )
        response = (
            self.drive_service.files()
            .list(q=query, fields="files(id)", pageSize=1)
            .execute()
        )

        files = response.get("files", [])
        media = MediaFileUpload(str(local_path), mimetype=mimetype)

        if files:
            # Update existing file
            file_id = files[0]["id"]
            self.drive_service.files().update(
                fileId=file_id,
                media_body=media,
            ).execute()
            return file_id
        else:
            # Create new file
            file_metadata = {
                "name": filename,
                "parents": [folder_id],
            }
            result = (
                self.drive_service.files()
                .create(body=file_metadata, media_body=media, fields="id")
                .execute()
            )
            return result["id"]
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_client.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add org_gdocs_sync/gdocs/client.py tests/test_client.py
git commit -m "feat: add image upload to Drive with update support"
```

---

## Task 9: Add Get Parent Folder Method

**Files:**
- Modify: `org_gdocs_sync/gdocs/client.py`
- Test: `tests/test_client.py`

**Step 1: Write the failing test**

Add to `tests/test_client.py`:

```python
def test_get_parent_folder():
    """Test getting parent folder of a document."""
    with patch("org_gdocs_sync.gdocs.client.get_credentials"):
        with patch("org_gdocs_sync.gdocs.client.build") as mock_build:
            mock_drive = MagicMock()
            mock_build.return_value = mock_drive

            mock_drive.files().get().execute.return_value = {
                "parents": ["parent123"]
            }

            from org_gdocs_sync.gdocs.client import GoogleDocsClient

            client = GoogleDocsClient()
            parent_id = client.get_parent_folder("doc456")

            assert parent_id == "parent123"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_client.py::test_get_parent_folder -v`
Expected: FAIL with "GoogleDocsClient has no attribute 'get_parent_folder'"

**Step 3: Implement get_parent_folder**

Add to `org_gdocs_sync/gdocs/client.py`:

```python
    def get_parent_folder(self, file_id: str) -> str:
        """Get the parent folder ID of a file.

        Args:
            file_id: Google Drive file ID.

        Returns:
            Parent folder ID.
        """
        response = (
            self.drive_service.files()
            .get(fileId=file_id, fields="parents")
            .execute()
        )
        parents = response.get("parents", [])
        return parents[0] if parents else "root"
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_client.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add org_gdocs_sync/gdocs/client.py tests/test_client.py
git commit -m "feat: add get_parent_folder method"
```

---

## Task 10: Add Inline Image Insertion to Converter

**Files:**
- Modify: `org_gdocs_sync/convert/org_to_gdocs.py`
- Test: `tests/test_converter.py` (new file)

**Step 1: Write the failing test**

Create `tests/test_converter.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_converter.py -v`
Expected: FAIL (no handling for RENDERED_IMAGE type)

**Step 3: Add import for OrgRenderedImage**

In `org_gdocs_sync/convert/org_to_gdocs.py`, update imports:

```python
from ..models import (
    NodeType,
    OrgDocument,
    OrgHeading,
    OrgLink,
    OrgList,
    OrgListItem,
    OrgNode,
    OrgParagraph,
    OrgRenderedImage,
    OrgSrcBlock,
    OrgTable,
    OrgText,
)
```

**Step 4: Add RENDERED_IMAGE handling in _convert_node**

In `org_gdocs_sync/convert/org_to_gdocs.py`, in `_convert_node` method (around line 87-106), add case before SRC_BLOCK:

```python
        elif node.type == NodeType.RENDERED_IMAGE:
            self._convert_rendered_image(node)
```

**Step 5: Add _convert_rendered_image method**

Add after `_convert_src_block` method (around line 367):

```python
    def _convert_rendered_image(self, node: OrgNode) -> None:
        """Convert rendered image to inline image insertion."""
        img = node if isinstance(node, OrgRenderedImage) else None
        if not img or not img.drive_url:
            return

        self.requests.append(
            {
                "insertInlineImage": {
                    "location": {"index": self.current_index},
                    "uri": img.drive_url,
                    "objectSize": {
                        "height": {"magnitude": 300, "unit": "PT"},
                        "width": {"magnitude": 400, "unit": "PT"},
                    },
                }
            }
        )
        # Image takes one index position
        self.current_index += 1

        # Add newline after image
        self._insert_text("\n")
```

**Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_converter.py -v`
Expected: PASS

**Step 7: Commit**

```bash
git add org_gdocs_sync/convert/org_to_gdocs.py tests/test_converter.py
git commit -m "feat: add inline image insertion to converter"
```

---

## Task 11: Add Babel Processing to Push Workflow

**Files:**
- Modify: `org_gdocs_sync/sync/push.py`
- Test: `tests/test_push.py` (new file)

**Step 1: Write the failing test**

Create `tests/test_push.py`:

```python
"""Tests for push workflow."""

from pathlib import Path
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

    with patch("org_gdocs_sync.sync.push.execute_babel") as mock_exec:
        with patch("org_gdocs_sync.sync.push.GoogleDocsClient") as mock_client_cls:
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
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_push.py -v`
Expected: FAIL with "cannot import name 'process_babel_blocks'"

**Step 3: Implement process_babel_blocks**

Add imports at top of `org_gdocs_sync/sync/push.py`:

```python
from pathlib import Path

from ..babel import (
    execute_babel,
    extract_file_output,
    find_babel_blocks,
    parse_header_args,
    verify_babel_outputs,
)
from ..models import NodeType, OrgRenderedImage
```

Add function before `push`:

```python
def process_babel_blocks(
    doc: OrgDocument, gdoc_id: str, client: GoogleDocsClient
) -> OrgDocument:
    """Process babel blocks: execute, upload, and replace with images.

    Args:
        doc: Parsed org document.
        gdoc_id: Google Doc ID.
        client: Google Docs client.

    Returns:
        Document with babel blocks replaced by rendered images.
    """
    from copy import deepcopy

    # Find blocks with :file output
    babel_blocks = find_babel_blocks(doc)
    if not babel_blocks:
        return doc

    org_dir = Path(doc.path).parent if doc.path else Path.cwd()

    # Collect expected output files
    expected_files: list[tuple[OrgSrcBlock, Path]] = []
    for block in babel_blocks:
        output_path = extract_file_output(block.header_args, org_dir)
        if output_path:
            expected_files.append((block, output_path))

    if not expected_files:
        return doc

    # Execute babel
    execute_babel(Path(doc.path))

    # Verify outputs
    verify_babel_outputs([path for _, path in expected_files])

    # Upload images and create replacement nodes
    parent_id = client.get_parent_folder(gdoc_id)
    doc_title = client.get_document_title(gdoc_id)
    assets_folder = client.get_or_create_folder(f"{doc_title}_assets", parent_id)

    replacements: dict[int, OrgRenderedImage] = {}
    for block, output_path in expected_files:
        file_id = client.upload_image(output_path, assets_folder)
        drive_url = f"https://drive.google.com/uc?id={file_id}"

        rendered = OrgRenderedImage(
            type=NodeType.RENDERED_IMAGE,
            source_language=block.language or "",
            local_path=output_path,
            header_args=block.header_args,
            drive_url=drive_url,
            start_line=block.start_line,
            end_line=block.end_line,
        )
        replacements[id(block)] = rendered

    # Replace blocks in document tree
    def replace_blocks(nodes: list) -> list:
        result = []
        for node in nodes:
            if id(node) in replacements:
                result.append(replacements[id(node)])
            else:
                if hasattr(node, "children"):
                    node.children = replace_blocks(node.children)
                result.append(node)
        return result

    doc = deepcopy(doc)
    doc.content = replace_blocks(doc.content)
    return doc
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_push.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add org_gdocs_sync/sync/push.py tests/test_push.py
git commit -m "feat: add babel block processing to push workflow"
```

---

## Task 12: Integrate Babel Processing into Push

**Files:**
- Modify: `org_gdocs_sync/sync/push.py`
- Test: Integration test

**Step 1: Update push function**

In `org_gdocs_sync/sync/push.py`, modify the `push` function to call `process_babel_blocks`:

After parsing (line 38) and before converting (line 46), add:

```python
    # Process babel blocks (execute, upload images, replace with rendered nodes)
    doc = process_babel_blocks(doc, gdoc_id, client)
```

The updated section should look like:

```python
    # Parse org file
    doc = parser.parse_file(org_path)

    # Validate
    gdoc_id = doc.get_gdoc_id()
    if not gdoc_id:
        raise ValueError("No GDOC_ID found in document. Run 'sync init' first.")

    # Process babel blocks (execute, upload images, replace with rendered nodes)
    doc = process_babel_blocks(doc, gdoc_id, client)

    # Convert org content to Google Docs requests
    requests = converter.convert(doc)
```

**Step 2: Run all tests**

Run: `uv run pytest -v`
Expected: PASS

**Step 3: Commit**

```bash
git add org_gdocs_sync/sync/push.py
git commit -m "feat: integrate babel processing into push workflow"
```

---

## Task 13: Manual Integration Test

**Files:** None (manual testing)

**Step 1: Create test org file**

Create a test file with a mermaid diagram to verify end-to-end functionality.

**Step 2: Test the flow**

```bash
# Initialize a test document
org-gdocs init /path/to/test.org --title "Babel Test"

# Push with babel rendering
org-gdocs push /path/to/test.org
```

**Step 3: Verify in Google Docs**

Open the Google Doc and confirm:
1. Mermaid diagram appears as an image
2. Image is in the `{Title}_assets` folder in Drive
3. Non-diagram source blocks still appear as monospace text

**Step 4: Final commit**

```bash
git add -A
git commit -m "feat: complete babel image rendering implementation"
```

---

## Dependency Graph

```
Task 1 (OrgRenderedImage model)
    │
    ▼
Task 2 (Parser header args) ──────────────────┐
    │                                          │
    ▼                                          │
Task 3 (Header arg parsing) ◄─────────────────┤
    │                                          │
    ▼                                          │
Task 4 (Babel block detection)                 │
    │                                          │
    ▼                                          │
Task 5 (Emacs execution)                       │
    │                                          │
    ▼                                          │
Task 6 (Output verification)                   │
                                               │
Task 7 (Drive folder mgmt) ◄──────────────────┤
    │                                          │
    ▼                                          │
Task 8 (Image upload)                          │
    │                                          │
    ▼                                          │
Task 9 (Parent folder)                         │
                                               │
Task 10 (Converter image insert) ◄────────────┘
    │
    ▼
Task 11 (Push babel processing)
    │
    ▼
Task 12 (Integration)
    │
    ▼
Task 13 (Manual test)
```

**Critical path:** 1 → 2 → 3 → 4 → 5 → 6 → 11 → 12 → 13

**Parallel tracks:**
- Tasks 7-9 (Drive operations) can run parallel to Tasks 3-6
- Task 10 (Converter) can run parallel to Tasks 5-9
