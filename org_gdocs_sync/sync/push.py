"""Push workflow: org-mode -> Google Docs."""

from datetime import datetime

from ..convert.org_to_gdocs import OrgToGDocsConverter
from ..gdocs.client import GoogleDocsClient
from ..models import NodeType
from ..org.parser import OrgParser
from ..org.writer import OrgWriter


def push(org_path: str, force: bool = False) -> dict:
    """Push org-mode document to Google Docs.

    Steps:
    1. Parse org document
    2. Convert to Google Docs requests
    3. Clear and replace document content
    4. Post any inline #+GDOCS_COMMENT: directives
    5. Update metadata

    Args:
        org_path: Path to org-mode file.
        force: If True, push even if there are potential conflicts.

    Returns:
        Dictionary with push results.

    Raises:
        ValueError: If document is not initialized.
    """
    parser = OrgParser()
    converter = OrgToGDocsConverter()
    client = GoogleDocsClient()
    writer = OrgWriter()

    # Parse org file
    doc = parser.parse_file(org_path)

    # Validate
    gdoc_id = doc.get_gdoc_id()
    if not gdoc_id:
        raise ValueError("No GDOC_ID found in document. Run 'sync init' first.")

    # Convert org content to Google Docs requests
    requests = converter.convert(doc)

    # Clear existing document content
    client.clear_document_content(gdoc_id)

    # Apply new content
    if requests:
        client.batch_update(gdoc_id, requests)

    # Extract and post inline GDOCS_COMMENT directives
    comments_posted = 0
    comment_nodes = _extract_gdocs_comments(doc)
    for comment_content in comment_nodes:
        client.create_comment(gdoc_id, comment_content)
        comments_posted += 1

    # Remove posted comments from org file
    _remove_gdocs_comment_directives(doc)

    # Update metadata
    rev_id = client.get_latest_revision(gdoc_id)
    doc.metadata["LAST_PUSH_REV"] = rev_id or ""
    doc.metadata["LAST_SYNC"] = datetime.now().isoformat()

    # Save updated org file
    writer.write_file(org_path, doc)

    return {
        "gdoc_id": gdoc_id,
        "url": f"https://docs.google.com/document/d/{gdoc_id}/edit",
        "requests_sent": len(requests),
        "comments_posted": comments_posted,
        "revision": rev_id,
    }


def _extract_gdocs_comments(doc) -> list[str]:
    """Extract GDOCS_COMMENT directive contents from document."""
    comments = []

    def walk_nodes(nodes):
        for node in nodes:
            if node.type == NodeType.GDOCS_COMMENT_DIRECTIVE:
                content = node.properties.get("content", "")
                if content:
                    comments.append(content)
            if hasattr(node, "children"):
                walk_nodes(node.children)

    walk_nodes(doc.content)
    return comments


def _remove_gdocs_comment_directives(doc) -> None:
    """Remove GDOCS_COMMENT directives from document after posting."""

    def filter_nodes(nodes):
        filtered = []
        for node in nodes:
            if node.type != NodeType.GDOCS_COMMENT_DIRECTIVE:
                if hasattr(node, "children"):
                    node.children = filter_nodes(node.children)
                filtered.append(node)
        return filtered

    doc.content = filter_nodes(doc.content)
