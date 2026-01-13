"""Push workflow: org-mode -> Google Docs."""

from copy import deepcopy
from datetime import datetime
from pathlib import Path

from ..babel import (
    execute_babel,
    extract_file_output,
    find_babel_blocks,
    verify_babel_outputs,
)
from ..convert.org_to_gdocs import OrgToGDocsConverter
from ..gdocs.client import GoogleDocsClient
from ..models import NodeType, OrgDocument, OrgRenderedImage, OrgSrcBlock
from ..org.parser import OrgParser
from ..org.writer import OrgWriter


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
    # Find blocks with :file output
    babel_blocks = find_babel_blocks(doc)
    if not babel_blocks:
        return doc

    # Must have a file path to execute babel
    if not doc.path:
        raise ValueError("Cannot process babel blocks: document has no file path")

    org_dir = Path(doc.path).parent

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

    # Build replacements keyed by (start_line, end_line) tuple
    # This survives deepcopy unlike object id
    replacements: dict[tuple[int, int], OrgRenderedImage] = {}
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
        replacements[(block.start_line, block.end_line)] = rendered

    # Replace blocks in document tree
    def replace_blocks(nodes: list) -> list:
        result = []
        for node in nodes:
            key = (getattr(node, "start_line", None), getattr(node, "end_line", None))
            if key in replacements:
                result.append(replacements[key])
            else:
                if hasattr(node, "children"):
                    node.children = replace_blocks(node.children)
                result.append(node)
        return result

    # Deepcopy first to avoid mutating the original document
    new_doc = deepcopy(doc)
    new_doc.content = replace_blocks(new_doc.content)
    return new_doc


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

    # Process babel blocks (execute, upload images, replace with rendered nodes)
    doc = process_babel_blocks(doc, gdoc_id, client)

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
