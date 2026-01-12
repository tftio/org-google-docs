# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

org-gdocs-sync is a bidirectional synchronization tool between Emacs org-mode documents and Google Docs. Authors work in org-mode (source of truth) while collaborators review and comment in Google Docs.

## Development Commands

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest
uv run pytest --cov              # with coverage
uv run pytest tests/test_parser.py::test_name  # single test

# Linting
uv run ruff check org_gdocs_sync tests
uv run ruff format org_gdocs_sync tests

# CLI (after uv tool install .)
org-gdocs setup                  # OAuth2 authentication
org-gdocs init doc.org --title "Title"  # create new Google Doc
org-gdocs push doc.org           # push org content to Google Docs
org-gdocs pull doc.org           # pull comments/suggestions
org-gdocs status doc.org         # check sync state
```

## Architecture

```
┌─────────────────────────────────────┐
│  Emacs (org-gdocs-mode.el)          │  Minor mode, C-c g keybindings
│  Calls Python CLI via shell         │  Reads plist output with (read ...)
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  Python CLI (cli.py)                │  Click-based, default plist output
└──────────────┬──────────────────────┘
               │
    ┌──────────┼──────────┐
    ▼          ▼          ▼
┌────────┐ ┌────────┐ ┌─────────┐
│ Parser │ │Convert │ │ Sync    │
│ (AST)  │ │ layers │ │ Engine  │
└────────┘ └────────┘ └─────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  Google Docs/Drive APIs             │
└─────────────────────────────────────┘
```

**Data flow:**
- Push: `org file → parser (AST) → org_to_gdocs converter → Google Docs API`
- Pull: `Google Docs API → gdocs_to_org converter → writer → org file`

## Key Modules

| Path | Purpose |
|------|---------|
| `org-gdocs-mode.el` | Emacs minor mode with keybindings and modeline |
| `org_gdocs_sync/cli.py` | Click CLI entry point |
| `org_gdocs_sync/org/parser.py` | Org-mode → AST parser |
| `org_gdocs_sync/org/writer.py` | AST → org-mode writer |
| `org_gdocs_sync/convert/org_to_gdocs.py` | AST → Google Docs API requests |
| `org_gdocs_sync/convert/gdocs_to_org.py` | Google Docs → org annotations |
| `org_gdocs_sync/sync/engine.py` | Orchestrates push/pull workflows |
| `org_gdocs_sync/output.py` | Plist and JSON output formatting |

## Important Patterns

**Plist output format**: CLI outputs Elisp plists by default for direct `(read ...)` in Emacs. Keys are `:kebab-case`. Use `--json` flag for JSON.

**Sync state in org file**: All sync metadata lives in the org file itself (no external database):
```org
#+GDOC_ID: <document-id>
#+LAST_SYNC: <ISO-8601>
#+LAST_PUSH_REV: <revision>
```

**Special sections excluded from push**:
- `* GDOCS_ANNOTATIONS` - pending comments/suggestions from collaborators
- `* GDOCS_ARCHIVE` - resolved/integrated items

**AST model classes** (in `models.py`): `OrgDocument`, `OrgHeading`, `OrgParagraph`, `OrgList`, `OrgTable`, `OrgSrcBlock`, `OrgLink`

## Google API Constraints

- Cannot create suggestions programmatically (API limitation)
- Comments posted from org-mode are unanchored (not tied to specific text)
- OAuth credentials stored at `~/.config/org-gdocs-sync/`

## Documentation

- `HOWTO.org` - User guide with workflow examples
- `org-gdocs-sync-plan.md` - Detailed design document and rationale
