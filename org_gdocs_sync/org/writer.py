"""Write org-mode AST back to file format."""

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


class OrgWriter:
    """Serialize org-mode AST to file format."""

    def write_file(self, path: str | Path, doc: OrgDocument) -> None:
        """Write org document to file.

        Args:
            path: Output file path.
            doc: Document to write.
        """
        content = self.to_string(doc)
        path = Path(path)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)

    def to_string(self, doc: OrgDocument) -> str:
        """Convert org document to string.

        Args:
            doc: Document to convert.

        Returns:
            Org-mode formatted string.
        """
        lines = []

        # Write metadata
        for key, value in doc.metadata.items():
            lines.append(f"#+{key}: {value}")

        # Add blank line after metadata if there's content
        if doc.metadata and doc.content:
            lines.append("")

        # Write content
        for node in doc.content:
            node_lines = self._write_node(node)
            lines.extend(node_lines)

        return "\n".join(lines)

    def _write_node(self, node: OrgNode) -> list[str]:
        """Convert single node to lines."""
        if node.type == NodeType.HEADING:
            return self._write_heading(node)
        elif node.type == NodeType.TEXT:
            return self._write_text(node)
        elif node.type == NodeType.PARAGRAPH:
            return self._write_paragraph(node)
        elif node.type == NodeType.LINK:
            return self._write_link(node)
        elif node.type == NodeType.SRC_BLOCK:
            return self._write_src_block(node)
        elif node.type == NodeType.TABLE:
            return self._write_table(node)
        elif node.type == NodeType.LIST:
            return self._write_list(node)
        elif node.type == NodeType.GDOCS_COMMENT_DIRECTIVE:
            return self._write_gdocs_comment(node)
        else:
            # Unknown node type - skip
            return []

    def _write_heading(self, node: OrgNode) -> list[str]:
        """Write heading node."""
        heading = node if isinstance(node, OrgHeading) else None
        if not heading:
            return []

        lines = []

        # Build heading line
        stars = "*" * heading.level
        parts = [stars]

        if heading.todo_state:
            parts.append(heading.todo_state)

        if heading.priority:
            parts.append(f"[#{heading.priority}]")

        parts.append(heading.title)

        if heading.tags:
            tag_str = ":" + ":".join(heading.tags) + ":"
            parts.append(tag_str)

        lines.append(" ".join(parts))

        # Write properties if present
        if heading.properties:
            lines.append(":PROPERTIES:")
            for key, value in heading.properties.items():
                lines.append(f":{key}: {value}")
            lines.append(":END:")

        # Write children
        for child in heading.children:
            child_lines = self._write_node(child)
            lines.extend(child_lines)

        return lines

    def _write_text(self, node: OrgNode) -> list[str]:
        """Write text node."""
        text = node if isinstance(node, OrgText) else None
        if not text:
            return []
        if not text.content.strip():
            return []
        return [text.content]

    def _write_paragraph(self, node: OrgNode) -> list[str]:
        """Write paragraph node."""
        para = node if isinstance(node, OrgParagraph) else None
        if not para:
            return []

        # Serialize children to inline content
        content_parts = []
        for child in para.children:
            content_parts.append(self._inline_to_string(child))

        content = "".join(content_parts)
        if content.strip():
            return [content, ""]  # Add blank line after paragraph
        return []

    def _inline_to_string(self, node: OrgNode) -> str:
        """Convert inline node to string."""
        if node.type == NodeType.TEXT:
            text = node if isinstance(node, OrgText) else None
            return text.content if text else ""
        elif node.type == NodeType.LINK:
            link = node if isinstance(node, OrgLink) else None
            if not link:
                return ""
            if link.description:
                return f"[[{link.url}][{link.description}]]"
            return f"[[{link.url}]]"
        return ""

    def _write_link(self, node: OrgNode) -> list[str]:
        """Write link node (standalone)."""
        link = node if isinstance(node, OrgLink) else None
        if not link:
            return []
        if link.description:
            return [f"[[{link.url}][{link.description}]]"]
        return [f"[[{link.url}]]"]

    def _write_src_block(self, node: OrgNode) -> list[str]:
        """Write source block."""
        src = node if isinstance(node, OrgSrcBlock) else None
        if not src:
            return []

        lines = []
        if src.language:
            lines.append(f"#+BEGIN_SRC {src.language}")
        else:
            lines.append("#+BEGIN_SRC")

        # Add content lines
        lines.extend(src.content.split("\n"))

        lines.append("#+END_SRC")
        lines.append("")  # Blank line after

        return lines

    def _write_table(self, node: OrgNode) -> list[str]:
        """Write table node."""
        table = node if isinstance(node, OrgTable) else None
        if not table or not table.rows:
            return []

        lines = []

        # Calculate column widths
        col_widths = []
        for row in table.rows:
            for i, cell in enumerate(row):
                if i >= len(col_widths):
                    col_widths.append(len(cell))
                else:
                    col_widths[i] = max(col_widths[i], len(cell))

        # Write rows
        for i, row in enumerate(table.rows):
            cells = [cell.ljust(col_widths[j]) for j, cell in enumerate(row)]
            lines.append("| " + " | ".join(cells) + " |")

            # Add separator after header
            if i == 0 and table.has_header:
                sep = "|-" + "-+-".join("-" * w for w in col_widths) + "-|"
                lines.append(sep)

        lines.append("")  # Blank line after table

        return lines

    def _write_list(self, node: OrgNode) -> list[str]:
        """Write list node."""
        org_list = node if isinstance(node, OrgList) else None
        if not org_list:
            return []

        lines = []
        for i, item in enumerate(org_list.children):
            if isinstance(item, OrgListItem):
                bullet = item.bullet
                if org_list.list_type == "ordered" and bullet[0].isdigit():
                    bullet = f"{i + 1}."

                if item.checkbox:
                    lines.append(f"{bullet} [{item.checkbox}] {item.content}")
                else:
                    lines.append(f"{bullet} {item.content}")

        lines.append("")  # Blank line after list

        return lines

    def _write_gdocs_comment(self, node: OrgNode) -> list[str]:
        """Write GDOCS_COMMENT directive."""
        content = node.properties.get("content", "")
        return [f"#+GDOCS_COMMENT: {content}"]
