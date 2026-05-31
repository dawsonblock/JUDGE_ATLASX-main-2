"""Tests for Canadian law ingestion adapters.

Tests Justice Laws and Saskatchewan law adapters.
"""

from unittest.mock import MagicMock

import pytest

from app.ingestion.laws.canada_federal_justice_xml import JusticeLawsAdapter
from app.ingestion.laws.canada_saskatchewan import SaskatchewanLawAdapter
from app.ingestion.laws.canada_federal_justice_xml import LawSection
from app.ingestion.laws.canada_saskatchewan import SaskatchewanLawSection

# ---------------------------------------------------------------------------
# Minimal HTML fixtures used by mocked HTTP responses
# ---------------------------------------------------------------------------
_FEDERAL_SECTION_HTML = """\
<!DOCTYPE html><html><body>
<main>
  <section>
    <p class="marginal-note">{heading}</p>
    <p><strong>{num}</strong> {body}</p>
  </section>
</main>
</body></html>
"""

_SK_ACT_HTML = """\
<!DOCTYPE html><html><body>
<main>
  <h3>{heading}</h3>
  <p>{body}</p>
</main>
</body></html>
"""

# Map section num -> (heading, body) for Criminal Code mocks
_CC_SECTIONS = {
    "515": (
        "Judicial interim release",
        "Where an accused is charged with an offence...",
    ),
    "718": (
        "Purpose and principles of sentencing",
        "The fundamental purpose of sentencing is...",
    ),
    "753": (
        "Dangerous offenders and long-term offenders",
        "The court may find an offender to be...",
    ),
}

_YCJA_SECTIONS = {
    "3": (
        "Declaration of principles",
        "The youth criminal justice system is based on...",
    ),
}


def _make_federal_client(sections_map: dict[str, tuple[str, str]]) -> MagicMock:
    """Return a mocked httpx.Client whose .get() returns HTML keyed by section num."""

    def fake_get(url: str, **kwargs):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        # extract section number from URL …/section-{NUM}.html
        part = url.rsplit("/section-", 1)[-1].replace(".html", "")
        heading, body = sections_map.get(part, ("Unknown heading", "Unknown body"))
        resp.text = _FEDERAL_SECTION_HTML.format(num=part, heading=heading, body=body)
        return resp

    client = MagicMock()
    client.get.side_effect = fake_get
    return client


def _make_sk_client(
    heading: str = "Definitions", body: str = "In this Act..."
) -> MagicMock:
    """Return a mocked httpx.Client for Saskatchewan acts."""
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.text = _SK_ACT_HTML.format(heading=heading, body=body)
    client = MagicMock()
    client.get.return_value = resp
    return client


class TestJusticeLawsAdapter:
    """Test federal Justice Laws adapter."""

    def test_adapter_initializes(self):
        """Adapter should initialize with default client."""
        adapter = JusticeLawsAdapter()
        assert adapter is not None
        assert adapter.BASE_URL == "https://laws.justice.gc.ca"

    def test_fetch_criminal_code_sections(self):
        """Should return Criminal Code sections from mocked HTTP."""
        adapter = JusticeLawsAdapter(client=_make_federal_client(_CC_SECTIONS))

        sections = adapter.fetch_act_sections("Criminal Code")

        assert len(sections) > 0
        for section in sections:
            assert section.jurisdiction == "CA-FED"
            assert section.source == "Justice Laws"
            assert section.law_title == "Criminal Code"
            assert section.law_type == "act"
            assert section.section_number
            assert section.section_heading
            assert section.source_url.startswith("https://")

    def test_sections_not_stubs_when_fetched(self):
        """Sections fetched from real HTTP must not be marked as stubs."""
        adapter = JusticeLawsAdapter(client=_make_federal_client(_CC_SECTIONS))

        sections = adapter.fetch_act_sections("Criminal Code")

        for section in sections:
            assert (
                section.is_stub is False
            ), f"Section {section.section_number} should not be a stub after real fetch"

    def test_sections_have_hash_when_fetched(self):
        """Sections fetched from real HTTP must have a non-empty raw_hash."""
        adapter = JusticeLawsAdapter(client=_make_federal_client(_CC_SECTIONS))

        sections = adapter.fetch_act_sections("Criminal Code")

        for section in sections:
            assert (
                section.raw_hash != ""
            ), f"Section {section.section_number} must have a raw_hash after real fetch"

    def test_sections_text_not_stub_marker(self):
        """Section text must not contain the [STUB] marker after real fetch."""
        adapter = JusticeLawsAdapter(client=_make_federal_client(_CC_SECTIONS))

        sections = adapter.fetch_act_sections("Criminal Code")

        for section in sections:
            assert (
                "[STUB]" not in section.section_text
            ), f"Section {section.section_number} still has [STUB] text after real fetch"

    def test_section_515_bail_exists(self):
        """Should have s. 515 (bail) in Criminal Code."""
        adapter = JusticeLawsAdapter(client=_make_federal_client(_CC_SECTIONS))

        sections = adapter.fetch_act_sections("Criminal Code")
        section_515 = [s for s in sections if s.section_number == "515"]

        assert len(section_515) == 1
        assert "Judicial interim release" in section_515[0].section_heading

    def test_section_718_sentencing_exists(self):
        """Should have s. 718 (sentencing) in Criminal Code."""
        adapter = JusticeLawsAdapter(client=_make_federal_client(_CC_SECTIONS))

        sections = adapter.fetch_act_sections("Criminal Code")
        section_718 = [s for s in sections if s.section_number == "718"]

        assert len(section_718) == 1
        assert "sentencing" in section_718[0].section_heading.lower()

    def test_section_753_dangerous_offender_exists(self):
        """Should have s. 753 (dangerous offender) in Criminal Code."""
        adapter = JusticeLawsAdapter(client=_make_federal_client(_CC_SECTIONS))

        sections = adapter.fetch_act_sections("Criminal Code")
        section_753 = [s for s in sections if s.section_number == "753"]

        assert len(section_753) == 1
        assert "dangerous" in section_753[0].section_heading.lower()

    def test_get_law_by_citation(self):
        """Should lookup law by citation."""
        adapter = JusticeLawsAdapter(client=_make_federal_client(_CC_SECTIONS))

        section = adapter.get_law_by_citation("Criminal Code, s. 515")

        assert section is not None
        assert section.section_number == "515"
        assert "Criminal Code" in section.law_title

    def test_link_event_to_law_bail(self):
        """Should link bail events to s. 515."""
        adapter = JusticeLawsAdapter(client=_make_federal_client(_CC_SECTIONS))

        laws = adapter.link_event_to_law(
            event_type="bail_hearing",
            event_description="Judicial interim release hearing",
        )

        section_515 = [l for l in laws if l.section_number == "515"]
        assert len(section_515) == 1

    def test_link_event_to_law_sentencing(self):
        """Should link sentencing events to s. 718."""
        adapter = JusticeLawsAdapter(client=_make_federal_client(_CC_SECTIONS))

        laws = adapter.link_event_to_law(
            event_type="sentencing",
            event_description="Sentencing hearing for offender",
        )

        section_718 = [l for l in laws if l.section_number == "718"]
        assert len(section_718) == 1

    def test_law_section_has_source_url(self):
        """All sections should have official source URLs."""
        adapter = JusticeLawsAdapter(client=_make_federal_client(_CC_SECTIONS))

        sections = adapter.fetch_act_sections("Criminal Code")

        for section in sections:
            assert section.source_url
            assert "laws.justice.gc.ca" in section.source_url

    def test_law_section_has_jurisdiction(self):
        """All sections should have CA-FED jurisdiction."""
        adapter = JusticeLawsAdapter(client=_make_federal_client(_CC_SECTIONS))

        sections = adapter.fetch_act_sections("Criminal Code")

        for section in sections:
            assert section.jurisdiction == "CA-FED"

    def test_unknown_act_returns_empty(self):
        """Unknown act name should return an empty list without error."""
        adapter = JusticeLawsAdapter(client=_make_federal_client(_CC_SECTIONS))

        sections = adapter.fetch_act_sections("Nonexistent Act")

        assert sections == []

    def test_http_error_returns_empty(self):
        """HTTP errors on section fetch should be swallowed and return empty list."""
        import httpx

        client = MagicMock()
        client.get.side_effect = httpx.HTTPError("timeout")
        adapter = JusticeLawsAdapter(client=client)

        sections = adapter.fetch_act_sections("Criminal Code")

        assert sections == []

    def test_ycja_sections(self):
        """YCJA fetch should delegate to fetch_act_sections."""
        adapter = JusticeLawsAdapter(client=_make_federal_client(_YCJA_SECTIONS))

        sections = adapter.fetch_youth_criminal_justice_sections()

        assert len(sections) > 0
        assert sections[0].law_title == "Youth Criminal Justice Act"
        assert sections[0].is_stub is False


class TestSaskatchewanLawAdapter:
    """Test Saskatchewan law adapter."""

    def test_adapter_initializes(self):
        """Adapter should initialize with default client."""
        adapter = SaskatchewanLawAdapter()
        assert adapter is not None
        assert adapter.BASE_URL == "https://publications.saskatchewan.ca"

    def test_fetch_police_act(self):
        """Should fetch Saskatchewan Police Act sections from mocked HTTP."""
        adapter = SaskatchewanLawAdapter(client=_make_sk_client())

        sections = adapter.fetch_police_act_sections()

        assert len(sections) > 0
        for section in sections:
            assert section.jurisdiction == "CA-SK"
            assert section.source == "Saskatchewan King's Printer"
            assert "Police Act" in section.law_title

    def test_sections_not_stubs_when_fetched(self):
        """Sections fetched from real HTTP must not be marked as stubs."""
        adapter = SaskatchewanLawAdapter(client=_make_sk_client())

        sections = adapter.fetch_police_act_sections()

        for section in sections:
            assert (
                section.is_stub is False
            ), f"Section {section.section_number} should not be a stub after real fetch"

    def test_sections_have_hash_when_fetched(self):
        """Sections fetched from real HTTP must have a non-empty raw_hash."""
        adapter = SaskatchewanLawAdapter(client=_make_sk_client())

        sections = adapter.fetch_police_act_sections()

        for section in sections:
            assert (
                section.raw_hash != ""
            ), f"Section {section.section_number} must have a raw_hash after real fetch"

    def test_fetch_correctional_services(self):
        """Should fetch Correctional Services Act sections."""
        adapter = SaskatchewanLawAdapter(client=_make_sk_client())

        sections = adapter.fetch_correctional_services_sections()

        assert len(sections) > 0
        for section in sections:
            assert section.jurisdiction == "CA-SK"
            assert "Correctional Services" in section.law_title

    def test_fetch_victims_of_crime(self):
        """Should fetch Victims of Crime Act sections."""
        adapter = SaskatchewanLawAdapter(client=_make_sk_client())

        sections = adapter.fetch_victims_of_crime_sections()

        assert len(sections) > 0
        for section in sections:
            assert section.jurisdiction == "CA-SK"
            assert "Victims of Crime" in section.law_title

    def test_http_error_returns_empty(self):
        """HTTP errors should be swallowed and return empty list."""
        import httpx

        client = MagicMock()
        client.get.side_effect = httpx.HTTPError("network error")
        adapter = SaskatchewanLawAdapter(client=client)

        assert adapter.fetch_police_act_sections() == []
        assert adapter.fetch_correctional_services_sections() == []
        assert adapter.fetch_victims_of_crime_sections() == []

    def test_get_law_by_citation_police(self):
        """Should lookup Police Act by citation."""
        adapter = SaskatchewanLawAdapter(client=_make_sk_client())

        section = adapter.get_law_by_citation("Saskatchewan Police Act, s. 5")

        assert section is not None
        assert "Police" in section.law_title

    def test_link_event_to_law_police(self):
        """Should link police events to Police Act."""
        adapter = SaskatchewanLawAdapter(client=_make_sk_client())

        laws = adapter.link_event_to_law(
            event_type="police_detention",
            event_description="Police officer detention incident",
        )

        police_sections = [l for l in laws if "Police" in l.law_title]
        assert len(police_sections) > 0

    def test_get_priority_laws(self):
        """Should return all priority laws."""
        adapter = SaskatchewanLawAdapter(client=_make_sk_client())

        laws = adapter.get_priority_laws()

        titles = [l.law_title for l in laws]
        assert any("Police" in t for t in titles)
        assert any("Correctional" in t for t in titles)
        assert any("Victims" in t for t in titles)

    def test_source_is_kings_printer(self):
        """Source should be Saskatchewan King's Printer."""
        adapter = SaskatchewanLawAdapter()

        sections = adapter.fetch_police_act_sections()

        for section in sections:
            assert "King's Printer" in section.source

    def test_saskatchewan_stub_sections_marked(self):
        """Saskatchewan hard-coded sections must be marked as stubs."""
        adapter = SaskatchewanLawAdapter()

        sections = adapter.fetch_police_act_sections()

        for section in sections:
            assert (
                section.is_stub is True
            ), f"Section {section.section_number} should be marked as stub"
            assert (
                "[STUB]" in section.section_text
            ), f"Section {section.section_number} text should indicate stub status"


class TestLawSectionStructure:
    """Test law section dataclass structure."""

    def test_federal_law_section_fields(self):
        """Federal sections should have all required fields."""
        section = LawSection(
            jurisdiction="CA-FED",
            source="Justice Laws",
            law_title="Criminal Code",
            law_type="act",
            chapter="R.S.C., 1985, c. C-46",
            section_number="515",
            section_heading="Judicial interim release",
            section_text="Order of release...",
            language="en",
            source_url="https://laws.justice.gc.ca/...",
            consolidation_date=None,
            raw_hash="abc123",
        )

        assert section.jurisdiction == "CA-FED"
        assert section.section_number == "515"
        assert len(section.raw_hash) > 0

    def test_provincial_law_section_fields(self):
        """Provincial sections should have all required fields."""
        section = SaskatchewanLawSection(
            jurisdiction="CA-SK",
            source="Saskatchewan King's Printer",
            law_title="Police Act",
            law_type="act",
            chapter="S.S. 2018, c. P-15.2",
            section_number="5",
            section_heading="Policing standards",
            section_text="The minister shall...",
            language="en",
            source_url="https://publications.saskatchewan.ca/...",
            consolidation_date=None,
            raw_hash="def456",
        )

        assert section.jurisdiction == "CA-SK"
        assert section.section_number == "5"
