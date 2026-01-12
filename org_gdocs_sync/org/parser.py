"""Parse org-mode files into AST."""

import re
from pathlib import Path

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

# Regex patterns for org-mode syntax
HEADING_RE = re.compile(r"^(\*+)\s+(?:(TODO|DONE|WAITING|CANCELLED)\s+)?(?:\[#([A-Z])\]\s+)?(.*)$")
METADATA_RE = re.compile(r"^#\+(\w+):\s*(.*)$")
LINK_RE = re.compile(r"\[\[([^\]]+)\](?:\[([^\]]+)\])?\]")
SRC_BEGIN_RE = re.compile(r"^#\+BEGIN_SRC\s*(\w*)\s*$", re.IGNORECASE)
SRC_END_RE = re.compile(r"^#\+END_SRC\s*$", re.IGNORECASE)
TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")
TABLE_SEP_RE = re.compile(r"^\s*\|[-+]+\|\s*$")
LIST_ITEM_RE = re.compile(r"^(\s*)([-+*]|\d+[.)])\s+(?:\[([ X-])\]\s+)?(.*)$")
PROPERTY_DRAWER_START_RE = re.compile(r"^\s*:PROPERTIES:\s*$")
PROPERTY_DRAWER_END_RE = re.compile(r"^\s*:END:\s*$")
PROPERTY_RE = re.compile(r"^\s*:(\w+):\s*(.*)$")
GDOCS_COMMENT_RE = re.compile(r"^#\+GDOCS_COMMENT:\s*(.*)$")

# Inline formatting patterns
BOLD_RE = re.compile(r"\*([^*]+)\*")
ITALIC_RE = re.compile(r"/([^/]+)/")
CODE_RE = re.compile(r"[~=]([^~=]+)[~=]")
UNDERLINE_RE = re.compile(r"_([^_]+)_")
STRIKETHROUGH_RE = re.compile(r"\+([^+]+)\+")


class OrgParser:
    """Parse org-mode documents."""

    def parse_file(self, path: str | Path) -> OrgDocument:
        """Parse org-mode file into document structure.

        Args:
            path: Path to org-mode file.

        Returns:
            Parsed OrgDocument.
        """
        path = Path(path)
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()

        doc = OrgDocument(path=str(path))

        # Parse metadata (#+KEY: value lines at top)
        # Exclude directives that should be parsed as content (GDOCS_COMMENT, BEGIN_SRC, etc.)
        line_idx = 0
        while line_idx < len(lines):
            line = lines[line_idx].rstrip("\n\r")
            match = METADATA_RE.match(line)
            if match:
                key = match.group(1).upper()
                # These are directives, not metadata - stop here
                if key in ("GDOCS_COMMENT", "BEGIN_SRC", "END_SRC"):
                    break
                value = match.group(2)
                doc.metadata[match.group(1)] = value
                line_idx += 1
            elif line.strip() == "":
                line_idx += 1
            else:
                break

        # Parse content
        doc.content = self._parse_content(lines[line_idx:], start_line=line_idx)

        return doc

    def parse_string(self, content: str) -> OrgDocument:
        """Parse org-mode content from string.

        Args:
            content: Org-mode formatted string.

        Returns:
            Parsed OrgDocument.
        """
        lines = content.split("\n")
        # Add newlines back for consistent processing
        lines = [line + "\n" if not line.endswith("\n") else line for line in lines]

        doc = OrgDocument()

        # Parse metadata (#+KEY: value lines at top)
        # Exclude directives that should be parsed as content
        line_idx = 0
        while line_idx < len(lines):
            line = lines[line_idx].rstrip("\n\r")
            match = METADATA_RE.match(line)
            if match:
                key = match.group(1).upper()
                # These are directives, not metadata - stop here
                if key in ("GDOCS_COMMENT", "BEGIN_SRC", "END_SRC"):
                    break
                value = match.group(2)
                doc.metadata[match.group(1)] = value
                line_idx += 1
            elif line.strip() == "":
                line_idx += 1
            else:
                break

        # Parse content
        doc.content = self._parse_content(lines[line_idx:], start_line=line_idx)

        return doc

    def _parse_content(self, lines: list[str], start_line: int = 0) -> list[OrgNode]:
        """Parse document content into nodes."""
        nodes = []
        i = 0

        while i < len(lines):
            line = lines[i].rstrip("\n\r")

            # Heading
            heading_match = HEADING_RE.match(line)
            if heading_match:
                level = len(heading_match.group(1))
                todo_state = heading_match.group(2)
                priority = heading_match.group(3)
                title = heading_match.group(4).strip()

                # Extract tags from title if present
                tags = []
                if title.endswith(":"):
                    tag_match = re.search(r"\s+:([:\w]+):$", title)
                    if tag_match:
                        tags = [t for t in tag_match.group(1).split(":") if t]
                        title = title[: tag_match.start()].strip()

                # Find heading children (until next heading of same/higher level)
                child_lines = []
                j = i + 1
                while j < len(lines):
                    next_line = lines[j]
                    next_match = HEADING_RE.match(next_line.rstrip("\n\r"))
                    if next_match and len(next_match.group(1)) <= level:
                        break
                    child_lines.append(next_line)
                    j += 1

                heading = OrgHeading(
                    type=NodeType.HEADING,
                    level=level,
                    title=title,
                    todo_state=todo_state,
                    priority=priority,
                    tags=tags,
                    children=self._parse_content(child_lines, start_line=start_line + i + 1),
                    start_line=start_line + i,
                    end_line=start_line + j - 1,
                )
                nodes.append(heading)
                i = j
                continue

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
                nodes.append(src_block)
                i += 1
                continue

            # Table
            if TABLE_ROW_RE.match(line) or TABLE_SEP_RE.match(line):
                table_lines = [line]
                table_start = i
                i += 1
                while i < len(lines):
                    table_line = lines[i].rstrip("\n\r")
                    if not (TABLE_ROW_RE.match(table_line) or TABLE_SEP_RE.match(table_line)):
                        break
                    table_lines.append(table_line)
                    i += 1

                table = self._parse_table(table_lines)
                table.start_line = start_line + table_start
                table.end_line = start_line + i - 1
                nodes.append(table)
                continue

            # List item
            list_match = LIST_ITEM_RE.match(line)
            if list_match:
                list_lines = [line]
                list_start = i
                indent = len(list_match.group(1))
                i += 1
                while i < len(lines):
                    next_line = lines[i].rstrip("\n\r")
                    next_match = LIST_ITEM_RE.match(next_line)
                    if next_match:
                        # Same or deeper indentation continues the list
                        if len(next_match.group(1)) >= indent:
                            list_lines.append(next_line)
                            i += 1
                            continue
                        break
                    # Continuation lines
                    if next_line.startswith(" " * (indent + 2)):
                        list_lines.append(next_line)
                        i += 1
                        continue
                    if next_line.strip() == "":
                        i += 1
                        continue
                    break

                org_list = self._parse_list(list_lines)
                org_list.start_line = start_line + list_start
                org_list.end_line = start_line + i - 1
                nodes.append(org_list)
                continue

            # GDOCS_COMMENT directive
            comment_match = GDOCS_COMMENT_RE.match(line)
            if comment_match:
                comment_text = comment_match.group(1)
                comment_node = OrgNode(
                    type=NodeType.GDOCS_COMMENT_DIRECTIVE,
                    properties={"content": comment_text},
                    start_line=start_line + i,
                    end_line=start_line + i,
                )
                nodes.append(comment_node)
                i += 1
                continue

            # Regular paragraph/text
            if line.strip():
                para_lines = [line]
                para_start = i
                i += 1
                while i < len(lines):
                    next_line = lines[i].rstrip("\n\r")
                    # End paragraph on empty line, heading, src block, table, list
                    if (
                        not next_line.strip()
                        or HEADING_RE.match(next_line)
                        or SRC_BEGIN_RE.match(next_line)
                        or TABLE_ROW_RE.match(next_line)
                        or LIST_ITEM_RE.match(next_line)
                        or METADATA_RE.match(next_line)
                    ):
                        break
                    para_lines.append(next_line)
                    i += 1

                paragraph = self._parse_paragraph(para_lines)
                paragraph.start_line = start_line + para_start
                paragraph.end_line = start_line + i - 1
                nodes.append(paragraph)
                continue

            i += 1

        return nodes

    def _parse_paragraph(self, lines: list[str]) -> OrgParagraph:
        """Parse paragraph with inline formatting."""
        content = " ".join(lines)
        paragraph = OrgParagraph(type=NodeType.PARAGRAPH)

        # Parse inline elements (links, formatting)
        children = self._parse_inline(content)
        paragraph.children = children

        return paragraph

    def _parse_inline(self, text: str) -> list[OrgNode]:
        """Parse inline elements (links, formatting) from text."""
        nodes = []
        pos = 0

        # Find all links
        for match in LINK_RE.finditer(text):
            # Add text before link
            if match.start() > pos:
                before_text = text[pos : match.start()]
                nodes.append(OrgText(type=NodeType.TEXT, content=before_text))

            # Add link
            url = match.group(1)
            description = match.group(2)
            nodes.append(OrgLink(type=NodeType.LINK, url=url, description=description))

            pos = match.end()

        # Add remaining text
        if pos < len(text):
            nodes.append(OrgText(type=NodeType.TEXT, content=text[pos:]))

        # If no links found, just return single text node
        if not nodes:
            nodes.append(OrgText(type=NodeType.TEXT, content=text))

        return nodes

    def _parse_table(self, lines: list[str]) -> OrgTable:
        """Parse org-mode table."""
        rows = []
        has_header = False

        for line in lines:
            # Skip separator lines but note if we've seen one
            if TABLE_SEP_RE.match(line):
                if rows and not has_header:
                    has_header = True
                continue

            # Parse cells
            match = TABLE_ROW_RE.match(line)
            if match:
                cells = [cell.strip() for cell in match.group(1).split("|")]
                rows.append(cells)

        return OrgTable(type=NodeType.TABLE, rows=rows, has_header=has_header)

    def _parse_list(self, lines: list[str]) -> OrgList:
        """Parse org-mode list."""
        items = []
        first_match = LIST_ITEM_RE.match(lines[0])

        # Determine list type
        bullet = first_match.group(2) if first_match else "-"
        if bullet[0].isdigit():
            list_type = "ordered"
        else:
            list_type = "unordered"

        current_item = None
        current_content = []

        for line in lines:
            match = LIST_ITEM_RE.match(line)
            if match:
                # Save previous item
                if current_item:
                    current_item.content = " ".join(current_content)
                    items.append(current_item)

                # Start new item
                bullet = match.group(2)
                checkbox = match.group(3)
                content = match.group(4)

                current_item = OrgListItem(
                    type=NodeType.LIST_ITEM,
                    bullet=bullet,
                    checkbox=checkbox,
                    content=content,
                )
                current_content = [content]
            elif current_item:
                # Continuation of current item
                current_content.append(line.strip())

        # Save last item
        if current_item:
            current_item.content = " ".join(current_content)
            items.append(current_item)

        org_list = OrgList(type=NodeType.LIST, list_type=list_type)
        org_list.children = items
        return org_list
