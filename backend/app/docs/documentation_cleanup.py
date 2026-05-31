"""Documentation cleanup utility (Phase 22).

Provides tools for cleaning and organizing documentation.
"""

import logging
from pathlib import Path
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class DocumentationCleaner:
    """Cleans and organizes documentation files."""

    def __init__(self, docs_root: str):
        self.docs_root = Path(docs_root)

    def find_duplicate_sections(self) -> Dict[str, Any]:
        """Find duplicate sections in documentation.

        Returns:
            Dictionary of duplicate sections found
        """
        duplicates = []

        if not self.docs_root.exists():
            return {"duplicates": duplicates, "count": 0}

        for md_file in self.docs_root.rglob("*.md"):
            try:
                content = md_file.read_text()
                # Simple duplicate detection - check for repeated headers
                lines = content.split("\n")
                headers = [line for line in lines if line.startswith("#")]
                seen = set()
                for header in headers:
                    if header in seen:
                        duplicates.append({
                            "file": str(md_file),
                            "header": header,
                        })
                    seen.add(header)
            except Exception as e:
                logger.warning(f"Error reading {md_file}: {e}")

        return {
            "duplicates": duplicates,
            "count": len(duplicates),
        }

    def find_orphaned_files(self) -> Dict[str, Any]:
        """Find documentation files not linked from index.

        Returns:
            Dictionary of orphaned files
        """
        orphaned = []

        if not self.docs_root.exists():
            return {"orphaned": orphaned, "count": 0}

        # Find all markdown files
        all_files = set(self.docs_root.rglob("*.md"))

        # Find index files
        index_files = [
            f for f in all_files
            if f.name.lower() in ["readme.md", "index.md"]
        ]

        # Read index files to find links
        linked_files = set()
        for index_file in index_files:
            try:
                content = index_file.read_text()
                # Extract markdown links
                import re
                links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", content)
                for _, link in links:
                    if link.endswith(".md"):
                        linked_path = self.docs_root / link
                        if linked_path.exists():
                            linked_files.add(linked_path)
            except Exception as e:
                logger.warning(f"Error reading {index_file}: {e}")

        # Find orphaned files
        for md_file in all_files:
            if md_file not in linked_files and md_file not in index_files:
                orphaned.append(str(md_file))

        return {
            "orphaned": orphaned,
            "count": len(orphaned),
        }

    def check_dead_links(self) -> Dict[str, Any]:
        """Check for dead internal links.

        Returns:
            Dictionary of dead links found
        """
        dead_links = []

        if not self.docs_root.exists():
            return {"dead_links": dead_links, "count": 0}

        for md_file in self.docs_root.rglob("*.md"):
            try:
                content = md_file.read_text()
                import re
                links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", content)

                for text, link in links:
                    if link.endswith(".md"):
                        link_path = self.docs_root / link
                        if not link_path.exists():
                            dead_links.append({
                                "file": str(md_file),
                                "link_text": text,
                                "link_target": link,
                            })
            except Exception as e:
                logger.warning(f"Error reading {md_file}: {e}")

        return {
            "dead_links": dead_links,
            "count": len(dead_links),
        }

    def generate_cleanup_report(self) -> Dict[str, Any]:
        """Generate comprehensive cleanup report.

        Returns:
            Cleanup report with all issues
        """
        report = {
            "duplicate_sections": self.find_duplicate_sections(),
            "orphaned_files": self.find_orphaned_files(),
            "dead_links": self.check_dead_links(),
        }

        total_issues = (
            report["duplicate_sections"]["count"]
            + report["orphaned_files"]["count"]
            + report["dead_links"]["count"]
        )

        report["total_issues"] = total_issues
        report["needs_cleanup"] = total_issues > 0

        return report


def cleanup_documentation(docs_root: str = "docs") -> Dict[str, Any]:
    """Run documentation cleanup.

    Args:
        docs_root: Documentation root directory

    Returns:
        Cleanup report
    """
    cleaner = DocumentationCleaner(docs_root)
    return cleaner.generate_cleanup_report()
