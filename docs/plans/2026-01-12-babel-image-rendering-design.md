# Design: Babel Block Rendering for Google Docs Push

## Problem

When pushing org files to Google Docs, source blocks with `:file` header arguments (like mermaid diagrams) are dumped as raw code text instead of rendered images.

## Solution

Execute org-babel via Emacs batch mode during push, upload rendered images to Google Drive, and insert them inline in the Google Doc.

## Requirements

1. Source blocks with `:file` or `:results file` headers are rendered via babel
2. Source blocks without file output stay as monospace text
3. Rendered images appear in Google Docs (no source code shown)
4. Images stored in `{Doc Title}_assets/` subfolder in Drive
5. If any babel block fails to render, the push fails entirely

## Push Flow

```
org file
    │
    ▼
┌─────────────────────────────┐
│ 1. Identify babel blocks    │  Scan for #+BEGIN_SRC with :file headers
│    needing execution        │
└─────────────┬───────────────┘
              ▼
┌─────────────────────────────┐
│ 2. Execute babel via        │  emacs --batch --eval '(org-babel-execute-buffer)'
│    Emacs batch mode         │  → generates SVG/PNG files locally
└─────────────┬───────────────┘
              ▼
┌─────────────────────────────┐
│ 3. Create assets folder     │  "{Doc Title}_assets/" in same Drive folder
│    in Google Drive          │
└─────────────┬───────────────┘
              ▼
┌─────────────────────────────┐
│ 4. Upload rendered images   │  Upload SVG/PNG files, get Drive URLs
└─────────────┬───────────────┘
              ▼
┌─────────────────────────────┐
│ 5. Convert org → GDocs      │  Replace :file blocks with insertInlineImage
│    with image references    │  Other blocks stay as monospace text
└─────────────┬───────────────┘
              ▼
┌─────────────────────────────┐
│ 6. Push to Google Docs      │  batchUpdate with text + images
└─────────────────────────────┘
```

## Babel Execution

### Emacs Batch Invocation

```bash
emacs --batch \
  --eval "(require 'org)" \
  --eval "(setq org-confirm-babel-evaluate nil)" \
  --visit "/path/to/file.org" \
  --eval "(org-babel-execute-buffer)" \
  --kill
```

### Detection Logic

Before calling Emacs:
- Scan org file for `#+BEGIN_SRC` lines
- Parse header arguments looking for `:file <filename>`
- Build list of expected output files

After Emacs runs:
- Verify each expected file exists
- If any missing → fail with error listing which blocks failed

### Expected File Locations

- `:file foo.svg` → `{org_file_dir}/foo.svg`
- `:file ./diagrams/foo.svg` → `{org_file_dir}/diagrams/foo.svg`

### Error Handling

- Emacs exit code != 0 → fail with stderr output
- Expected file doesn't exist → fail with "Block at line N failed to produce: foo.svg"

## Google Drive Integration

### Assets Folder

```python
folder_name = f"{doc_title}_assets"
folder_id = drive_client.get_or_create_folder(
    name=folder_name,
    parent_id=doc_parent_folder_id
)
```

### Image Upload

```python
file_metadata = {
    "name": "current-auth-flow.svg",
    "parents": [folder_id]
}
media = MediaFileUpload(local_path, mimetype="image/svg+xml")
uploaded = drive_service.files().create(
    body=file_metadata,
    media_body=media,
    fields="id,webContentLink"
).execute()
```

### Update Behavior

- Check if image already exists in assets folder (by filename)
- If exists → update the file (new version)
- If not → create new file
- Old images from removed blocks stay (no auto-delete)

## Converter Changes

### New AST Node

```python
@dataclass
class OrgRenderedImage(OrgNode):
    """A babel block that was rendered to an image file."""
    source_language: str          # "mermaid", "dot", etc.
    local_path: Path              # /path/to/current-auth-flow.svg
    drive_url: str | None = None  # Set after upload
```

### Image Insertion Request

```python
def _insert_inline_image(self, node: OrgRenderedImage) -> None:
    request = {
        "insertInlineImage": {
            "location": {"index": self.current_index},
            "uri": node.drive_url,
            "objectSize": {
                "height": {"magnitude": 300, "unit": "PT"},
                "width": {"magnitude": 400, "unit": "PT"}
            }
        }
    }
    self.requests.append(request)
```

Default size 400x300pt; Google Docs maintains aspect ratio; user can resize manually.

## Implementation

### New Files

| File | Purpose |
|------|---------|
| `org_gdocs_sync/babel.py` | Emacs batch invocation, file detection |
| `org_gdocs_sync/gdocs/drive.py` | Drive folder/file upload helpers |

### Modified Files

| File | Changes |
|------|---------|
| `models.py` | Add `OrgRenderedImage` dataclass |
| `org/parser.py` | Detect `:file` header args, mark blocks for rendering |
| `convert/org_to_gdocs.py` | Add `_insert_inline_image()` method |
| `sync/push.py` | Insert babel execution + upload steps before conversion |
| `gdocs/client.py` | Add Drive folder/upload methods |

### Dependencies

None new. Uses:
- `subprocess` for Emacs invocation
- Existing `google-api-python-client` for Drive API

## Verification

1. Unit tests for header arg parsing
2. Integration test with simple mermaid block (requires Emacs + mmdc)
3. Manual test with RFC document
