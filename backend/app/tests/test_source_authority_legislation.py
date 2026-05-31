"""Phase 7 regression — source_rules official_legislation authority.

Verifies that check_record_type_allowed() permits SourceSnapshot, LegalInstrument,
LegalSection, and ReviewItem for 'official_legislation' authority tier, and that
it still blocks invalid types.
"""

from __future__ import annotations

import pytest

from app.ingestion.source_rules import RuleViolation, check_record_type_allowed


_OFFICIAL_LEGISLATION_ALLOWED = {
    "SourceSnapshot",
    "LegalInstrument",
    "LegalSection",
    "ReviewItem",
}

_BLOCKED_TYPES = {
    "Event",
    "CrimeIncident",
    "Person",
    "Organisation",
    "AuditLog",
}


class TestOfficialLegislationAuthority:
    @pytest.mark.parametrize("record_type", sorted(_OFFICIAL_LEGISLATION_ALLOWED))
    def test_allowed_types_are_permitted(self, record_type: str) -> None:
        result = check_record_type_allowed(record_type, "official_legislation", None)
        assert result is None, (
            f"Expected '{record_type}' to be allowed for official_legislation, "
            f"got violation: {result}"
        )

    @pytest.mark.parametrize("record_type", sorted(_BLOCKED_TYPES))
    def test_blocked_types_are_rejected(self, record_type: str) -> None:
        result = check_record_type_allowed(record_type, "official_legislation", None)
        assert isinstance(result, RuleViolation), (
            f"Expected '{record_type}' to be blocked for official_legislation"
        )

    def test_legal_instrument_was_previously_blocked(self) -> None:
        """Guard: LegalInstrument must be allowed (was blocked before Phase 7 fix)."""
        result = check_record_type_allowed("LegalInstrument", "official_legislation", None)
        assert result is None, (
            "LegalInstrument must be allowed for official_legislation "
            "(was incorrectly blocked before Phase 7 fix)"
        )

    def test_legal_section_was_previously_blocked(self) -> None:
        """Guard: LegalSection must be allowed (was blocked before Phase 7 fix)."""
        result = check_record_type_allowed("LegalSection", "official_legislation", None)
        assert result is None

    def test_source_snapshot_was_previously_blocked(self) -> None:
        """Guard: SourceSnapshot must be allowed (was blocked before Phase 7 fix)."""
        result = check_record_type_allowed("SourceSnapshot", "official_legislation", None)
        assert result is None
