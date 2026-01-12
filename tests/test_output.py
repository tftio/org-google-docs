"""Tests for sexpr/plist output formatting."""

import json

from org_gdocs_sync.output import (
    format_output,
    to_plist,
    to_plist_pretty,
    _to_kebab_case,
)


class TestKebabCase:
    def test_snake_case(self):
        assert _to_kebab_case("gdoc_id") == "gdoc-id"
        assert _to_kebab_case("last_sync_time") == "last-sync-time"

    def test_camel_case(self):
        assert _to_kebab_case("lastSync") == "last-sync"
        assert _to_kebab_case("pendingComments") == "pending-comments"

    def test_simple(self):
        assert _to_kebab_case("status") == "status"
        assert _to_kebab_case("id") == "id"


class TestToPlist:
    def test_none(self):
        assert to_plist(None) == "nil"

    def test_bool(self):
        assert to_plist(True) == "t"
        assert to_plist(False) == "nil"

    def test_numbers(self):
        assert to_plist(42) == "42"
        assert to_plist(3.14) == "3.14"

    def test_string(self):
        assert to_plist("hello") == '"hello"'
        assert to_plist('say "hi"') == '"say \\"hi\\""'
        assert to_plist("path\\to\\file") == '"path\\\\to\\\\file"'

    def test_empty_containers(self):
        assert to_plist({}) == "()"
        assert to_plist([]) == "()"

    def test_simple_dict(self):
        result = to_plist({"status": "synced", "count": 3})
        assert result == '(:status "synced" :count 3)'

    def test_dict_with_snake_case_keys(self):
        result = to_plist({"gdoc_id": "abc123", "last_sync": "2026-01-12"})
        assert result == '(:gdoc-id "abc123" :last-sync "2026-01-12")'

    def test_simple_list(self):
        result = to_plist(["a", "b", "c"])
        assert result == '("a" "b" "c")'

    def test_list_of_numbers(self):
        result = to_plist([1, 2, 3])
        assert result == "(1 2 3)"

    def test_nested_dict(self):
        data = {
            "status": "synced",
            "metadata": {"gdoc_id": "abc", "revision": 42},
        }
        result = to_plist(data)
        assert result == '(:status "synced" :metadata (:gdoc-id "abc" :revision 42))'

    def test_dict_with_list(self):
        data = {"comments": [{"id": "c1"}, {"id": "c2"}]}
        result = to_plist(data)
        assert result == '(:comments ((:id "c1") (:id "c2")))'

    def test_dict_with_bool(self):
        data = {"resolved": True, "pending": False}
        result = to_plist(data)
        assert result == "(:resolved t :pending nil)"


class TestToPlistPretty:
    def test_simple_dict(self):
        result = to_plist_pretty({"status": "ok"})
        assert ':status "ok"' in result
        assert result.startswith("(")
        assert result.endswith(")")

    def test_list_of_dicts(self):
        data = [{"id": "a"}, {"id": "b"}]
        result = to_plist_pretty(data)
        assert '(:id "a")' in result
        assert '(:id "b")' in result


class TestFormatOutput:
    def test_json_output(self):
        data = {"status": "synced", "count": 3}
        result = format_output(data, use_json=True, pretty=False)
        parsed = json.loads(result)
        assert parsed == data

    def test_plist_output(self):
        data = {"status": "synced", "count": 3}
        result = format_output(data, use_json=False, pretty=False)
        assert result == '(:status "synced" :count 3)'

    def test_json_pretty(self):
        data = {"status": "ok"}
        result = format_output(data, use_json=True, pretty=True)
        assert "\n" in result


class TestRealWorldExamples:
    """Test cases matching expected CLI output format."""

    def test_status_output(self):
        data = {
            "status": "synced",
            "gdoc_id": "1abc...xyz",
            "last_sync": "2026-01-12T10:00:00",
            "pending_comments": 3,
            "pending_suggestions": 1,
        }
        result = to_plist(data)
        # Should produce readable plist for Emacs
        assert ':status "synced"' in result
        assert ':gdoc-id "1abc...xyz"' in result
        assert ":pending-comments 3" in result

    def test_comments_list(self):
        data = {
            "comments": [
                {
                    "id": "abc123",
                    "author": "alice@example.com",
                    "anchor": "This document",
                    "content": "Can we clarify scope?",
                    "resolved": False,
                },
                {
                    "id": "def456",
                    "author": "bob@example.com",
                    "anchor": "Background",
                    "content": "Add more context",
                    "resolved": False,
                },
            ]
        }
        result = to_plist(data)
        assert ":comments" in result
        assert ':id "abc123"' in result
        assert ':author "alice@example.com"' in result
        assert ":resolved nil" in result
