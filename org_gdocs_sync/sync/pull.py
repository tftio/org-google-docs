"""Pull workflow: Google Docs -> org-mode."""

import os
import shutil
from datetime import datetime

from ..convert.gdocs_to_org import GDocsToOrgConverter
from ..gdocs.client import GoogleDocsClient
from ..org.parser import OrgParser
from ..org.writer import OrgWriter


def pull(org_path: str, force: bool = False, backup: bool = False) -> dict:
    """Pull suggestions and comments from Google Docs.

    Steps:
    1. Check for local changes
    2. Optionally create backup
    3. Fetch document with suggestions
    4. Fetch comments
    5. Create annotation blocks
    6. Update metadata

    Args:
        org_path: Path to org-mode file.
        force: If True, pull despite local changes.
        backup: If True, create backup before pulling.

    Returns:
        Dictionary with pull results.

    Raises:
        ValueError: If document is not initialized.
        RuntimeError: If local changes detected and neither force nor backup specified.
    """
    parser = OrgParser()
    client = GoogleDocsClient()
    converter = GDocsToOrgConverter()
    writer = OrgWriter()

    # Parse org file
    doc = parser.parse_file(org_path)

    # Validate
    gdoc_id = doc.get_gdoc_id()
    if not gdoc_id:
        raise ValueError("No GDOC_ID found in document. Run 'sync init' first.")

    # Conflict detection
    last_sync_str = doc.get_last_sync()
    backup_path = None

    if last_sync_str:
        try:
            last_sync = datetime.fromisoformat(last_sync_str)
            file_mtime = datetime.fromtimestamp(os.path.getmtime(org_path))

            if file_mtime > last_sync:
                if not force and not backup:
                    raise RuntimeError(
                        "Local changes detected since last sync. "
                        "Use --force to pull anyway, or --backup to create backup first."
                    )

                if backup:
                    backup_path = f"{org_path}.backup.{int(file_mtime.timestamp())}"
                    shutil.copy(org_path, backup_path)
        except ValueError:
            pass  # Invalid timestamp, proceed anyway

    # Fetch document with suggestions
    gdoc = client.get_document(gdoc_id, suggestions_inline=True)

    # Extract suggestions from document
    suggestions = client.extract_suggestions(gdoc)

    # Fetch comments via Drive API
    comments = client.list_comments(gdoc_id)

    # Add annotations to org document
    converter.add_annotations(doc, comments, suggestions)

    # Update metadata
    rev_id = client.get_latest_revision(gdoc_id)
    doc.metadata["LAST_PULL_REV"] = rev_id or ""
    doc.metadata["LAST_SYNC"] = datetime.now().isoformat()

    # Save updated org file
    writer.write_file(org_path, doc)

    return {
        "gdoc_id": gdoc_id,
        "comments_added": len(comments),
        "suggestions_added": len(suggestions),
        "backup_path": backup_path,
        "revision": rev_id,
    }
