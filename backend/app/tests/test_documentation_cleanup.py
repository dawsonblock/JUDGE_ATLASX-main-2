"""Tests for documentation cleanup (Phase 22).

Tests documentation cleanup utilities.
"""

from pathlib import Path

from app.docs.documentation_cleanup import DocumentationCleaner


class TestDocumentationCleaner:
    """Test documentation cleanup functionality."""

    def test_find_duplicate_sections_empty(self):
        """Test duplicate section finding with no docs."""
        cleaner = DocumentationCleaner("/nonexistent")
        result = cleaner.find_duplicate_sections()

        assert result["count"] == 0
        assert result["duplicates"] == []

    def test_find_orphaned_files_empty(self):
        """Test orphaned file finding with no docs."""
        cleaner = DocumentationCleaner("/nonexistent")
        result = cleaner.find_orphaned_files()

        assert result["count"] == 0
        assert result["orphaned"] == []

    def test_check_dead_links_empty(self):
        """Test dead link checking with no docs."""
        cleaner = DocumentationCleaner("/nonexistent")
        result = cleaner.check_dead_links()

        assert result["count"] == 0
        assert result["dead_links"] == []

    def test_generate_cleanup_report(self):
        """Test comprehensive cleanup report."""
        cleaner = DocumentationCleaner("/nonexistent")
        report = cleaner.generate_cleanup_report()

        assert "duplicate_sections" in report
        assert "orphaned_files" in report
        assert "dead_links" in report
        assert "total_issues" in report
        assert "needs_cleanup" in report
