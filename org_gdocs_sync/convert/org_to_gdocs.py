"""Convert org-mode AST to Google Docs API requests."""

import re
from typing import Any

from ..models import (
    NodeType,
    OrgDocument,
    OrgHeading,
    OrgLink,
    OrgList,
    OrgListItem,
    OrgNode,
    OrgParagraph,
    OrgSrcBlock,
    OrgTable,
    OrgText,
)


# Sections to exclude from push
EXCLUDED_SECTIONS = {"GDOCS_ANNOTATIONS", "GDOCS_ARCHIVE"}

# Inline formatting patterns - order matters (most specific first)
# Each tuple: (pattern, style_key, style_value)
INLINE_FORMATS = [
    # Links: [[url][description]] or [[url]]
    (re.compile(r"\[\[([^\]]+)\]\[([^\]]+)\]\]"), "link", None),  # with description
    (re.compile(r"\[\[([^\]]+)\]\]"), "link_bare", None),  # bare link
    # Bold: *text*
    (re.compile(r"(?<![*\w])\*([^*\n]+)\*(?![*\w])"), "bold", True),
    # Italic: /text/
    (re.compile(r"(?<![/\w])/([^/\n]+)/(?![/\w])"), "italic", True),
    # Code: ~text~ or =text=
    (re.compile(r"~([^~\n]+)~"), "code", True),
    (re.compile(r"=([^=\n]+)="), "code", True),
    # Underline: _text_
    (re.compile(r"(?<![_\w])_([^_\n]+)_(?![_\w])"), "underline", True),
    # Strikethrough: +text+
    (re.compile(r"(?<![+\w])\+([^+\n]+)\+(?![+\w])"), "strikethrough", True),
]


class OrgToGDocsConverter:
    """Convert org-mode AST to Google Docs batchUpdate requests."""

    def __init__(self):
        """Initialize converter."""
        self.current_index = 1  # Google Docs uses 1-based indexing
        self.requests: list[dict[str, Any]] = []

    def convert(self, doc: OrgDocument) -> list[dict[str, Any]]:
        """Convert org document to list of batchUpdate requests.

        Args:
            doc: Parsed org-mode document.

        Returns:
            List of request objects for documents.batchUpdate().
        """
        self.current_index = 1
        self.requests = []

        # Filter out sync-related sections
        filtered_content = self._filter_sync_sections(doc.content)

        # Convert each node
        for node in filtered_content:
            self._convert_node(node)

        return self.requests

    def _filter_sync_sections(self, nodes: list[OrgNode]) -> list[OrgNode]:
        """Remove GDOCS_ANNOTATIONS and GDOCS_ARCHIVE sections."""
        filtered = []
        for node in nodes:
            if node.type == NodeType.HEADING:
                heading = node if isinstance(node, OrgHeading) else None
                if heading and heading.title in EXCLUDED_SECTIONS:
                    continue
                # Also filter children
                if heading:
                    heading.children = self._filter_sync_sections(heading.children)
            filtered.append(node)
        return filtered

    def _convert_node(self, node: OrgNode) -> None:
        """Convert a single node to requests."""
        if node.type == NodeType.HEADING:
            self._convert_heading(node)
        elif node.type == NodeType.PARAGRAPH:
            self._convert_paragraph(node)
        elif node.type == NodeType.TEXT:
            self._convert_text(node)
        elif node.type == NodeType.SRC_BLOCK:
            self._convert_src_block(node)
        elif node.type == NodeType.TABLE:
            self._convert_table(node)
        elif node.type == NodeType.LIST:
            self._convert_list(node)
        elif node.type == NodeType.LINK:
            self._convert_link(node)
        elif node.type == NodeType.GDOCS_COMMENT_DIRECTIVE:
            # Skip - these are handled separately for posting comments
            pass
        # Other node types are skipped

    def _convert_heading(self, node: OrgNode) -> None:
        """Convert heading to Google Docs requests."""
        heading = node if isinstance(node, OrgHeading) else None
        if not heading:
            return

        # Build heading text
        text_parts = []
        if heading.todo_state:
            text_parts.append(heading.todo_state)
        text_parts.append(heading.title)
        text = " ".join(text_parts)

        # Add tags at end if present
        if heading.tags:
            text += " :" + ":".join(heading.tags) + ":"

        text += "\n"

        # Insert text
        start_index = self.current_index
        self._insert_text(text)

        # Apply heading style
        heading_style = f"HEADING_{min(heading.level, 6)}"
        self.requests.append(
            {
                "updateParagraphStyle": {
                    "range": {
                        "startIndex": start_index,
                        "endIndex": self.current_index,
                    },
                    "paragraphStyle": {"namedStyleType": heading_style},
                    "fields": "namedStyleType",
                }
            }
        )

        # Convert children
        for child in heading.children:
            self._convert_node(child)

    def _convert_paragraph(self, node: OrgNode) -> None:
        """Convert paragraph to Google Docs requests."""
        para = node if isinstance(node, OrgParagraph) else None
        if not para:
            return

        # Convert inline children
        for child in para.children:
            self._convert_inline_node(child)

        # Add newline after paragraph
        self._insert_text("\n")

    def _convert_inline_node(self, node: OrgNode) -> None:
        """Convert inline node (text, link) preserving position for formatting."""
        if node.type == NodeType.TEXT:
            text = node if isinstance(node, OrgText) else None
            if text and text.content:
                self._insert_formatted_text(text.content)
        elif node.type == NodeType.LINK:
            link = node if isinstance(node, OrgLink) else None
            if link:
                display_text = link.description or link.url
                start_index = self.current_index
                self._insert_text(display_text)

                # Apply link formatting
                self.requests.append(
                    {
                        "updateTextStyle": {
                            "range": {
                                "startIndex": start_index,
                                "endIndex": self.current_index,
                            },
                            "textStyle": {"link": {"url": link.url}},
                            "fields": "link",
                        }
                    }
                )

    def _insert_formatted_text(self, text: str) -> None:
        """Insert text with inline formatting (bold, italic, etc.)."""
        # Find all formatting spans
        spans = self._find_format_spans(text)

        if not spans:
            # No formatting, just insert plain text
            self._insert_text(text)
            return

        # Sort spans by start position
        spans.sort(key=lambda x: x[0])

        # Build plain text (with markers removed) and track style ranges
        plain_text = ""
        style_ranges = []  # (start, end, style_type, style_data)
        last_end = 0

        for start, end, style_type, content, style_data in spans:
            # Add text before this span
            plain_text += text[last_end:start]

            # Track where this styled content will be in the plain text
            style_start = len(plain_text)
            plain_text += content
            style_end = len(plain_text)

            style_ranges.append((style_start, style_end, style_type, style_data))
            last_end = end

        # Add remaining text after last span
        plain_text += text[last_end:]

        # Insert the plain text
        insert_start = self.current_index
        self._insert_text(plain_text)

        # Apply styles to the ranges
        for style_start, style_end, style_type, style_data in style_ranges:
            abs_start = insert_start + style_start
            abs_end = insert_start + style_end

            if style_type == "link":
                self.requests.append(
                    {
                        "updateTextStyle": {
                            "range": {"startIndex": abs_start, "endIndex": abs_end},
                            "textStyle": {"link": {"url": style_data}},
                            "fields": "link",
                        }
                    }
                )
            elif style_type == "bold":
                self.requests.append(
                    {
                        "updateTextStyle": {
                            "range": {"startIndex": abs_start, "endIndex": abs_end},
                            "textStyle": {"bold": True},
                            "fields": "bold",
                        }
                    }
                )
            elif style_type == "italic":
                self.requests.append(
                    {
                        "updateTextStyle": {
                            "range": {"startIndex": abs_start, "endIndex": abs_end},
                            "textStyle": {"italic": True},
                            "fields": "italic",
                        }
                    }
                )
            elif style_type == "code":
                self.requests.append(
                    {
                        "updateTextStyle": {
                            "range": {"startIndex": abs_start, "endIndex": abs_end},
                            "textStyle": {
                                "weightedFontFamily": {"fontFamily": "Courier New"},
                            },
                            "fields": "weightedFontFamily",
                        }
                    }
                )
            elif style_type == "underline":
                self.requests.append(
                    {
                        "updateTextStyle": {
                            "range": {"startIndex": abs_start, "endIndex": abs_end},
                            "textStyle": {"underline": True},
                            "fields": "underline",
                        }
                    }
                )
            elif style_type == "strikethrough":
                self.requests.append(
                    {
                        "updateTextStyle": {
                            "range": {"startIndex": abs_start, "endIndex": abs_end},
                            "textStyle": {"strikethrough": True},
                            "fields": "strikethrough",
                        }
                    }
                )

    def _find_format_spans(self, text: str) -> list[tuple[int, int, str, str, Any]]:
        """Find all formatting spans in text.

        Returns list of (start, end, style_type, content, style_data) tuples.
        """
        spans = []

        for pattern, style_type, _ in INLINE_FORMATS:
            for match in pattern.finditer(text):
                if style_type == "link":
                    # [[url][description]]
                    url = match.group(1)
                    description = match.group(2)
                    spans.append((match.start(), match.end(), "link", description, url))
                elif style_type == "link_bare":
                    # [[url]]
                    url = match.group(1)
                    spans.append((match.start(), match.end(), "link", url, url))
                else:
                    # Other formatting: group(1) is the content
                    content = match.group(1)
                    spans.append((match.start(), match.end(), style_type, content, None))

        # Remove overlapping spans (keep first match)
        spans.sort(key=lambda x: (x[0], -x[1]))  # Sort by start, then longest first
        non_overlapping = []
        last_end = -1
        for span in spans:
            if span[0] >= last_end:
                non_overlapping.append(span)
                last_end = span[1]

        return non_overlapping

    def _convert_text(self, node: OrgNode) -> None:
        """Convert standalone text node."""
        text = node if isinstance(node, OrgText) else None
        if text and text.content.strip():
            self._insert_text(text.content + "\n")

    def _convert_src_block(self, node: OrgNode) -> None:
        """Convert source block to monospace text."""
        src = node if isinstance(node, OrgSrcBlock) else None
        if not src:
            return

        # Build content with optional language comment
        text = ""
        if src.language:
            text += f"# Language: {src.language}\n"
        text += src.content + "\n\n"

        start_index = self.current_index
        self._insert_text(text)

        # Apply monospace style to the code (not the trailing newlines)
        code_end = self.current_index - 1
        if code_end > start_index:
            self.requests.append(
                {
                    "updateTextStyle": {
                        "range": {
                            "startIndex": start_index,
                            "endIndex": code_end,
                        },
                        "textStyle": {
                            "weightedFontFamily": {"fontFamily": "Courier New"},
                            "fontSize": {"magnitude": 10, "unit": "PT"},
                        },
                        "fields": "weightedFontFamily,fontSize",
                    }
                }
            )

    def _convert_table(self, node: OrgNode) -> None:
        """Convert org table to text representation.

        Note: Google Docs table insertion is complex and requires careful
        index tracking. For now, we render tables as formatted text.
        """
        table = node if isinstance(node, OrgTable) else None
        if not table or not table.rows:
            return

        # Calculate column widths
        col_widths: list[int] = []
        for row in table.rows:
            for i, cell in enumerate(row):
                if i >= len(col_widths):
                    col_widths.append(len(cell))
                else:
                    col_widths[i] = max(col_widths[i], len(cell))

        # Build text representation
        lines = []
        for i, row in enumerate(table.rows):
            cells = [cell.ljust(col_widths[j]) if j < len(col_widths) else cell
                     for j, cell in enumerate(row)]
            lines.append("| " + " | ".join(cells) + " |")
            # Add separator after first row (header)
            if i == 0 and table.has_header:
                sep_cells = ["-" * w for w in col_widths]
                lines.append("|-" + "-+-".join(sep_cells) + "-|")

        text = "\n".join(lines) + "\n\n"

        # Insert as monospace text
        start_index = self.current_index
        self._insert_text(text)

        # Apply monospace formatting
        if self.current_index > start_index:
            self.requests.append(
                {
                    "updateTextStyle": {
                        "range": {
                            "startIndex": start_index,
                            "endIndex": self.current_index - 1,
                        },
                        "textStyle": {
                            "weightedFontFamily": {"fontFamily": "Courier New"},
                            "fontSize": {"magnitude": 10, "unit": "PT"},
                        },
                        "fields": "weightedFontFamily,fontSize",
                    }
                }
            )

    def _convert_list(self, node: OrgNode) -> None:
        """Convert list to Google Docs bullet/numbered list."""
        org_list = node if isinstance(node, OrgList) else None
        if not org_list:
            return

        # Track start index for applying bullet style
        list_start = self.current_index

        # Insert all list items as text first
        for child in org_list.children:
            if isinstance(child, OrgListItem):
                item_text = child.content
                if child.checkbox:
                    item_text = f"[{child.checkbox}] {item_text}"
                self._insert_text(item_text + "\n")

        # Apply bullet style to the range
        if self.current_index > list_start:
            bullet_preset = (
                "BULLET_DISC_CIRCLE_SQUARE"
                if org_list.list_type == "unordered"
                else "NUMBERED_DECIMAL_ALPHA_ROMAN"
            )

            self.requests.append(
                {
                    "createParagraphBullets": {
                        "range": {
                            "startIndex": list_start,
                            "endIndex": self.current_index,
                        },
                        "bulletPreset": bullet_preset,
                    }
                }
            )

        # Add blank line after list
        self._insert_text("\n")

    def _convert_link(self, node: OrgNode) -> None:
        """Convert standalone link."""
        link = node if isinstance(node, OrgLink) else None
        if not link:
            return

        display_text = link.description or link.url
        start_index = self.current_index
        self._insert_text(display_text + "\n")

        # Apply link formatting
        self.requests.append(
            {
                "updateTextStyle": {
                    "range": {
                        "startIndex": start_index,
                        "endIndex": self.current_index - 1,  # Exclude newline
                    },
                    "textStyle": {"link": {"url": link.url}},
                    "fields": "link",
                }
            }
        )

    def _insert_text(self, text: str) -> None:
        """Insert text at current position and update index."""
        if not text:
            return

        self.requests.append(
            {
                "insertText": {
                    "location": {"index": self.current_index},
                    "text": text,
                }
            }
        )
        self.current_index += len(text)
