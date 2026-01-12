"""Data models for org-mode and Google Docs structures."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class NodeType(Enum):
    """Org-mode node types."""

    DOCUMENT = "document"
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    TEXT = "text"
    LINK = "link"
    TABLE = "table"
    SRC_BLOCK = "src_block"
    IMAGE = "image"
    LIST = "list"
    LIST_ITEM = "list_item"
    PROPERTY_DRAWER = "property_drawer"
    GDOCS_COMMENT_DIRECTIVE = "gdocs_comment_directive"
    ANNOTATION_SECTION = "annotation_section"
    ARCHIVE_SECTION = "archive_section"


@dataclass
class OrgNode:
    """Base org-mode AST node."""

    type: NodeType
    children: list["OrgNode"] = field(default_factory=list)
    properties: dict[str, Any] = field(default_factory=dict)
    start_line: int | None = None
    end_line: int | None = None


@dataclass
class OrgHeading(OrgNode):
    """Org-mode heading."""

    level: int = 1
    title: str = ""
    todo_state: str | None = None  # TODO, DONE, etc.
    tags: list[str] = field(default_factory=list)
    priority: str | None = None  # A, B, C, etc.

    def __post_init__(self):
        if self.type is None:
            self.type = NodeType.HEADING


@dataclass
class OrgText(OrgNode):
    """Plain text with optional inline formatting spans."""

    content: str = ""

    def __post_init__(self):
        if self.type is None:
            self.type = NodeType.TEXT


@dataclass
class OrgParagraph(OrgNode):
    """Paragraph containing text and inline elements."""

    def __post_init__(self):
        if self.type is None:
            self.type = NodeType.PARAGRAPH


@dataclass
class OrgLink(OrgNode):
    """Link [[url][description]]."""

    url: str = ""
    description: str | None = None

    def __post_init__(self):
        if self.type is None:
            self.type = NodeType.LINK


@dataclass
class OrgSrcBlock(OrgNode):
    """#+BEGIN_SRC ... #+END_SRC."""

    language: str | None = None
    content: str = ""

    def __post_init__(self):
        if self.type is None:
            self.type = NodeType.SRC_BLOCK


@dataclass
class OrgTable(OrgNode):
    """Org-mode table."""

    rows: list[list[str]] = field(default_factory=list)
    has_header: bool = False

    def __post_init__(self):
        if self.type is None:
            self.type = NodeType.TABLE


@dataclass
class OrgList(OrgNode):
    """Org-mode list (bulleted, numbered, or description)."""

    list_type: str = "unordered"  # unordered, ordered, description

    def __post_init__(self):
        if self.type is None:
            self.type = NodeType.LIST


@dataclass
class OrgListItem(OrgNode):
    """Single item in an org list."""

    bullet: str = "-"  # -, +, *, 1., 1), etc.
    checkbox: str | None = None  # [ ], [X], [-]
    content: str = ""

    def __post_init__(self):
        if self.type is None:
            self.type = NodeType.LIST_ITEM


@dataclass
class OrgPropertyDrawer(OrgNode):
    """Property drawer :PROPERTIES: ... :END:."""

    def __post_init__(self):
        if self.type is None:
            self.type = NodeType.PROPERTY_DRAWER


@dataclass
class OrgDocument:
    """Complete org-mode document."""

    metadata: dict[str, str] = field(default_factory=dict)
    content: list[OrgNode] = field(default_factory=list)
    path: str | None = None

    def get_gdoc_id(self) -> str | None:
        """Get the linked Google Doc ID."""
        return self.metadata.get("GDOC_ID")

    def set_gdoc_id(self, doc_id: str) -> None:
        """Set the linked Google Doc ID."""
        self.metadata["GDOC_ID"] = doc_id

    def get_last_sync(self) -> str | None:
        """Get the last sync timestamp."""
        return self.metadata.get("LAST_SYNC")

    def set_last_sync(self, timestamp: str) -> None:
        """Set the last sync timestamp."""
        self.metadata["LAST_SYNC"] = timestamp


# Google Docs structures


@dataclass
class CommentReply:
    """Reply to a Google Docs comment."""

    id: str
    content: str
    author: str
    created_time: datetime


@dataclass
class Comment:
    """Google Docs comment."""

    id: str
    content: str
    author: str
    created_time: datetime
    resolved: bool = False
    anchor: str = ""  # Quoted text being commented on
    replies: list[CommentReply] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for output."""
        return {
            "id": self.id,
            "content": self.content,
            "author": self.author,
            "created_time": self.created_time.isoformat()
            if isinstance(self.created_time, datetime)
            else self.created_time,
            "resolved": self.resolved,
            "anchor": self.anchor,
            "replies": [
                {
                    "id": r.id,
                    "content": r.content,
                    "author": r.author,
                    "created_time": r.created_time.isoformat()
                    if isinstance(r.created_time, datetime)
                    else r.created_time,
                }
                for r in self.replies
            ],
        }


@dataclass
class Suggestion:
    """Google Docs suggestion."""

    id: str
    type: str  # 'insertion' or 'deletion'
    content: str
    author: str
    created_time: datetime
    start_index: int
    end_index: int
    location_hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for output."""
        return {
            "id": self.id,
            "type": self.type,
            "content": self.content,
            "author": self.author,
            "created_time": self.created_time.isoformat()
            if isinstance(self.created_time, datetime)
            else self.created_time,
            "start_index": self.start_index,
            "end_index": self.end_index,
            "location_hint": self.location_hint,
        }


# Sync state structures


class SyncStatus(Enum):
    """Status of sync between org file and Google Doc."""

    NOT_INITIALIZED = "not_initialized"
    SYNCED = "synced"
    LOCAL_CHANGES = "local_changes"
    REMOTE_CHANGES = "remote_changes"
    CONFLICT = "conflict"


@dataclass
class SyncState:
    """Current sync state for a document."""

    status: SyncStatus
    gdoc_id: str | None = None
    last_sync: str | None = None
    last_push_rev: str | None = None
    last_pull_rev: str | None = None
    pending_comments: int = 0
    pending_suggestions: int = 0
    local_modified: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for output."""
        return {
            "status": self.status.value,
            "gdoc_id": self.gdoc_id,
            "last_sync": self.last_sync,
            "last_push_rev": self.last_push_rev,
            "last_pull_rev": self.last_pull_rev,
            "pending_comments": self.pending_comments,
            "pending_suggestions": self.pending_suggestions,
            "local_modified": self.local_modified,
        }
