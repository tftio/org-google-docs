"""Command-line interface for org-gdocs-sync."""

import sys

import click

from .auth import clear_credentials, setup_credentials
from .output import print_output
from .sync.engine import SyncEngine
from .sync.pull import pull as pull_workflow
from .sync.push import push as push_workflow

# Global option for JSON output
pass_json = click.make_pass_decorator(dict, ensure=True)


@click.group()
@click.option("--json", "use_json", is_flag=True, help="Output in JSON format instead of plist")
@click.pass_context
def main(ctx, use_json):
    """Sync org-mode documents with Google Docs.

    Default output format is Elisp plist. Use --json for JSON output.
    """
    ctx.ensure_object(dict)
    ctx.obj["use_json"] = use_json


@main.command()
@click.pass_context
def setup(ctx):
    """Set up Google API credentials.

    Follow the instructions to configure OAuth2 credentials for
    accessing Google Docs and Drive APIs.
    """
    try:
        setup_credentials()
        print_output(
            {"status": "success", "message": "Authentication configured"},
            use_json=ctx.obj.get("use_json", False),
        )
    except FileNotFoundError as e:
        print_output(
            {"status": "error", "message": str(e)},
            use_json=ctx.obj.get("use_json", False),
        )
        sys.exit(1)


@main.command()
@click.pass_context
def logout(ctx):
    """Clear stored authentication credentials."""
    clear_credentials()
    print_output(
        {"status": "success", "message": "Credentials cleared"},
        use_json=ctx.obj.get("use_json", False),
    )


@main.command()
@click.argument("org_file", type=click.Path(exists=True))
@click.option("--title", help="Title for new Google Doc")
@click.option("--gdoc-id", help="Link to existing Google Doc by ID")
@click.pass_context
def init(ctx, org_file, title, gdoc_id):
    """Initialize sync for an org-mode document.

    Creates a new Google Doc or links to an existing one.

    Examples:

        sync init document.org --title "My Document"

        sync init document.org --gdoc-id 1abc...xyz
    """
    use_json = ctx.obj.get("use_json", False)
    engine = SyncEngine()

    try:
        doc_id = engine.initialize(org_file, title=title, gdoc_id=gdoc_id)
        result = {
            "status": "success",
            "gdoc_id": doc_id,
            "url": engine.get_document_url(doc_id),
            "message": "initialized" if not gdoc_id else "linked",
        }
        print_output(result, use_json=use_json)
    except ValueError as e:
        print_output({"status": "error", "message": str(e)}, use_json=use_json)
        sys.exit(1)
    except Exception as e:
        print_output({"status": "error", "message": str(e)}, use_json=use_json)
        sys.exit(1)


@main.command()
@click.argument("org_file", type=click.Path(exists=True))
@click.option("--force", is_flag=True, help="Push even if conflicts detected")
@click.pass_context
def push(ctx, org_file, force):
    """Push org-mode content to Google Docs.

    Uploads the org document content to the linked Google Doc.
    Also posts any #+GDOCS_COMMENT: directives as comments.

    Example:

        sync push document.org
    """
    use_json = ctx.obj.get("use_json", False)

    try:
        result = push_workflow(org_file, force=force)
        result["status"] = "success"
        print_output(result, use_json=use_json)
    except ValueError as e:
        print_output({"status": "error", "message": str(e)}, use_json=use_json)
        sys.exit(1)
    except Exception as e:
        print_output({"status": "error", "message": str(e)}, use_json=use_json)
        sys.exit(1)


@main.command()
@click.argument("org_file", type=click.Path(exists=True))
@click.option("--force", is_flag=True, help="Pull despite local changes")
@click.option("--backup", is_flag=True, help="Create backup before pulling")
@click.pass_context
def pull(ctx, org_file, force, backup):
    """Pull suggestions and comments from Google Docs.

    Downloads suggestions and comments from the linked Google Doc
    and adds them as GDOCS_ANNOTATIONS sections in the org file.

    Example:

        sync pull document.org --backup
    """
    use_json = ctx.obj.get("use_json", False)

    try:
        result = pull_workflow(org_file, force=force, backup=backup)
        result["status"] = "success"
        print_output(result, use_json=use_json)
    except ValueError as e:
        print_output({"status": "error", "message": str(e)}, use_json=use_json)
        sys.exit(1)
    except RuntimeError as e:
        print_output({"status": "conflict", "message": str(e)}, use_json=use_json)
        sys.exit(1)
    except Exception as e:
        print_output({"status": "error", "message": str(e)}, use_json=use_json)
        sys.exit(1)


@main.command()
@click.argument("org_file", type=click.Path(exists=True))
@click.pass_context
def status(ctx, org_file):
    """Show sync status for a document.

    Displays current sync state including linked Google Doc,
    last sync time, and pending annotations.

    Example:

        sync status document.org
    """
    use_json = ctx.obj.get("use_json", False)
    engine = SyncEngine()

    state = engine.get_sync_state(org_file)
    result = state.to_dict()

    if state.gdoc_id:
        result["url"] = engine.get_document_url(state.gdoc_id)

    print_output(result, use_json=use_json)


@main.command("list")
@click.argument("org_file", type=click.Path(exists=True))
@click.option(
    "--type",
    "item_type",
    type=click.Choice(["comments", "suggestions", "all"]),
    default="all",
    help="Type of items to list",
)
@click.pass_context
def list_items(ctx, org_file, item_type):
    """List pending annotations in a document.

    Shows unresolved comments and/or pending suggestions.

    Examples:

        sync list document.org

        sync list document.org --type comments
    """
    use_json = ctx.obj.get("use_json", False)

    from .convert.gdocs_to_org import GDocsToOrgConverter
    from .org.parser import OrgParser

    parser = OrgParser()
    converter = GDocsToOrgConverter()

    doc = parser.parse_file(org_file)
    result = {}

    if item_type in ("comments", "all"):
        comments = converter.get_pending_comments(doc)
        result["comments"] = [
            {
                "id": c.properties.get("COMMENT_ID", ""),
                "title": c.title,
                "resolved": c.properties.get("RESOLVED") == "t",
            }
            for c in comments
        ]

    if item_type in ("suggestions", "all"):
        suggestions = converter.get_pending_suggestions(doc)
        result["suggestions"] = [
            {
                "id": s.properties.get("SUGG_ID", ""),
                "title": s.title,
                "type": s.properties.get("TYPE", ""),
                "status": s.properties.get("STATUS", ""),
            }
            for s in suggestions
        ]

    print_output(result, use_json=use_json)


@main.command()
@click.argument("org_file", type=click.Path(exists=True))
@click.argument("suggestion_id")
@click.pass_context
def integrate(ctx, org_file, suggestion_id):
    """Mark a suggestion as integrated.

    After manually applying a suggestion's changes to your document,
    use this command to mark it as integrated and archive it.

    Example:

        sync integrate document.org sugg123
    """
    use_json = ctx.obj.get("use_json", False)

    from .convert.gdocs_to_org import GDocsToOrgConverter
    from .org.parser import OrgParser
    from .org.writer import OrgWriter

    parser = OrgParser()
    converter = GDocsToOrgConverter()
    writer = OrgWriter()

    doc = parser.parse_file(org_file)

    if converter.mark_suggestion_integrated(doc, suggestion_id):
        writer.write_file(org_file, doc)
        print_output(
            {"status": "success", "suggestion_id": suggestion_id, "action": "integrated"},
            use_json=use_json,
        )
    else:
        print_output(
            {"status": "error", "message": f"Suggestion not found: {suggestion_id}"},
            use_json=use_json,
        )
        sys.exit(1)


@main.command()
@click.argument("org_file", type=click.Path(exists=True))
@click.argument("comment_id")
@click.pass_context
def resolve(ctx, org_file, comment_id):
    """Mark a comment as resolved.

    Marks a comment annotation as resolved. The comment will be
    resolved in Google Docs on the next push.

    Example:

        sync resolve document.org comment123
    """
    use_json = ctx.obj.get("use_json", False)

    from .convert.gdocs_to_org import GDocsToOrgConverter
    from .org.parser import OrgParser
    from .org.writer import OrgWriter

    parser = OrgParser()
    converter = GDocsToOrgConverter()
    writer = OrgWriter()

    doc = parser.parse_file(org_file)

    if converter.mark_comment_resolved(doc, comment_id):
        writer.write_file(org_file, doc)
        print_output(
            {"status": "success", "comment_id": comment_id, "action": "resolved"},
            use_json=use_json,
        )
    else:
        print_output(
            {"status": "error", "message": f"Comment not found: {comment_id}"},
            use_json=use_json,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
