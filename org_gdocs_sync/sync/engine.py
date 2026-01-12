"""Core sync engine for org-mode and Google Docs."""

import os
from datetime import datetime
from pathlib import Path

from ..convert.gdocs_to_org import GDocsToOrgConverter
from ..gdocs.client import GoogleDocsClient
from ..models import SyncState, SyncStatus
from ..org.parser import OrgParser
from ..org.writer import OrgWriter


class SyncEngine:
    """Core synchronization engine."""

    def __init__(self):
        """Initialize the sync engine."""
        self.parser = OrgParser()
        self.writer = OrgWriter()
        self.converter = GDocsToOrgConverter()
        self._client: GoogleDocsClient | None = None

    @property
    def client(self) -> GoogleDocsClient:
        """Lazy-load the Google Docs client."""
        if self._client is None:
            self._client = GoogleDocsClient()
        return self._client

    def get_sync_state(self, org_path: str) -> SyncState:
        """Get the current sync state for a document.

        Args:
            org_path: Path to org-mode file.

        Returns:
            Current sync state.
        """
        path = Path(org_path)

        if not path.exists():
            return SyncState(status=SyncStatus.NOT_INITIALIZED)

        doc = self.parser.parse_file(org_path)
        gdoc_id = doc.get_gdoc_id()

        if not gdoc_id:
            return SyncState(status=SyncStatus.NOT_INITIALIZED)

        # Check for local modifications
        last_sync_str = doc.get_last_sync()
        local_modified = False

        if last_sync_str:
            try:
                last_sync = datetime.fromisoformat(last_sync_str)
                file_mtime = datetime.fromtimestamp(os.path.getmtime(org_path))
                local_modified = file_mtime > last_sync
            except (ValueError, OSError):
                pass

        # Count pending annotations
        pending_comments = len(self.converter.get_pending_comments(doc))
        pending_suggestions = len(self.converter.get_pending_suggestions(doc))

        # Determine status
        if local_modified:
            status = SyncStatus.LOCAL_CHANGES
        else:
            status = SyncStatus.SYNCED

        return SyncState(
            status=status,
            gdoc_id=gdoc_id,
            last_sync=last_sync_str,
            last_push_rev=doc.metadata.get("LAST_PUSH_REV"),
            last_pull_rev=doc.metadata.get("LAST_PULL_REV"),
            pending_comments=pending_comments,
            pending_suggestions=pending_suggestions,
            local_modified=local_modified,
        )

    def initialize(self, org_path: str, title: str | None = None, gdoc_id: str | None = None) -> str:
        """Initialize sync for an org document.

        Either creates a new Google Doc or links to an existing one.

        Args:
            org_path: Path to org-mode file.
            title: Title for new document (if creating).
            gdoc_id: Existing document ID to link (if linking).

        Returns:
            Google Doc ID.

        Raises:
            ValueError: If document is already initialized.
        """
        doc = self.parser.parse_file(org_path)

        if doc.get_gdoc_id():
            raise ValueError(
                f"Document already initialized with GDOC_ID: {doc.get_gdoc_id()}"
            )

        if gdoc_id:
            # Link to existing document
            doc_id = gdoc_id
        else:
            # Create new document
            doc_title = title or doc.metadata.get("TITLE", "Untitled")
            doc_id = self.client.create_document(doc_title)

        # Update org file metadata
        doc.set_gdoc_id(doc_id)
        doc.set_last_sync(datetime.now().isoformat())

        self.writer.write_file(org_path, doc)

        return doc_id

    def get_document_url(self, gdoc_id: str) -> str:
        """Get the web URL for a Google Doc.

        Args:
            gdoc_id: Google Docs document ID.

        Returns:
            URL to open the document in browser.
        """
        return f"https://docs.google.com/document/d/{gdoc_id}/edit"
