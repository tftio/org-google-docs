"""Convert Google Docs comments and suggestions to org-mode annotations."""

from datetime import datetime

from ..models import (
    Comment,
    NodeType,
    OrgDocument,
    OrgHeading,
    OrgNode,
    OrgText,
    Suggestion,
)


class GDocsToOrgConverter:
    """Convert Google Docs feedback to org-mode annotation blocks."""

    def add_annotations(
        self,
        doc: OrgDocument,
        comments: list[Comment],
        suggestions: list[Suggestion],
    ) -> None:
        """Add comments and suggestions as annotation blocks to org document.

        Annotations are added to GDOCS_ANNOTATIONS sections within each
        top-level heading, or at the document level if no headings exist.

        Args:
            doc: Org document to modify.
            comments: List of comments from Google Docs.
            suggestions: List of suggestions from Google Docs.
        """
        # Group annotations by approximate location
        # For simplicity, we'll add all to a top-level GDOCS_ANNOTATIONS section
        annotation_nodes = []

        # Convert comments to annotation nodes
        for comment in comments:
            if not comment.resolved:  # Skip already resolved comments
                node = self._comment_to_annotation(comment)
                annotation_nodes.append(node)

        # Convert suggestions to annotation nodes
        for suggestion in suggestions:
            node = self._suggestion_to_annotation(suggestion)
            annotation_nodes.append(node)

        if not annotation_nodes:
            return

        # Find or create GDOCS_ANNOTATIONS section
        annotations_section = self._find_or_create_annotations_section(doc)

        # Add annotation nodes as children
        annotations_section.children.extend(annotation_nodes)

    def _comment_to_annotation(self, comment: Comment) -> OrgHeading:
        """Convert a comment to an org annotation heading."""
        # Format timestamp
        if isinstance(comment.created_time, datetime):
            timestamp = comment.created_time.strftime("[%Y-%m-%d %a %H:%M]")
        else:
            timestamp = str(comment.created_time)

        # Create heading for comment
        heading = OrgHeading(
            type=NodeType.HEADING,
            level=3,  # Will be adjusted based on parent
            title=f"Comment from {comment.author} {timestamp}",
            properties={
                "COMMENT_ID": comment.id,
                "ANCHOR": f'"{comment.anchor}"' if comment.anchor else '""',
                "RESOLVED": "nil",
            },
        )

        # Add comment content as child text
        content_node = OrgText(type=NodeType.TEXT, content=comment.content)
        heading.children.append(content_node)

        # Add replies as sub-headings
        for reply in comment.replies:
            if isinstance(reply.created_time, datetime):
                reply_ts = reply.created_time.strftime("[%Y-%m-%d %a %H:%M]")
            else:
                reply_ts = str(reply.created_time)

            reply_heading = OrgHeading(
                type=NodeType.HEADING,
                level=4,
                title=f"Reply from {reply.author} {reply_ts}",
            )
            reply_content = OrgText(type=NodeType.TEXT, content=reply.content)
            reply_heading.children.append(reply_content)
            heading.children.append(reply_heading)

        return heading

    def _suggestion_to_annotation(self, suggestion: Suggestion) -> OrgHeading:
        """Convert a suggestion to an org annotation heading."""
        # Format timestamp
        if isinstance(suggestion.created_time, datetime):
            timestamp = suggestion.created_time.strftime("[%Y-%m-%d %a %H:%M]")
        else:
            timestamp = str(suggestion.created_time)

        # Create heading for suggestion
        heading = OrgHeading(
            type=NodeType.HEADING,
            level=3,
            title=f"Suggestion from {suggestion.author} {timestamp}",
            properties={
                "SUGG_ID": suggestion.id,
                "TYPE": suggestion.type,
                "STATUS": "pending",
                "LOCATION": f'"{suggestion.location_hint}"' if suggestion.location_hint else '""',
            },
        )

        # Add suggestion content as child text
        content_text = f"[{suggestion.type.upper()}] {suggestion.content}"
        content_node = OrgText(type=NodeType.TEXT, content=content_text)
        heading.children.append(content_node)

        return heading

    def _find_or_create_annotations_section(self, doc: OrgDocument) -> OrgHeading:
        """Find existing GDOCS_ANNOTATIONS section or create one."""
        # Look for existing section at top level
        for node in doc.content:
            if node.type == NodeType.HEADING:
                heading = node if isinstance(node, OrgHeading) else None
                if heading and heading.title == "GDOCS_ANNOTATIONS":
                    return heading

        # Create new section
        section = OrgHeading(
            type=NodeType.HEADING,
            level=1,
            title="GDOCS_ANNOTATIONS",
        )
        doc.content.append(section)
        return section

    def mark_comment_resolved(self, doc: OrgDocument, comment_id: str) -> bool:
        """Mark a comment annotation as resolved.

        Args:
            doc: Org document to modify.
            comment_id: ID of the comment to mark resolved.

        Returns:
            True if comment was found and marked, False otherwise.
        """
        annotation = self._find_annotation_by_id(doc, comment_id, "COMMENT_ID")
        if annotation:
            annotation.properties["RESOLVED"] = "t"
            annotation.properties["RESOLVED_DATE"] = datetime.now().strftime(
                "[%Y-%m-%d %a %H:%M]"
            )
            return True
        return False

    def mark_suggestion_integrated(self, doc: OrgDocument, suggestion_id: str) -> bool:
        """Mark a suggestion annotation as integrated.

        Args:
            doc: Org document to modify.
            suggestion_id: ID of the suggestion to mark integrated.

        Returns:
            True if suggestion was found and marked, False otherwise.
        """
        annotation = self._find_annotation_by_id(doc, suggestion_id, "SUGG_ID")
        if annotation:
            annotation.properties["STATUS"] = "integrated"
            annotation.properties["INTEGRATED_DATE"] = datetime.now().strftime(
                "[%Y-%m-%d %a %H:%M]"
            )
            return True
        return False

    def move_to_archive(self, doc: OrgDocument, annotation: OrgHeading) -> None:
        """Move an annotation to the GDOCS_ARCHIVE section.

        Args:
            doc: Org document to modify.
            annotation: Annotation heading to archive.
        """
        # Find or create archive section
        archive = self._find_or_create_archive_section(doc)

        # Remove from current location
        self._remove_annotation(doc, annotation)

        # Add to archive
        archive.children.append(annotation)

    def _find_or_create_archive_section(self, doc: OrgDocument) -> OrgHeading:
        """Find existing GDOCS_ARCHIVE section or create one."""
        for node in doc.content:
            if node.type == NodeType.HEADING:
                heading = node if isinstance(node, OrgHeading) else None
                if heading and heading.title == "GDOCS_ARCHIVE":
                    return heading

        # Create new section
        section = OrgHeading(
            type=NodeType.HEADING,
            level=1,
            title="GDOCS_ARCHIVE",
        )
        doc.content.append(section)
        return section

    def _find_annotation_by_id(
        self, doc: OrgDocument, target_id: str, id_property: str
    ) -> OrgHeading | None:
        """Find an annotation heading by its ID property."""

        def search_nodes(nodes: list[OrgNode]) -> OrgHeading | None:
            for node in nodes:
                if node.type == NodeType.HEADING:
                    heading = node if isinstance(node, OrgHeading) else None
                    if heading:
                        if heading.properties.get(id_property) == target_id:
                            return heading
                        # Search children
                        result = search_nodes(heading.children)
                        if result:
                            return result
            return None

        return search_nodes(doc.content)

    def _remove_annotation(self, doc: OrgDocument, target: OrgHeading) -> bool:
        """Remove an annotation from its current location in the document."""

        def remove_from_nodes(nodes: list[OrgNode]) -> bool:
            for i, node in enumerate(nodes):
                if node is target:
                    nodes.pop(i)
                    return True
                if node.type == NodeType.HEADING:
                    heading = node if isinstance(node, OrgHeading) else None
                    if heading and remove_from_nodes(heading.children):
                        return True
            return False

        return remove_from_nodes(doc.content)

    def get_pending_comments(self, doc: OrgDocument) -> list[OrgHeading]:
        """Get all unresolved comment annotations.

        Args:
            doc: Org document to search.

        Returns:
            List of comment annotation headings.
        """
        comments = []

        def search_nodes(nodes: list[OrgNode]) -> None:
            for node in nodes:
                if node.type == NodeType.HEADING:
                    heading = node if isinstance(node, OrgHeading) else None
                    if heading:
                        if (
                            "COMMENT_ID" in heading.properties
                            and heading.properties.get("RESOLVED") != "t"
                        ):
                            comments.append(heading)
                        search_nodes(heading.children)

        search_nodes(doc.content)
        return comments

    def get_pending_suggestions(self, doc: OrgDocument) -> list[OrgHeading]:
        """Get all pending suggestion annotations.

        Args:
            doc: Org document to search.

        Returns:
            List of suggestion annotation headings.
        """
        suggestions = []

        def search_nodes(nodes: list[OrgNode]) -> None:
            for node in nodes:
                if node.type == NodeType.HEADING:
                    heading = node if isinstance(node, OrgHeading) else None
                    if heading:
                        if (
                            "SUGG_ID" in heading.properties
                            and heading.properties.get("STATUS") == "pending"
                        ):
                            suggestions.append(heading)
                        search_nodes(heading.children)

        search_nodes(doc.content)
        return suggestions
