# Org-Mode ↔ Google Docs Sync System
## Complete Implementation Plan

**Version**: 1.0  
**Date**: January 2026  
**Language**: Python 3.10+

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Requirements & Workflow](#requirements--workflow)
3. [Design Decisions & Rationale](#design-decisions--rationale)
4. [System Architecture](#system-architecture)
5. [Technical Specifications](#technical-specifications)
6. [Implementation Steps](#implementation-steps)
7. [API Capabilities & Constraints](#api-capabilities--constraints)
8. [Testing Strategy](#testing-strategy)

---

## Project Overview

### Problem Statement

The user is a document author who:
- Prefers authoring in org-mode (cannot work effectively in web applications)
- Needs to collaborate with a team that uses Google Docs
- Team members provide comments, suggestions, and edits in Google Docs
- Needs bidirectional sync: push org-mode content → Google Docs, pull comments/suggestions back

### Solution

A Python-based CLI tool (`org-gdocs-sync`) that:
1. **Pushes** org-mode documents to Google Docs as direct edits
2. **Pulls** suggestions and comments from Google Docs into org-mode annotations
3. Manages the sync state within the org-mode document itself (no external database)
4. Handles images, formatting, links, tables, and code blocks
5. Supports comment replies and resolution

### Key Constraint

**Google Docs API cannot create suggestions programmatically** - only read them. When pushing, all changes are direct edits, not suggestions. Comments CAN be created programmatically.

---

## Requirements & Workflow

### User's Primary Workflow

```
1. Author document in org-mode (source of truth)
   ↓
2. Push to Google Docs
   - Creates/updates the document
   - Posts any inline #+GDOCS_COMMENT: annotations as comments
   ↓
3. Team reviews in Google Docs
   - Makes suggestions (tracked changes)
   - Adds comments
   - Replies to comments
   ↓
4. Pull changes from Google Docs
   - Downloads suggestions and comments
   - Adds them as org-mode annotations in GDOCS_ANNOTATIONS sections
   ↓
5. Review in org-mode and integrate
   - Manually integrate suggested text
   - Reply to comments
   - Mark items as resolved/integrated
   ↓
6. Push updated content
   - Sends direct edits
   - Posts comment replies
   - Resolves addressed comments
   - Archives processed annotations
   ↓
7. Repeat from step 3
```

### Out of Scope

- **Full collaborative editing** - This is NOT a real-time collaborative editing system
- **Suggestions from org-mode** - Cannot create suggestions when pushing (API limitation)
- **Complex merge conflicts** - Manual resolution preferred over automatic merging

---

## Design Decisions & Rationale

### Decision 1: State Storage Location

**Q**: Should we use SQLite to track sync state?  
**A**: No, embed everything in the org-mode document itself.

**Rationale**:
- Org-mode has excellent property drawer support
- Everything stays in one file (version control friendly)
- No external dependencies
- Natural org-mode navigation works
- Simpler architecture

**Implementation**: Use `#+METADATA:` at document top and `:PROPERTIES:` drawers for annotations.

### Decision 2: Annotation Placement

**Q**: Where should pulled suggestions/comments appear in the org file?

**Options**:
- A. Inline at relevant location
- B. Collected at end of each section (CHOSEN)
- C. All at end of document

**Choice**: Option B - End of each section in `** GDOCS_ANNOTATIONS` subsection

**Rationale**:
- Keeps main content clean and readable
- Grouped by section makes them easy to find
- Doesn't clutter the authoring space
- Easy to review all pending items per section

### Decision 3: Processed Annotation Handling

**Q**: How to handle integrated suggestions and resolved comments?

**Options**:
- A. Delete entirely
- B. Change property + keep in place
- C. Change property + move to archive

**Choice**: Option C - Change `:STATUS:` to `integrated`/`resolved` and move to `* GDOCS_ARCHIVE` section

**Rationale**:
- Maintains history in org file
- Removes clutter from active sections
- Can reference later if needed
- Clear separation of pending vs. completed

### Decision 4: Org → Google Docs Mapping

**Decisions made**:

| Org-mode Feature | Google Docs Mapping | Rationale |
|------------------|---------------------|-----------|
| `*` `**` `***` headings | H1, H2, H3 levels | Natural hierarchical mapping |
| `* TODO` `* DONE` | Keep as text prefix | Preserve task state visibility |
| `[[url][text]]` | Hyperlinks | Preserve URLs |
| `#+BEGIN_SRC lang` | Monospace + language comment | API cannot create code blocks, but preserve language |
| Org tables | Google Docs tables | Direct structural mapping |
| `*bold*` `/italic/` `~code~` | Formatted text | Preserve formatting |
| Images `[[file:...]]` | Upload/download images | Sync with local filesystem |

### Decision 5: Comment Creation Method

**Q**: How to specify what to comment on from org-mode?

**Options**:
- A. Special syntax in file
- B. Select text + command
- C. Reference by line/heading

**Choice**: Option A - `#+GDOCS_COMMENT: text` inline in org file

**Rationale**:
- Natural org-mode syntax
- Easy to write while authoring
- Visible in plain text
- Gets removed/archived after posting

### Decision 6: Metadata Block Style

**Q**: Where should sync metadata live?

**Options**:
- A. Top-level property drawer
- B. Separate metadata block

**Choice**: Option B - `#+METADATA:` style at document top

**Rationale**:
- More visible/accessible
- Standard org-mode convention
- Easy to parse
- Doesn't require opening drawers

### Decision 7: Conflict Handling

**Q**: What if user has local changes AND new suggestions exist in Google Docs?

**Decision**: Warn user and require explicit override

**Implementation**:
```bash
sync pull document.org
# → Warning: Local changes detected
# → Use --force to pull anyway
# → Use --backup to create backup first
```

**Rationale**:
- Prevents accidental data loss
- Explicit user control
- Supports cautious workflow

### Decision 8: Image Handling

**Q**: How to handle images?

**Decision**: Download/upload from directory where org-mode finds them

**Implementation**:
- On push: Upload images from `./images/` or org-mode link paths
- On pull: Download to `./images/` directory
- Update org-mode links to local paths

**Rationale**:
- Consistent with org-mode conventions
- Version control friendly (images in repo)
- Offline access to images

### Decision 9: Special Section Handling

**Q**: Should `GDOCS_ANNOTATIONS` and `GDOCS_ARCHIVE` sections be pushed to Google Docs?

**Decision**: No, exclude them from push

**Rationale**:
- They're internal bookkeeping
- Team doesn't need to see sync metadata
- Keeps Google Doc clean

### Decision 10: Code Block Language Preservation

**Q**: Should we preserve language hint from `#+BEGIN_SRC language`?

**Decision**: Yes, as a comment prefix if possible

**Implementation**:
```
# Language: python
def hello():
    print("world")
```

**Rationale**:
- API cannot create fancy code blocks
- Preserves information for manual conversion
- Team can manually apply code block formatting in UI if desired

### Decision 11: Document Update Strategy

**Q**: Should push be incremental (diffs) or full replacement?

**Decision**: Always replace entire document content

**Rationale**:
- Simpler implementation
- Avoids complex diff algorithms
- Less error-prone
- Org-mode is source of truth anyway

---

## System Architecture

### High-Level Architecture

```
┌──────────────────┐
│   Org-Mode       │  ← User authors here (source of truth)
│   Document       │
│   (.org file)    │
└────────┬─────────┘
         │
         │ CLI Commands (sync push/pull/etc)
         │
    ┌────▼────────────────────────────┐
    │  org-gdocs-sync (Python)       │
    │                                 │
    │  ┌──────────┐   ┌────────────┐ │
    │  │Org Parser│   │  Converter │ │
    │  └──────────┘   └────────────┘ │
    │                                 │
    │  ┌──────────────────────────┐  │
    │  │  Sync Engine             │  │
    │  │  - Push workflow         │  │
    │  │  - Pull workflow         │  │
    │  │  - Conflict detection    │  │
    │  └──────────────────────────┘  │
    │                                 │
    │  ┌──────────────────────────┐  │
    │  │  Google API Client       │  │
    │  │  - Docs API              │  │
    │  │  - Drive API (comments)  │  │
    │  │  - OAuth2 auth           │  │
    │  └──────────────────────────┘  │
    └─────────────┬───────────────────┘
                  │
                  │ HTTPS/REST
                  │
    ┌─────────────▼───────────────────┐
    │      Google Workspace           │
    │                                  │
    │  ┌──────────────┐               │
    │  │ Google Docs  │               │
    │  │  Document    │               │
    │  └──────────────┘               │
    │         ↕                        │
    │  ┌──────────────┐               │
    │  │  Comments    │               │
    │  │  (Drive API) │               │
    │  └──────────────┘               │
    └──────────────────────────────────┘
                  ↕
    ┌─────────────────────────────────┐
    │  Team Members                    │
    │  - View document                 │
    │  - Make suggestions              │
    │  - Add comments                  │
    │  - Reply to comments             │
    └──────────────────────────────────┘
```

### Directory Structure

```
org-gdocs-sync/
├── pyproject.toml           # Python project config
├── README.md                # User documentation
├── setup.py                 # Package setup
├── requirements.txt         # Dependencies
├── .gitignore
│
├── org_gdocs_sync/
│   ├── __init__.py
│   ├── __main__.py         # Entry point: python -m org_gdocs_sync
│   ├── cli.py              # CLI command handlers
│   ├── config.py           # Configuration management
│   ├── auth.py             # OAuth2 authentication
│   ├── models.py           # Data classes
│   │
│   ├── gdocs/              # Google Docs/Drive API layer
│   │   ├── __init__.py
│   │   ├── client.py       # API client wrapper
│   │   ├── comments.py     # Comment operations
│   │   └── images.py       # Image upload/download
│   │
│   ├── org/                # Org-mode handling
│   │   ├── __init__.py
│   │   ├── parser.py       # Parse org → AST
│   │   ├── writer.py       # AST → org file
│   │   ├── metadata.py     # #+GDOC_ID: handling
│   │   └── annotations.py  # GDOCS_ANNOTATIONS sections
│   │
│   ├── convert/            # Conversion between formats
│   │   ├── __init__.py
│   │   ├── org_to_gdocs.py    # Org AST → GDocs requests
│   │   ├── gdocs_to_org.py    # GDocs → Org annotations
│   │   └── formatting.py      # Style mappings
│   │
│   └── sync/               # Sync orchestration
│       ├── __init__.py
│       ├── engine.py       # Core sync logic
│       ├── push.py         # Push workflow
│       ├── pull.py         # Pull workflow
│       └── conflict.py     # Conflict detection
│
└── tests/                  # Test suite
    ├── __init__.py
    ├── test_parser.py
    ├── test_converter.py
    ├── test_sync.py
    └── fixtures/
        └── sample.org
```

---

## Technical Specifications

### Org-Mode Document Format

#### Complete Example

```org
#+TITLE: Project Requirements Document
#+AUTHOR: Your Name
#+DATE: [2026-01-12 Mon]
#+GDOC_ID: 1abc...xyz
#+LAST_PUSH_REV: ALm...123
#+LAST_PULL_REV: ALm...456
#+LAST_SYNC: [2026-01-12 Mon 15:45]

* Introduction

This document describes the project requirements with *bold* text and /italic/ emphasis.

** Background

We need to implement a new feature. Here's a [[https://example.com][reference link]].

#+GDOCS_COMMENT: Should we add more historical context here?

** Current State

| Feature | Status | Priority |
|---------|--------|----------|
| Auth    | Done   | High     |
| API     | WIP    | High     |
| UI      | TODO   | Medium   |

** GDOCS_ANNOTATIONS

*** Comment from alice@example.com [2026-01-10 Fri 14:23]
:PROPERTIES:
:COMMENT_ID: abc123
:ANCHOR: "This document describes"
:RESOLVED: nil
:END:
Can we clarify the scope of this document?

**** Reply [2026-01-11 Sat 10:15]
Good point. I'll add a scope section in the next revision.

*** Suggestion from bob@example.com [2026-01-10 Fri 15:30]
:PROPERTIES:
:SUGG_ID: def456
:TYPE: insertion
:STATUS: pending
:LOCATION: After "Background" heading
:END:
We should also mention the technical constraints from the kickoff meeting.

* Implementation

** Technical Details

Here's a code example:

#+BEGIN_SRC python
def authenticate_user(credentials):
    """Authenticate user with OAuth2"""
    token = oauth2_flow.fetch_token(credentials)
    return token
#+END_SRC

** TODO Architecture Design
DEADLINE: <2026-01-20 Mon>

Need to finalize the system architecture.

** GDOCS_ANNOTATIONS

(no pending items)

* Images Example

Here's the system diagram:

[[./images/architecture.png]]

* Conclusion

Final thoughts and next steps.

** GDOCS_ANNOTATIONS

(no pending items)

* GDOCS_ARCHIVE

** Integrated Suggestions

*** Suggestion from charlie@example.com [2026-01-09 Thu 11:20]
:PROPERTIES:
:SUGG_ID: xyz789
:TYPE: deletion
:STATUS: integrated
:INTEGRATED_DATE: [2026-01-10 Fri 09:00]
:END:
Removed redundant paragraph in introduction

** Resolved Comments

*** Comment from dave@example.com [2026-01-08 Wed 16:45]
:PROPERTIES:
:COMMENT_ID: old123
:RESOLVED: t
:RESOLVED_DATE: [2026-01-10 Fri 09:30]
:END:
Question about formatting standards - addressed in style guide
```

#### Metadata Fields

```org
#+GDOC_ID: <google-doc-id>           # Google Docs document ID
#+LAST_PUSH_REV: <revision-id>       # Last pushed revision ID
#+LAST_PULL_REV: <revision-id>       # Last pulled revision ID
#+LAST_SYNC: [timestamp]             # Last sync timestamp
```

#### Annotation Properties

**Comment Properties**:
```org
:COMMENT_ID: abc123              # Google Docs comment ID
:ANCHOR: "quoted text"           # Text being commented on
:RESOLVED: nil                   # t or nil
:RESOLVED_DATE: [timestamp]      # When resolved (if applicable)
```

**Suggestion Properties**:
```org
:SUGG_ID: def456                 # Suggestion ID
:TYPE: insertion|deletion        # Type of suggestion
:STATUS: pending|integrated      # Processing status
:LOCATION: "description"         # Approximate location
:INTEGRATED_DATE: [timestamp]    # When integrated (if applicable)
```

### CLI Interface

#### Commands

```bash
# Initialize - create new or link existing document
sync init <org-file> [options]
  --title TEXT        Title for new Google Doc
  --gdoc-id ID        Link to existing Google Doc
  
# Push - upload org content to Google Docs
sync push <org-file> [options]
  --force            Push even if conflicts detected
  
# Pull - download suggestions/comments from Google Docs
sync pull <org-file> [options]
  --force            Pull despite local changes
  --backup           Create backup before pulling
  --interactive      Interactive conflict resolution

# Status - show sync state
sync status <org-file>

# Integrate suggestion - mark as integrated and archive
sync integrate <org-file> <suggestion-id>

# Resolve comment - mark as resolved (will be resolved on next push)
sync resolve <org-file> <comment-id>

# List pending items
sync list <org-file> [--type comments|suggestions|all]
```

#### Example Usage

```bash
# First time setup
cd ~/documents
sync init requirements.org --title "Project Requirements"

# Make edits in requirements.org, then push
sync push requirements.org

# Team adds comments/suggestions in Google Docs...

# Pull their feedback
sync pull requirements.org

# Review annotations in Emacs/org-mode...
# Edit requirements.org to integrate changes...

# Mark suggestion as integrated
sync integrate requirements.org def456

# Reply to comment (edit the annotation in org file, then push)
sync push requirements.org
```

### Org → Google Docs Conversion

#### Mapping Table

| Org Element | Google Docs Representation | Notes |
|-------------|----------------------------|-------|
| `* Heading` | Heading 1 (HEADING_1) | |
| `** Heading` | Heading 2 (HEADING_2) | |
| `*** Heading` | Heading 3 (HEADING_3) | Up to 6 levels |
| `* TODO Item` | "TODO Item" (plain text) | Keep keyword as prefix |
| `* DONE Item` | "DONE Item" (plain text) | Keep keyword as prefix |
| `*bold*` | Bold formatting | TextStyle.bold = true |
| `/italic/` | Italic formatting | TextStyle.italic = true |
| `~code~` or `=code=` | Monospace font | weightedFontFamily = 'Courier New' |
| `_underline_` | Underline | TextStyle.underline = true |
| `+strikethrough+` | Strikethrough | TextStyle.strikethrough = true |
| `[[url][text]]` | Hyperlink | Link.url = url, text displayed |
| `[[url]]` | Hyperlink | Link.url = url, url displayed |
| `- item` | Bullet list | CreateBullets request |
| `+ item` | Bullet list | CreateBullets request |
| `1. item` | Numbered list | CreateBullets with numbered style |
| Org table | Google Docs table | InsertTable request |
| `#+BEGIN_SRC lang` | Monospace paragraph | Prefix with "# Language: lang" |
| `[[file:img.png]]` | Inline image | Upload and insert image |
| `#+GDOCS_COMMENT:` | Google Docs comment | Post via Drive API |
| `** GDOCS_ANNOTATIONS` | (skip) | Not pushed to Google Docs |
| `* GDOCS_ARCHIVE` | (skip) | Not pushed to Google Docs |

#### Text Style Conversion

```python
# Org-mode emphasis → Google Docs TextStyle
STYLE_MAP = {
    'bold': {'bold': True},
    'italic': {'italic': True},
    'code': {
        'weightedFontFamily': {'fontFamily': 'Courier New'},
        'fontSize': {'magnitude': 10, 'unit': 'PT'}
    },
    'underline': {'underline': True},
    'strikethrough': {'strikethrough': True}
}
```

#### Heading Level Conversion

```python
def org_level_to_gdocs_style(level):
    """Convert org heading level to Google Docs named style"""
    if level == 1:
        return 'HEADING_1'
    elif level == 2:
        return 'HEADING_2'
    elif level == 3:
        return 'HEADING_3'
    elif level == 4:
        return 'HEADING_4'
    elif level == 5:
        return 'HEADING_5'
    elif level == 6:
        return 'HEADING_6'
    else:
        # Org-mode supports unlimited nesting, GDocs stops at 6
        return 'HEADING_6'
```

### Google Docs → Org Conversion

#### Suggestion Extraction

```python
def extract_suggestions(doc):
    """
    Extract suggestions from Google Docs document.
    
    Docs API returns suggestions as:
    - suggestedInsertionIds: list of insertion suggestion IDs
    - suggestedDeletionIds: list of deletion suggestion IDs
    
    These appear on TextRun and other elements.
    """
    suggestions = []
    
    for element in walk_document(doc):
        # Check for insertion suggestions
        if hasattr(element, 'suggestedInsertionIds'):
            for sugg_id in element.suggestedInsertionIds:
                suggestions.append({
                    'id': sugg_id,
                    'type': 'insertion',
                    'content': element.textRun.content,
                    'start_index': element.startIndex,
                    'end_index': element.endIndex,
                    'author': get_suggestion_author(doc, sugg_id)
                })
        
        # Check for deletion suggestions
        if hasattr(element, 'suggestedDeletionIds'):
            for sugg_id in element.suggestedDeletionIds:
                suggestions.append({
                    'id': sugg_id,
                    'type': 'deletion',
                    'content': element.textRun.content,
                    'start_index': element.startIndex,
                    'end_index': element.endIndex,
                    'author': get_suggestion_author(doc, sugg_id)
                })
    
    return suggestions
```

#### Comment Extraction

```python
def extract_comments(gdoc_id):
    """
    Extract comments via Drive API.
    
    Drive API returns richer comment data than Docs API.
    """
    comments_response = drive_service.comments().list(
        fileId=gdoc_id,
        includeDeleted=False,
        fields='comments(id,content,quotedFileContent,author,createdTime,resolved,replies(id,content,author,createdTime))'
    ).execute()
    
    comments = []
    for c in comments_response.get('comments', []):
        comments.append({
            'id': c['id'],
            'content': c['content'],
            'anchor': c.get('quotedFileContent', {}).get('value', ''),
            'author': c['author']['emailAddress'],
            'created_time': c['createdTime'],
            'resolved': c.get('resolved', False),
            'replies': [
                {
                    'id': r['id'],
                    'content': r['content'],
                    'author': r['author']['emailAddress'],
                    'created_time': r['createdTime']
                }
                for r in c.get('replies', [])
            ]
        })
    
    return comments
```

### Push Workflow

```python
def push_workflow(org_path: str, force: bool = False):
    """
    Complete push workflow:
    1. Parse org document
    2. Convert to Google Docs requests
    3. Replace document content
    4. Post inline comments
    5. Reply to comments
    6. Resolve comments
    7. Archive processed annotations
    8. Update metadata
    """
    
    # Step 1: Parse org document
    org_doc = parse_org_file(org_path)
    gdoc_id = org_doc.metadata.get('GDOC_ID')
    
    if not gdoc_id:
        raise ValueError("No GDOC_ID found. Run 'sync init' first.")
    
    # Step 2: Convert org content to Google Docs structure
    # Exclude GDOCS_ANNOTATIONS and GDOCS_ARCHIVE sections
    filtered_content = filter_sync_sections(org_doc)
    gdocs_requests = convert_org_to_gdocs(filtered_content)
    
    # Step 3: Replace entire document content
    clear_document_content(gdoc_id)
    apply_content_requests(gdoc_id, gdocs_requests)
    
    # Step 4: Post inline #+GDOCS_COMMENT: annotations
    inline_comments = extract_inline_comments(org_doc)
    for comment in inline_comments:
        create_comment(gdoc_id, comment['content'])
        # Remove from org file after posting
        comment.mark_for_removal()
    
    # Step 5: Reply to comments from annotation blocks
    pending_replies = extract_pending_replies(org_doc)
    for reply in pending_replies:
        create_reply(gdoc_id, reply['comment_id'], reply['content'])
        # Move to archive
        reply.mark_as_sent()
    
    # Step 6: Resolve comments marked with :RESOLVED: t
    comments_to_resolve = extract_resolvable_comments(org_doc)
    for comment in comments_to_resolve:
        resolve_comment(gdoc_id, comment['comment_id'])
        # Move to archive
        comment.move_to_archive()
    
    # Step 7: Archive processed annotations
    move_processed_to_archive(org_doc)
    
    # Step 8: Update metadata
    current_rev = get_latest_revision(gdoc_id)
    org_doc.metadata['LAST_PUSH_REV'] = current_rev
    org_doc.metadata['LAST_SYNC'] = format_timestamp(now())
    
    # Save updated org file
    write_org_file(org_path, org_doc)
    
    print(f"✓ Pushed to Google Docs: {gdoc_id}")
```

### Pull Workflow

```python
def pull_workflow(org_path: str, force: bool = False, backup: bool = False):
    """
    Complete pull workflow:
    1. Check for local changes
    2. Optionally create backup
    3. Fetch document with suggestions
    4. Fetch comments
    5. Download images
    6. Create annotation blocks
    7. Update metadata
    """
    
    # Step 1: Conflict detection
    org_doc = parse_org_file(org_path)
    gdoc_id = org_doc.metadata.get('GDOC_ID')
    
    if not gdoc_id:
        raise ValueError("No GDOC_ID found. Run 'sync init' first.")
    
    # Check if local file modified since last sync
    last_sync = org_doc.metadata.get('LAST_SYNC')
    file_mtime = datetime.fromtimestamp(os.path.getmtime(org_path))
    
    if last_sync and file_mtime > parse_timestamp(last_sync):
        if not force and not backup:
            print("⚠️  Local changes detected since last sync.")
            print("Options:")
            print("  1. Abort (default)")
            print("  2. Pull anyway: use --force")
            print("  3. Create backup first: use --backup")
            return
        
        if backup:
            backup_path = f"{org_path}.backup.{int(time.time())}"
            shutil.copy(org_path, backup_path)
            print(f"✓ Created backup: {backup_path}")
    
    # Step 2: Fetch document with suggestions inline
    doc = docs_service.documents().get(
        documentId=gdoc_id,
        suggestionsViewMode='SUGGESTIONS_INLINE'
    ).execute()
    
    # Step 3: Extract suggestions
    suggestions = extract_suggestions(doc)
    
    # Step 4: Fetch comments via Drive API
    comments = extract_comments(gdoc_id)
    
    # Step 5: Download images
    download_images(doc, org_doc.directory)
    
    # Step 6: Insert annotations into appropriate sections
    insert_annotations(org_doc, suggestions, comments)
    
    # Step 7: Update metadata
    current_rev = get_latest_revision(gdoc_id)
    org_doc.metadata['LAST_PULL_REV'] = current_rev
    org_doc.metadata['LAST_SYNC'] = format_timestamp(now())
    
    # Save updated org file
    write_org_file(org_path, org_doc)
    
    print(f"✓ Pulled {len(suggestions)} suggestions and {len(comments)} comments")
```

---

## API Capabilities & Constraints

### Google Docs API (v1)

**Capabilities**:
- ✅ Read document structure and content
- ✅ Get document with suggestions inline (`suggestionsViewMode`)
- ✅ Create and modify documents
- ✅ Insert text, images, tables
- ✅ Apply formatting (bold, italic, fonts, colors)
- ✅ Create headers, footers
- ✅ Use named ranges

**Limitations**:
- ❌ **Cannot create suggestions programmatically** (only read)
- ❌ Cannot create fancy code blocks with syntax highlighting (only monospace text)
- ❌ Suggestion anchoring uses internal IDs, hard to map precisely

### Google Drive API (v3)

**Comments API Capabilities**:
- ✅ List comments on a document
- ✅ Create comments (anchored or unanchored)
- ✅ Create replies to comments
- ✅ Update comments (e.g., mark as resolved)
- ✅ Delete comments
- ✅ Get comment thread history

**Limitations**:
- ❌ Comment anchoring uses opaque range IDs (`kix.xyz` format)
- ❌ Precise text positioning is complex

### Revisions API

**Capabilities**:
- ✅ List revisions (with metadata: author, timestamp)
- ✅ Get specific revision content
- ✅ Export revisions

**Limitations**:
- ❌ **Revision history may be incomplete** for frequently-edited documents
- ❌ Revisions get merged over time
- ❌ API may not return all revisions that UI shows

---

## Implementation Steps

### Phase 1: Project Setup & Authentication

#### Step 1.1: Create Project Structure

```bash
mkdir org-gdocs-sync
cd org-gdocs-sync

# Create directory structure
mkdir -p org_gdocs_sync/{gdocs,org,convert,sync}
mkdir -p tests/fixtures

# Create __init__.py files
touch org_gdocs_sync/__init__.py
touch org_gdocs_sync/gdocs/__init__.py
touch org_gdocs_sync/org/__init__.py
touch org_gdocs_sync/convert/__init__.py
touch org_gdocs_sync/sync/__init__.py
touch tests/__init__.py
```

#### Step 1.2: Create pyproject.toml

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "org-gdocs-sync"
version = "0.1.0"
description = "Sync org-mode documents with Google Docs"
readme = "README.md"
requires-python = ">=3.10"
license = {text = "MIT"}
authors = [
    {name = "Your Name", email = "your.email@example.com"}
]

dependencies = [
    "google-api-python-client>=2.100.0",
    "google-auth-httplib2>=0.1.1",
    "google-auth-oauthlib>=1.1.0",
    "click>=8.1.7",
    "python-dateutil>=2.8.2",
    "pyyaml>=6.0.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.3",
    "pytest-cov>=4.1.0",
    "black>=23.11.0",
    "ruff>=0.1.6",
]

[project.scripts]
sync = "org_gdocs_sync.cli:main"

[tool.setuptools.packages.find]
where = ["."]
include = ["org_gdocs_sync*"]
```

#### Step 1.3: Implement OAuth2 Authentication

File: `org_gdocs_sync/auth.py`

```python
"""
OAuth2 authentication for Google APIs.
"""
import os
import pickle
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Required scopes
SCOPES = [
    'https://www.googleapis.com/auth/documents',
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/drive.readonly'
]

CONFIG_DIR = Path.home() / '.config' / 'org-gdocs-sync'
CREDENTIALS_FILE = CONFIG_DIR / 'credentials.json'
TOKEN_FILE = CONFIG_DIR / 'token.pickle'

def get_credentials():
    """
    Get valid user credentials from storage or initiate OAuth2 flow.
    
    Returns:
        google.oauth2.credentials.Credentials
    """
    creds = None
    
    # Load existing token
    if TOKEN_FILE.exists():
        with open(TOKEN_FILE, 'rb') as token:
            creds = pickle.load(token)
    
    # Refresh or obtain new credentials
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                raise FileNotFoundError(
                    f"Credentials file not found: {CREDENTIALS_FILE}\n"
                    "Please download OAuth2 credentials from Google Cloud Console."
                )
            
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)
        
        # Save credentials
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(TOKEN_FILE, 'wb') as token:
            pickle.dump(creds, token)
    
    return creds

def setup_credentials():
    """Interactive setup for credentials."""
    print("Setting up Google API credentials...")
    print(f"Please place your OAuth2 credentials JSON file at:")
    print(f"  {CREDENTIALS_FILE}")
    print()
    print("To obtain credentials:")
    print("1. Go to https://console.cloud.google.com/")
    print("2. Create a project (or select existing)")
    print("3. Enable Google Docs API and Google Drive API")
    print("4. Create OAuth 2.0 credentials (Desktop app)")
    print("5. Download JSON and save to above location")
    print()
    
    if CREDENTIALS_FILE.exists():
        print("✓ Credentials file found")
        # Trigger OAuth flow
        get_credentials()
        print("✓ Authentication successful")
    else:
        raise FileNotFoundError("Please add credentials file first")
```

### Phase 2: Org-Mode Parser

#### Step 2.1: Define Data Models

File: `org_gdocs_sync/models.py`

```python
"""
Data models for org-mode and Google Docs structures.
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

class NodeType(Enum):
    """Org-mode node types"""
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
    COMMENT_BLOCK = "comment_block"
    SUGGESTION_BLOCK = "suggestion_block"
    ANNOTATION_SECTION = "annotation_section"
    ARCHIVE_SECTION = "archive_section"

@dataclass
class OrgNode:
    """Base org-mode AST node"""
    type: NodeType
    children: List['OrgNode'] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)
    start_line: Optional[int] = None
    end_line: Optional[int] = None

@dataclass
class OrgHeading(OrgNode):
    """Org-mode heading"""
    level: int = 1
    title: str = ""
    todo_state: Optional[str] = None  # TODO, DONE, etc.
    tags: List[str] = field(default_factory=list)

@dataclass
class OrgText(OrgNode):
    """Plain text with inline formatting"""
    content: str = ""
    bold: bool = False
    italic: bool = False
    code: bool = False
    underline: bool = False
    strikethrough: bool = False

@dataclass
class OrgLink(OrgNode):
    """Link [[url][description]]"""
    url: str = ""
    description: Optional[str] = None

@dataclass
class OrgSrcBlock(OrgNode):
    """#+BEGIN_SRC ... #+END_SRC"""
    language: Optional[str] = None
    content: str = ""

@dataclass
class OrgTable(OrgNode):
    """Org-mode table"""
    rows: List[List[str]] = field(default_factory=list)
    header_rows: int = 0

@dataclass
class OrgDocument:
    """Complete org-mode document"""
    metadata: Dict[str, str] = field(default_factory=dict)
    content: List[OrgNode] = field(default_factory=list)
    path: Optional[str] = None

@dataclass
class Comment:
    """Google Docs comment"""
    id: str
    content: str
    author: str
    created_time: datetime
    resolved: bool = False
    anchor: str = ""
    replies: List['CommentReply'] = field(default_factory=list)

@dataclass
class CommentReply:
    """Reply to a comment"""
    id: str
    content: str
    author: str
    created_time: datetime

@dataclass
class Suggestion:
    """Google Docs suggestion"""
    id: str
    type: str  # 'insertion' or 'deletion'
    content: str
    author: str
    created_time: datetime
    start_index: int
    end_index: int
    location_hint: str = ""
```

#### Step 2.2: Implement Org Parser

File: `org_gdocs_sync/org/parser.py`

```python
"""
Parse org-mode files into AST.
"""
import re
from pathlib import Path
from typing import List, Optional, Tuple
from datetime import datetime

from ..models import (
    OrgDocument, OrgNode, OrgHeading, OrgText, OrgLink,
    OrgSrcBlock, OrgTable, NodeType
)

class OrgParser:
    """Parse org-mode documents"""
    
    def __init__(self):
        self.heading_re = re.compile(r'^(\*+)\s+(TODO|DONE)?\s*(.*)$')
        self.link_re = re.compile(r'\[\[([^\]]+)\](?:\[([^\]]+)\])?\]')
        self.metadata_re = re.compile(r'^\#\+(\w+):\s*(.*)$')
        
    def parse_file(self, path: str) -> OrgDocument:
        """Parse org-mode file"""
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        doc = OrgDocument(path=path)
        
        # Parse metadata (#+KEY: value lines at top)
        line_idx = 0
        while line_idx < len(lines):
            line = lines[line_idx].rstrip()
            match = self.metadata_re.match(line)
            if match:
                key = match.group(1)
                value = match.group(2)
                doc.metadata[key] = value
                line_idx += 1
            elif line.strip() == '':
                line_idx += 1
            else:
                break
        
        # Parse content
        doc.content = self._parse_content(lines[line_idx:])
        
        return doc
    
    def _parse_content(self, lines: List[str]) -> List[OrgNode]:
        """Parse document content into nodes"""
        nodes = []
        i = 0
        
        while i < len(lines):
            line = lines[i].rstrip()
            
            # Heading
            heading_match = self.heading_re.match(line)
            if heading_match:
                level = len(heading_match.group(1))
                todo_state = heading_match.group(2)
                title = heading_match.group(3).strip()
                
                # Find heading children (until next heading of same/higher level)
                child_lines = []
                j = i + 1
                while j < len(lines):
                    next_line = lines[j]
                    next_match = self.heading_re.match(next_line)
                    if next_match and len(next_match.group(1)) <= level:
                        break
                    child_lines.append(next_line)
                    j += 1
                
                heading = OrgHeading(
                    type=NodeType.HEADING,
                    level=level,
                    title=title,
                    todo_state=todo_state,
                    children=self._parse_content(child_lines)
                )
                nodes.append(heading)
                i = j
                continue
            
            # Source block
            if line.startswith('#+BEGIN_SRC'):
                language = line[11:].strip() or None
                content_lines = []
                i += 1
                while i < len(lines):
                    if lines[i].rstrip().startswith('#+END_SRC'):
                        break
                    content_lines.append(lines[i].rstrip())
                    i += 1
                
                src_block = OrgSrcBlock(
                    type=NodeType.SRC_BLOCK,
                    language=language,
                    content='\n'.join(content_lines)
                )
                nodes.append(src_block)
                i += 1
                continue
            
            # Table
            if line.startswith('|'):
                table_lines = [line]
                i += 1
                while i < len(lines) and lines[i].strip().startswith('|'):
                    table_lines.append(lines[i].rstrip())
                    i += 1
                
                table = self._parse_table(table_lines)
                nodes.append(table)
                continue
            
            # Regular paragraph/text
            if line.strip():
                paragraph = self._parse_paragraph(line)
                nodes.append(paragraph)
            
            i += 1
        
        return nodes
    
    def _parse_paragraph(self, line: str) -> OrgNode:
        """Parse paragraph with inline formatting"""
        # Simple text for now - expand to handle inline markup
        return OrgText(
            type=NodeType.TEXT,
            content=line
        )
    
    def _parse_table(self, lines: List[str]) -> OrgTable:
        """Parse org-mode table"""
        rows = []
        header_rows = 0
        
        for line in lines:
            # Skip separator lines (|---|---|)
            if re.match(r'^\|[\s\-\+]+\|$', line):
                if not rows:  # First separator = end of header
                    header_rows = len(rows)
                continue
            
            # Parse cells
            cells = [cell.strip() for cell in line.split('|')[1:-1]]
            rows.append(cells)
        
        return OrgTable(
            type=NodeType.TABLE,
            rows=rows,
            header_rows=header_rows if header_rows else 1
        )
```

### Phase 3: Org → Google Docs Converter

File: `org_gdocs_sync/convert/org_to_gdocs.py`

```python
"""
Convert org-mode AST to Google Docs API requests.
"""
from typing import List, Dict, Any
from ..models import OrgDocument, OrgNode, OrgHeading, OrgText, NodeType

class OrgToGDocsConverter:
    """Convert org-mode to Google Docs structure"""
    
    def __init__(self):
        self.current_index = 1  # GDocs uses 1-based indexing
    
    def convert(self, org_doc: OrgDocument) -> List[Dict[str, Any]]:
        """
        Convert org document to list of batchUpdate requests.
        
        Returns list of request objects for documents.batchUpdate()
        """
        requests = []
        
        # Filter out sync sections
        content = self._filter_sync_sections(org_doc.content)
        
        # Convert each node
        for node in content:
            node_requests = self._convert_node(node)
            requests.extend(node_requests)
        
        return requests
    
    def _filter_sync_sections(self, nodes: List[OrgNode]) -> List[OrgNode]:
        """Remove GDOCS_ANNOTATIONS and GDOCS_ARCHIVE sections"""
        filtered = []
        for node in nodes:
            if node.type == NodeType.HEADING:
                heading = node
                if heading.title in ('GDOCS_ANNOTATIONS', 'GDOCS_ARCHIVE'):
                    continue
            filtered.append(node)
        return filtered
    
    def _convert_node(self, node: OrgNode) -> List[Dict[str, Any]]:
        """Convert single node to requests"""
        if node.type == NodeType.HEADING:
            return self._convert_heading(node)
        elif node.type == NodeType.TEXT:
            return self._convert_text(node)
        elif node.type == NodeType.SRC_BLOCK:
            return self._convert_src_block(node)
        elif node.type == NodeType.TABLE:
            return self._convert_table(node)
        # ... handle other types
        
        return []
    
    def _convert_heading(self, heading: OrgHeading) -> List[Dict[str, Any]]:
        """Convert heading to Google Docs requests"""
        requests = []
        
        # Build heading text with TODO state
        text = heading.title
        if heading.todo_state:
            text = f"{heading.todo_state} {text}"
        text += "\n"
        
        # Insert text
        start_index = self.current_index
        requests.append({
            'insertText': {
                'location': {'index': self.current_index},
                'text': text
            }
        })
        self.current_index += len(text)
        
        # Apply heading style
        heading_style = f"HEADING_{min(heading.level, 6)}"
        requests.append({
            'updateParagraphStyle': {
                'range': {
                    'startIndex': start_index,
                    'endIndex': self.current_index
                },
                'paragraphStyle': {
                    'namedStyleType': heading_style
                },
                'fields': 'namedStyleType'
            }
        })
        
        # Convert children
        for child in heading.children:
            child_requests = self._convert_node(child)
            requests.extend(child_requests)
        
        return requests
    
    def _convert_text(self, text_node: OrgText) -> List[Dict[str, Any]]:
        """Convert text with inline formatting"""
        requests = []
        
        content = text_node.content + "\n"
        start_index = self.current_index
        
        # Insert text
        requests.append({
            'insertText': {
                'location': {'index': self.current_index},
                'text': content
            }
        })
        self.current_index += len(content)
        
        # Apply formatting if needed
        if any([text_node.bold, text_node.italic, text_node.code]):
            text_style = {}
            
            if text_node.bold:
                text_style['bold'] = True
            if text_node.italic:
                text_style['italic'] = True
            if text_node.code:
                text_style['weightedFontFamily'] = {'fontFamily': 'Courier New'}
            
            requests.append({
                'updateTextStyle': {
                    'range': {
                        'startIndex': start_index,
                        'endIndex': self.current_index - 1  # Exclude newline
                    },
                    'textStyle': text_style,
                    'fields': ','.join(text_style.keys())
                }
            })
        
        return requests
    
    def _convert_src_block(self, src_block: OrgSrcBlock) -> List[Dict[str, Any]]:
        """Convert source block to monospace text"""
        requests = []
        
        # Add language comment if specified
        text = ""
        if src_block.language:
            text += f"# Language: {src_block.language}\n"
        text += src_block.content + "\n\n"
        
        start_index = self.current_index
        
        # Insert text
        requests.append({
            'insertText': {
                'location': {'index': self.current_index},
                'text': text
            }
        })
        self.current_index += len(text)
        
        # Apply monospace style
        requests.append({
            'updateTextStyle': {
                'range': {
                    'startIndex': start_index,
                    'endIndex': self.current_index - 2  # Exclude trailing newlines
                },
                'textStyle': {
                    'weightedFontFamily': {'fontFamily': 'Courier New'},
                    'fontSize': {'magnitude': 10, 'unit': 'PT'}
                },
                'fields': 'weightedFontFamily,fontSize'
            }
        })
        
        return requests
    
    def _convert_table(self, table: OrgTable) -> List[Dict[str, Any]]:
        """Convert org table to Google Docs table"""
        requests = []
        
        # Insert table
        rows = len(table.rows)
        cols = len(table.rows[0]) if table.rows else 0
        
        requests.append({
            'insertTable': {
                'location': {'index': self.current_index},
                'rows': rows,
                'columns': cols
            }
        })
        
        # Note: Populating table cells requires more complex logic
        # For now, this creates an empty table structure
        # Full implementation would insert text into each cell
        
        # Update index (rough estimate - needs refinement)
        self.current_index += (rows * cols * 2)
        
        return requests
```

### Phase 4: Google Docs Client

File: `org_gdocs_sync/gdocs/client.py`

```python
"""
Google Docs and Drive API client.
"""
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from typing import List, Dict, Any, Optional

from ..auth import get_credentials
from ..models import Comment, CommentReply, Suggestion

class GoogleDocsClient:
    """Wrapper for Google Docs and Drive APIs"""
    
    def __init__(self):
        creds = get_credentials()
        self.docs_service = build('docs', 'v1', credentials=creds)
        self.drive_service = build('drive', 'v3', credentials=creds)
    
    # Document operations
    
    def create_document(self, title: str) -> str:
        """Create new Google Doc, return document ID"""
        doc = self.docs_service.documents().create(
            body={'title': title}
        ).execute()
        return doc['documentId']
    
    def get_document(self, doc_id: str, suggestions_inline: bool = False) -> Dict:
        """Get document content"""
        params = {'documentId': doc_id}
        if suggestions_inline:
            params['suggestionsViewMode'] = 'SUGGESTIONS_INLINE'
        
        return self.docs_service.documents().get(**params).execute()
    
    def clear_document_content(self, doc_id: str):
        """Clear all content from document"""
        doc = self.get_document(doc_id)
        end_index = doc['body']['content'][-1]['endIndex']
        
        self.docs_service.documents().batchUpdate(
            documentId=doc_id,
            body={
                'requests': [{
                    'deleteContentRange': {
                        'range': {
                            'startIndex': 1,
                            'endIndex': end_index - 1
                        }
                    }
                }]
            }
        ).execute()
    
    def batch_update(self, doc_id: str, requests: List[Dict[str, Any]]):
        """Apply batch updates to document"""
        if not requests:
            return
        
        try:
            self.docs_service.documents().batchUpdate(
                documentId=doc_id,
                body={'requests': requests}
            ).execute()
        except HttpError as e:
            raise Exception(f"Failed to update document: {e}")
    
    # Comment operations (via Drive API)
    
    def list_comments(self, file_id: str) -> List[Comment]:
        """Get all comments on document"""
        response = self.drive_service.comments().list(
            fileId=file_id,
            includeDeleted=False,
            fields='comments(id,content,quotedFileContent,author,createdTime,resolved,replies(id,content,author,createdTime))'
        ).execute()
        
        comments = []
        for c in response.get('comments', []):
            comment = Comment(
                id=c['id'],
                content=c['content'],
                author=c['author']['emailAddress'],
                created_time=c['createdTime'],
                resolved=c.get('resolved', False),
                anchor=c.get('quotedFileContent', {}).get('value', ''),
                replies=[
                    CommentReply(
                        id=r['id'],
                        content=r['content'],
                        author=r['author']['emailAddress'],
                        created_time=r['createdTime']
                    )
                    for r in c.get('replies', [])
                ]
            )
            comments.append(comment)
        
        return comments
    
    def create_comment(self, file_id: str, content: str, anchor: Optional[str] = None):
        """Create a comment (anchored or unanchored)"""
        body = {'content': content}
        
        # Anchoring is complex - for now create unanchored comments
        # TODO: Implement proper anchoring if needed
        
        self.drive_service.comments().create(
            fileId=file_id,
            body=body,
            fields='id'
        ).execute()
    
    def create_reply(self, file_id: str, comment_id: str, content: str):
        """Reply to a comment"""
        self.drive_service.replies().create(
            fileId=file_id,
            commentId=comment_id,
            body={'content': content},
            fields='id'
        ).execute()
    
    def resolve_comment(self, file_id: str, comment_id: str):
        """Mark comment as resolved"""
        self.drive_service.comments().update(
            fileId=file_id,
            commentId=comment_id,
            body={'resolved': True}
        ).execute()
    
    # Revision operations
    
    def get_latest_revision(self, file_id: str) -> str:
        """Get latest revision ID"""
        revisions = self.drive_service.revisions().list(
            fileId=file_id,
            fields='revisions(id,modifiedTime)',
            pageSize=1
        ).execute()
        
        if revisions.get('revisions'):
            return revisions['revisions'][0]['id']
        return None
```

### Phase 5: Sync Engine

File: `org_gdocs_sync/sync/push.py`

```python
"""
Push workflow: org-mode → Google Docs
"""
from pathlib import Path
from datetime import datetime

from ..org.parser import OrgParser
from ..org.writer import OrgWriter
from ..convert.org_to_gdocs import OrgToGDocsConverter
from ..gdocs.client import GoogleDocsClient

def push(org_path: str, force: bool = False):
    """
    Push org-mode document to Google Docs.
    
    Steps:
    1. Parse org document
    2. Convert to Google Docs requests
    3. Replace document content
    4. Post inline comments
    5. Reply to comments
    6. Resolve comments
    7. Archive processed annotations
    8. Update metadata
    """
    parser = OrgParser()
    converter = OrgToGDocsConverter()
    client = GoogleDocsClient()
    writer = OrgWriter()
    
    # Parse org file
    org_doc = parser.parse_file(org_path)
    
    # Validate
    gdoc_id = org_doc.metadata.get('GDOC_ID')
    if not gdoc_id:
        raise ValueError(
            "No GDOC_ID found in document. Run 'sync init' first."
        )
    
    print(f"Pushing {org_path} to Google Docs {gdoc_id}...")
    
    # Convert org content to Google Docs requests
    requests = converter.convert(org_doc)
    
    # Clear and update document
    print("  Clearing document...")
    client.clear_document_content(gdoc_id)
    
    print("  Uploading content...")
    client.batch_update(gdoc_id, requests)
    
    # TODO: Post inline comments
    # TODO: Reply to comments  
    # TODO: Resolve comments
    # TODO: Archive processed annotations
    
    # Update metadata
    rev_id = client.get_latest_revision(gdoc_id)
    org_doc.metadata['LAST_PUSH_REV'] = rev_id
    org_doc.metadata['LAST_SYNC'] = datetime.now().isoformat()
    
    # Save updated org file
    writer.write_file(org_path, org_doc)
    
    print("✓ Push complete")
```

File: `org_gdocs_sync/sync/pull.py`

```python
"""
Pull workflow: Google Docs → org-mode
"""
import os
import shutil
from pathlib import Path
from datetime import datetime

from ..org.parser import OrgParser
from ..org.writer import OrgWriter
from ..gdocs.client import GoogleDocsClient
from ..convert.gdocs_to_org import GDocsToOrgConverter

def pull(org_path: str, force: bool = False, backup: bool = False):
    """
    Pull suggestions and comments from Google Docs.
    
    Steps:
    1. Check for local changes
    2. Optionally create backup
    3. Fetch document with suggestions
    4. Fetch comments
    5. Create annotation blocks
    6. Update metadata
    """
    parser = OrgParser()
    client = GoogleDocsClient()
    converter = GDocsToOrgConverter()
    writer = OrgWriter()
    
    # Parse org file
    org_doc = parser.parse_file(org_path)
    
    # Validate
    gdoc_id = org_doc.metadata.get('GDOC_ID')
    if not gdoc_id:
        raise ValueError(
            "No GDOC_ID found in document. Run 'sync init' first."
        )
    
    # Conflict detection
    last_sync = org_doc.metadata.get('LAST_SYNC')
    if last_sync:
        file_mtime = datetime.fromtimestamp(os.path.getmtime(org_path))
        last_sync_dt = datetime.fromisoformat(last_sync)
        
        if file_mtime > last_sync_dt:
            if not force and not backup:
                print("⚠️  Local changes detected since last sync.")
                print("Options:")
                print("  1. Abort (default)")
                print("  2. Pull anyway: use --force")
                print("  3. Create backup first: use --backup")
                return
            
            if backup:
                backup_path = f"{org_path}.backup.{int(file_mtime.timestamp())}"
                shutil.copy(org_path, backup_path)
                print(f"✓ Created backup: {backup_path}")
    
    print(f"Pulling from Google Docs {gdoc_id}...")
    
    # Fetch document with suggestions
    print("  Fetching suggestions...")
    doc = client.get_document(gdoc_id, suggestions_inline=True)
    
    # Fetch comments
    print("  Fetching comments...")
    comments = client.list_comments(gdoc_id)
    
    # Convert to annotations
    print("  Creating annotations...")
    converter.add_annotations(org_doc, doc, comments)
    
    # Update metadata
    rev_id = client.get_latest_revision(gdoc_id)
    org_doc.metadata['LAST_PULL_REV'] = rev_id
    org_doc.metadata['LAST_SYNC'] = datetime.now().isoformat()
    
    # Save updated org file
    writer.write_file(org_path, org_doc)
    
    print(f"✓ Pull complete")
    print(f"  {len(comments)} comments added to annotations")
```

### Phase 6: CLI Interface

File: `org_gdocs_sync/cli.py`

```python
"""
Command-line interface.
"""
import click
from pathlib import Path

from .sync.push import push
from .sync.pull import pull
from .auth import setup_credentials
from .gdocs.client import GoogleDocsClient
from .org.parser import OrgParser
from .org.writer import OrgWriter

@click.group()
def main():
    """Sync org-mode documents with Google Docs"""
    pass

@main.command()
@click.argument('org_file', type=click.Path(exists=True))
@click.option('--title', help='Title for new Google Doc')
@click.option('--gdoc-id', help='Link to existing Google Doc')
def init(org_file, title, gdoc_id):
    """Initialize sync for an org-mode document"""
    parser = OrgParser()
    writer = OrgWriter()
    client = GoogleDocsClient()
    
    org_doc = parser.parse_file(org_file)
    
    # Check if already initialized
    if org_doc.metadata.get('GDOC_ID'):
        click.echo("Error: Document already initialized")
        click.echo(f"  GDOC_ID: {org_doc.metadata['GDOC_ID']}")
        return
    
    # Create or link Google Doc
    if gdoc_id:
        doc_id = gdoc_id
        click.echo(f"Linking to existing Google Doc: {doc_id}")
    else:
        doc_title = title or org_doc.metadata.get('TITLE', 'Untitled')
        doc_id = client.create_document(doc_title)
        click.echo(f"Created new Google Doc: {doc_id}")
    
    # Update org file metadata
    org_doc.metadata['GDOC_ID'] = doc_id
    org_doc.metadata['LAST_SYNC'] = datetime.now().isoformat()
    
    writer.write_file(org_file, org_doc)
    
    click.echo(f"✓ Initialized")
    click.echo(f"  Document URL: https://docs.google.com/document/d/{doc_id}/edit")

@main.command()
@click.argument('org_file', type=click.Path(exists=True))
@click.option('--force', is_flag=True, help='Push even if conflicts detected')
def push_cmd(org_file, force):
    """Push org-mode content to Google Docs"""
    push(org_file, force=force)

@main.command()
@click.argument('org_file', type=click.Path(exists=True))
@click.option('--force', is_flag=True, help='Pull despite local changes')
@click.option('--backup', is_flag=True, help='Create backup before pulling')
def pull_cmd(org_file, force, backup):
    """Pull suggestions and comments from Google Docs"""
    pull(org_file, force=force, backup=backup)

@main.command()
@click.argument('org_file', type=click.Path(exists=True))
def status(org_file):
    """Show sync status"""
    parser = OrgParser()
    org_doc = parser.parse_file(org_file)
    
    gdoc_id = org_doc.metadata.get('GDOC_ID')
    if not gdoc_id:
        click.echo("Not initialized. Run 'sync init' first.")
        return
    
    click.echo(f"Document: {org_file}")
    click.echo(f"Google Doc ID: {gdoc_id}")
    click.echo(f"URL: https://docs.google.com/document/d/{gdoc_id}/edit")
    click.echo(f"Last sync: {org_doc.metadata.get('LAST_SYNC', 'Never')}")
    
    # TODO: Count pending annotations

@main.command()
def setup():
    """Set up Google API credentials"""
    setup_credentials()

if __name__ == '__main__':
    main()
```

---

## Testing Strategy

### Unit Tests

**Test org parser**:
```python
def test_parse_heading():
    content = "* TODO Test Heading"
    # Parse and verify level, todo_state, title

def test_parse_table():
    content = """
| Header 1 | Header 2 |
|----------|----------|
| Cell 1   | Cell 2   |
"""
    # Parse and verify rows, columns

def test_parse_src_block():
    content = """
#+BEGIN_SRC python
def hello():
    print("world")
#+END_SRC
"""
    # Parse and verify language, content
```

**Test converter**:
```python
def test_heading_to_gdocs():
    # Create OrgHeading
    # Convert to requests
    # Verify insertText and updateParagraphStyle requests

def test_table_to_gdocs():
    # Create OrgTable
    # Convert to requests
    # Verify insertTable request with correct rows/cols
```

### Integration Tests

**Test round-trip**:
```python
def test_push_pull_roundtrip():
    # Create test org file
    # Push to Google Docs
    # Make changes in Google Docs (via API)
    # Pull back
    # Verify annotations created correctly
```

### Manual Testing

1. Create sample org file with various elements
2. Run `sync init` 
3. Run `sync push`
4. Open Google Doc in browser, verify formatting
5. Add comments and suggestions in UI
6. Run `sync pull`
7. Verify annotations appear in org file

---

## Next Steps for Implementation

### Immediate Priority (Phase 1-2)

1. Set up project structure
2. Implement OAuth2 authentication
3. Create basic org parser
4. Build simple converter (just headings and text)
5. Test with minimal example

### Medium Priority (Phase 3-4)

1. Expand converter to handle all org elements
2. Implement comment operations
3. Build push workflow
4. Build pull workflow
5. Add conflict detection

### Polish (Phase 5-6)

1. Implement annotation management
2. Add archive functionality
3. Improve error handling
4. Add comprehensive logging
5. Write documentation
6. Create test suite

---

## Notes for LLM Implementation Agent

### Critical Implementation Details

1. **Index Management**: Google Docs uses 1-based UTF-16 character indexing. Track `current_index` carefully when building requests.

2. **Request Ordering**: Some operations must be ordered correctly in batchUpdate. Generally:
   - Insert content first
   - Apply formatting second
   - Update styles last

3. **Error Handling**: Wrap all API calls in try-except blocks. Google APIs return detailed HttpError objects.

4. **OAuth Flow**: First run requires browser interaction. Store tokens securely in `~/.config/org-gdocs-sync/`.

5. **Testing**: Start with simple documents. Add complexity incrementally.

### Common Pitfalls

- **Forgetting to update current_index** after insertions
- **Off-by-one errors** in ranges (endIndex is exclusive)
- **Not handling UTF-16 surrogate pairs** (emojis consume 2 indices)
- **Clearing document incorrectly** (must preserve structural elements)

### Debugging Tips

- Use `documents.get()` to inspect document structure as JSON
- Print requests before sending to verify structure
- Test each converter function in isolation
- Start with empty document for testing

---

**End of Implementation Plan**
