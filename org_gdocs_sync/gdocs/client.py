"""Google Docs and Drive API client."""

from datetime import datetime
from pathlib import Path
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from ..auth import get_credentials
from ..models import Comment, CommentReply, Suggestion


class GoogleDocsClient:
    """Wrapper for Google Docs and Drive APIs."""

    def __init__(self):
        """Initialize the client with authenticated credentials."""
        creds = get_credentials()
        self.docs_service = build("docs", "v1", credentials=creds)
        self.drive_service = build("drive", "v3", credentials=creds)

    # Document operations

    def create_document(self, title: str) -> str:
        """Create a new Google Doc.

        Args:
            title: Title for the new document.

        Returns:
            Document ID of the created document.
        """
        doc = self.docs_service.documents().create(body={"title": title}).execute()
        return doc["documentId"]

    def get_document(self, doc_id: str, suggestions_inline: bool = False) -> dict[str, Any]:
        """Get document content.

        Args:
            doc_id: Google Docs document ID.
            suggestions_inline: If True, include suggestions in the document structure.

        Returns:
            Document structure from the API.
        """
        params = {"documentId": doc_id}
        if suggestions_inline:
            params["suggestionsViewMode"] = "SUGGESTIONS_INLINE"

        return self.docs_service.documents().get(**params).execute()

    def get_document_title(self, doc_id: str) -> str:
        """Get document title.

        Args:
            doc_id: Google Docs document ID.

        Returns:
            Document title.
        """
        doc = self.get_document(doc_id)
        return doc.get("title", "Untitled")

    def clear_document_content(self, doc_id: str) -> None:
        """Clear all content from document body.

        Args:
            doc_id: Google Docs document ID.
        """
        doc = self.get_document(doc_id)
        body_content = doc.get("body", {}).get("content", [])

        if len(body_content) <= 1:
            # Document is empty or only has structural element
            return

        # Find the end index (last content element)
        end_index = body_content[-1].get("endIndex", 1)

        # Cannot delete the final newline (index 1 is minimum)
        if end_index <= 2:
            return

        try:
            self.docs_service.documents().batchUpdate(
                documentId=doc_id,
                body={
                    "requests": [
                        {
                            "deleteContentRange": {
                                "range": {
                                    "startIndex": 1,
                                    "endIndex": end_index - 1,
                                }
                            }
                        }
                    ]
                },
            ).execute()
        except HttpError as e:
            # Ignore errors when document is already empty
            if "Invalid requests" not in str(e):
                raise

    def batch_update(self, doc_id: str, requests: list[dict[str, Any]]) -> dict[str, Any]:
        """Apply batch updates to document.

        Args:
            doc_id: Google Docs document ID.
            requests: List of request objects for batchUpdate.

        Returns:
            Response from the API.
        """
        if not requests:
            return {}

        try:
            return (
                self.docs_service.documents()
                .batchUpdate(documentId=doc_id, body={"requests": requests})
                .execute()
            )
        except HttpError as e:
            raise Exception(f"Failed to update document: {e}") from e

    # Comment operations (via Drive API)

    def list_comments(self, file_id: str, include_resolved: bool = False) -> list[Comment]:
        """Get all comments on document.

        Args:
            file_id: Google Drive file ID (same as doc ID).
            include_resolved: Whether to include resolved comments.

        Returns:
            List of Comment objects.
        """
        response = (
            self.drive_service.comments()
            .list(
                fileId=file_id,
                includeDeleted=False,
                fields="comments(id,content,quotedFileContent,author,createdTime,resolved,"
                "replies(id,content,author,createdTime))",
            )
            .execute()
        )

        comments = []
        for c in response.get("comments", []):
            # Skip resolved comments unless requested
            if c.get("resolved", False) and not include_resolved:
                continue

            # Note: Google Drive API does not populate emailAddress for privacy
            # reasons. We use displayName instead, falling back to emailAddress
            # if somehow available.
            author_info = c.get("author", {})
            author_name = (
                author_info.get("emailAddress")
                or author_info.get("displayName")
                or "unknown"
            )

            comment = Comment(
                id=c["id"],
                content=c.get("content", ""),
                author=author_name,
                created_time=self._parse_timestamp(c.get("createdTime", "")),
                resolved=c.get("resolved", False),
                anchor=c.get("quotedFileContent", {}).get("value", ""),
                replies=[
                    CommentReply(
                        id=r["id"],
                        content=r.get("content", ""),
                        author=(
                            r.get("author", {}).get("emailAddress")
                            or r.get("author", {}).get("displayName")
                            or "unknown"
                        ),
                        created_time=self._parse_timestamp(r.get("createdTime", "")),
                    )
                    for r in c.get("replies", [])
                ],
            )
            comments.append(comment)

        return comments

    def create_comment(self, file_id: str, content: str) -> str:
        """Create an unanchored comment on the document.

        Args:
            file_id: Google Drive file ID.
            content: Comment text.

        Returns:
            ID of created comment.
        """
        result = (
            self.drive_service.comments()
            .create(
                fileId=file_id,
                body={"content": content},
                fields="id",
            )
            .execute()
        )
        return result["id"]

    def create_reply(self, file_id: str, comment_id: str, content: str) -> str:
        """Reply to a comment.

        Args:
            file_id: Google Drive file ID.
            comment_id: ID of comment to reply to.
            content: Reply text.

        Returns:
            ID of created reply.
        """
        result = (
            self.drive_service.replies()
            .create(
                fileId=file_id,
                commentId=comment_id,
                body={"content": content},
                fields="id",
            )
            .execute()
        )
        return result["id"]

    def resolve_comment(self, file_id: str, comment_id: str) -> None:
        """Mark comment as resolved.

        Args:
            file_id: Google Drive file ID.
            comment_id: ID of comment to resolve.
        """
        self.drive_service.comments().update(
            fileId=file_id,
            commentId=comment_id,
            body={"resolved": True},
        ).execute()

    def delete_comment(self, file_id: str, comment_id: str) -> None:
        """Delete a comment.

        Args:
            file_id: Google Drive file ID.
            comment_id: ID of comment to delete.
        """
        self.drive_service.comments().delete(
            fileId=file_id,
            commentId=comment_id,
        ).execute()

    # Folder operations

    def get_or_create_folder(self, name: str, parent_id: str) -> str:
        """Get or create a folder in Google Drive.

        Args:
            name: Folder name.
            parent_id: Parent folder ID.

        Returns:
            Folder ID.

        Raises:
            Exception: If folder creation or lookup fails.
        """
        try:
            # Escape backslashes and single quotes in name to prevent query injection
            escaped_name = name.replace("\\", "\\\\").replace("'", "\\'")
            # Check if folder exists
            query = (
                f"name='{escaped_name}' and "
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
        except HttpError as e:
            raise Exception(f"Failed to get or create folder '{name}': {e}") from e

    def get_parent_folder(self, file_id: str) -> str:
        """Get the parent folder ID of a file.

        Args:
            file_id: Google Drive file ID.

        Returns:
            Parent folder ID, or "root" if no parent.

        Raises:
            Exception: If API call fails.
        """
        try:
            response = (
                self.drive_service.files()
                .get(fileId=file_id, fields="parents")
                .execute()
            )
            parents = response.get("parents", [])
            return parents[0] if parents else "root"
        except HttpError as e:
            raise Exception(f"Failed to get parent folder for file '{file_id}': {e}") from e

    def upload_image(self, local_path: Path, folder_id: str) -> str:
        """Upload or update an image file in Drive.

        Args:
            local_path: Path to local image file.
            folder_id: ID of folder to upload to.

        Returns:
            File ID of uploaded/updated file.

        Raises:
            Exception: If upload fails.
        """
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

        try:
            # Escape filename for query (same as get_or_create_folder)
            escaped_filename = filename.replace("\\", "\\\\").replace("'", "\\'")

            # Check if file exists
            query = (
                f"name='{escaped_filename}' and "
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
        except HttpError as e:
            raise Exception(f"Failed to upload image '{filename}': {e}") from e

    # Suggestion operations

    def extract_suggestions(self, doc: dict[str, Any]) -> list[Suggestion]:
        """Extract suggestions from document structure.

        Suggestions appear as suggestedInsertionIds or suggestedDeletionIds
        on text runs and other elements.

        Args:
            doc: Document structure from get_document(suggestions_inline=True).

        Returns:
            List of Suggestion objects.
        """
        suggestions = []
        doc.get("suggestionsViewMode", {})

        # Walk the document content
        body = doc.get("body", {})
        for element in body.get("content", []):
            self._extract_suggestions_from_element(element, suggestions, doc)

        return suggestions

    def _extract_suggestions_from_element(
        self, element: dict[str, Any], suggestions: list[Suggestion], doc: dict[str, Any]
    ) -> None:
        """Recursively extract suggestions from document element."""
        # Check paragraph content
        if "paragraph" in element:
            for elem in element["paragraph"].get("elements", []):
                self._extract_suggestions_from_element(elem, suggestions, doc)

        # Check text runs for suggestions
        if "textRun" in element:
            text_run = element["textRun"]
            content = text_run.get("content", "")
            start_index = element.get("startIndex", 0)
            end_index = element.get("endIndex", 0)

            # Check for insertion suggestions
            for sugg_id in text_run.get("suggestedInsertionIds", []):
                suggestions.append(
                    Suggestion(
                        id=sugg_id,
                        type="insertion",
                        content=content,
                        author=self._get_suggestion_author(doc, sugg_id),
                        created_time=datetime.now(),  # API doesn't provide this
                        start_index=start_index,
                        end_index=end_index,
                    )
                )

            # Check for deletion suggestions
            for sugg_id in text_run.get("suggestedDeletionIds", []):
                suggestions.append(
                    Suggestion(
                        id=sugg_id,
                        type="deletion",
                        content=content,
                        author=self._get_suggestion_author(doc, sugg_id),
                        created_time=datetime.now(),
                        start_index=start_index,
                        end_index=end_index,
                    )
                )

        # Check table cells
        if "table" in element:
            for row in element["table"].get("tableRows", []):
                for cell in row.get("tableCells", []):
                    for cell_content in cell.get("content", []):
                        self._extract_suggestions_from_element(cell_content, suggestions, doc)

    def _get_suggestion_author(self, doc: dict[str, Any], suggestion_id: str) -> str:
        """Get the author of a suggestion from document metadata."""
        # The suggestionStates contain author info
        doc.get("suggestedDocumentStyleChanges", {})
        # This is simplified - full implementation would traverse suggestion metadata
        return "unknown"

    # Revision operations

    def get_latest_revision(self, file_id: str) -> str | None:
        """Get latest revision ID.

        Args:
            file_id: Google Drive file ID.

        Returns:
            Revision ID or None if no revisions.
        """
        try:
            revisions = (
                self.drive_service.revisions()
                .list(
                    fileId=file_id,
                    fields="revisions(id,modifiedTime)",
                    pageSize=1,
                )
                .execute()
            )

            revisions_list = revisions.get("revisions", [])
            if revisions_list:
                return revisions_list[-1]["id"]
            return None
        except HttpError:
            return None

    def get_file_metadata(self, file_id: str) -> dict[str, Any]:
        """Get file metadata from Drive.

        Args:
            file_id: Google Drive file ID.

        Returns:
            File metadata dict.
        """
        return (
            self.drive_service.files()
            .get(fileId=file_id, fields="id,name,modifiedTime,webViewLink")
            .execute()
        )

    # Helper methods

    def _parse_timestamp(self, timestamp_str: str) -> datetime:
        """Parse ISO timestamp string to datetime."""
        if not timestamp_str:
            return datetime.now()
        try:
            # Handle both formats: with and without milliseconds
            if "." in timestamp_str:
                return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        except ValueError:
            return datetime.now()
