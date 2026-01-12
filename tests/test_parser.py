"""Tests for org-mode parser."""

from pathlib import Path

from org_gdocs_sync.models import NodeType
from org_gdocs_sync.org.parser import OrgParser

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestMetadataParsing:
    def test_parse_metadata(self):
        parser = OrgParser()
        doc = parser.parse_string("""#+TITLE: Test Doc
#+AUTHOR: Test
#+GDOC_ID: abc123

* Heading
""")
        assert doc.metadata["TITLE"] == "Test Doc"
        assert doc.metadata["AUTHOR"] == "Test"
        assert doc.metadata["GDOC_ID"] == "abc123"

    def test_gdoc_id_helper(self):
        parser = OrgParser()
        doc = parser.parse_string("#+GDOC_ID: xyz789\n\n* Test")
        assert doc.get_gdoc_id() == "xyz789"


class TestHeadingParsing:
    def test_simple_heading(self):
        parser = OrgParser()
        doc = parser.parse_string("* Hello World")
        assert len(doc.content) == 1
        heading = doc.content[0]
        assert heading.type == NodeType.HEADING
        assert heading.level == 1
        assert heading.title == "Hello World"

    def test_nested_headings(self):
        parser = OrgParser()
        doc = parser.parse_string("""* Level 1
** Level 2
*** Level 3
** Another Level 2
""")
        assert len(doc.content) == 1
        h1 = doc.content[0]
        assert h1.level == 1
        assert len(h1.children) == 2  # Two level-2 children
        h2a = h1.children[0]
        assert h2a.level == 2
        assert len(h2a.children) == 1  # One level-3 child

    def test_heading_with_todo(self):
        parser = OrgParser()
        doc = parser.parse_string("* TODO Fix the bug")
        heading = doc.content[0]
        assert heading.todo_state == "TODO"
        assert heading.title == "Fix the bug"

    def test_heading_with_done(self):
        parser = OrgParser()
        doc = parser.parse_string("* DONE Complete task")
        heading = doc.content[0]
        assert heading.todo_state == "DONE"
        assert heading.title == "Complete task"

    def test_heading_with_priority(self):
        parser = OrgParser()
        doc = parser.parse_string("* [#A] High priority item")
        heading = doc.content[0]
        assert heading.priority == "A"
        assert heading.title == "High priority item"

    def test_heading_with_tags(self):
        parser = OrgParser()
        doc = parser.parse_string("* Task :work:urgent:")
        heading = doc.content[0]
        assert heading.title == "Task"
        assert heading.tags == ["work", "urgent"]

    def test_heading_with_todo_and_tags(self):
        parser = OrgParser()
        doc = parser.parse_string("* TODO [#B] Important task :project:coding:")
        heading = doc.content[0]
        assert heading.todo_state == "TODO"
        assert heading.priority == "B"
        assert heading.title == "Important task"
        assert heading.tags == ["project", "coding"]


class TestSrcBlockParsing:
    def test_src_block_with_language(self):
        parser = OrgParser()
        doc = parser.parse_string("""#+BEGIN_SRC python
def hello():
    print("world")
#+END_SRC
""")
        assert len(doc.content) == 1
        src = doc.content[0]
        assert src.type == NodeType.SRC_BLOCK
        assert src.language == "python"
        assert "def hello():" in src.content

    def test_src_block_without_language(self):
        parser = OrgParser()
        doc = parser.parse_string("""#+BEGIN_SRC
some code
#+END_SRC
""")
        src = doc.content[0]
        assert src.language is None
        assert src.content == "some code"

    def test_src_block_with_file_header(self):
        """Test parsing source block with :file header argument."""
        content = '''#+BEGIN_SRC mermaid :file diagram.svg :exports results
graph TD
    A --> B
#+END_SRC
'''
        parser = OrgParser()
        doc = parser.parse_string(content)

        assert len(doc.content) == 1
        src = doc.content[0]
        assert src.type == NodeType.SRC_BLOCK
        assert src.language == "mermaid"
        assert src.header_args == ":file diagram.svg :exports results"
        assert "graph TD" in src.content

    def test_src_block_without_header_args(self):
        """Test parsing source block without header arguments."""
        content = '''#+BEGIN_SRC python
print("hello")
#+END_SRC
'''
        parser = OrgParser()
        doc = parser.parse_string(content)

        src = doc.content[0]
        assert src.header_args == ""


class TestTableParsing:
    def test_simple_table(self):
        parser = OrgParser()
        doc = parser.parse_string("""| A | B |
| 1 | 2 |
""")
        assert len(doc.content) == 1
        table = doc.content[0]
        assert table.type == NodeType.TABLE
        assert len(table.rows) == 2
        assert table.rows[0] == ["A", "B"]
        assert table.rows[1] == ["1", "2"]

    def test_table_with_header(self):
        parser = OrgParser()
        doc = parser.parse_string("""| Header1 | Header2 |
|---------+---------|
| Cell1   | Cell2   |
""")
        table = doc.content[0]
        assert table.has_header is True
        assert len(table.rows) == 2


class TestListParsing:
    def test_unordered_list(self):
        parser = OrgParser()
        doc = parser.parse_string("""- Item 1
- Item 2
- Item 3
""")
        assert len(doc.content) == 1
        org_list = doc.content[0]
        assert org_list.type == NodeType.LIST
        assert org_list.list_type == "unordered"
        assert len(org_list.children) == 3

    def test_ordered_list(self):
        parser = OrgParser()
        doc = parser.parse_string("""1. First
2. Second
3. Third
""")
        org_list = doc.content[0]
        assert org_list.list_type == "ordered"

    def test_list_with_checkbox(self):
        parser = OrgParser()
        doc = parser.parse_string("""- [ ] Todo item
- [X] Done item
""")
        org_list = doc.content[0]
        assert org_list.children[0].checkbox == " "
        assert org_list.children[1].checkbox == "X"


class TestLinkParsing:
    def test_link_with_description(self):
        parser = OrgParser()
        doc = parser.parse_string("Check [[https://example.com][Example Site]] for info.")
        para = doc.content[0]
        # Find link in children
        links = [c for c in para.children if c.type == NodeType.LINK]
        assert len(links) == 1
        assert links[0].url == "https://example.com"
        assert links[0].description == "Example Site"

    def test_link_without_description(self):
        parser = OrgParser()
        doc = parser.parse_string("Visit [[https://example.com]]")
        para = doc.content[0]
        links = [c for c in para.children if c.type == NodeType.LINK]
        assert len(links) == 1
        assert links[0].url == "https://example.com"
        assert links[0].description is None


class TestGDocsComment:
    def test_gdocs_comment_directive(self):
        parser = OrgParser()
        doc = parser.parse_string("#+GDOCS_COMMENT: This needs review")
        assert len(doc.content) == 1
        node = doc.content[0]
        assert node.type == NodeType.GDOCS_COMMENT_DIRECTIVE
        assert node.properties["content"] == "This needs review"


class TestSampleFile:
    def test_parse_sample_file(self):
        parser = OrgParser()
        sample_path = FIXTURES_DIR / "sample.org"
        doc = parser.parse_file(sample_path)

        # Check metadata
        assert doc.metadata["TITLE"] == "Sample Document"
        assert doc.metadata["GDOC_ID"] == "1abc123xyz"

        # Check top-level headings
        headings = [n for n in doc.content if n.type == NodeType.HEADING]
        assert len(headings) == 3  # Introduction, Implementation, Conclusion

        # Check TODO heading
        impl_heading = headings[1]
        assert impl_heading.title == "Implementation"
        assert impl_heading.todo_state == "TODO"
        assert impl_heading.tags == ["work", "coding"]
