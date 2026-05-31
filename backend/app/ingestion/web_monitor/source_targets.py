"""Source target configuration for web monitoring.

Defines the schema for monitored source targets with strict allowlists
and safety controls.
"""

from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

from app.ingestion.source_keys import WEB_MONITOR_SASKATOON_POLICE_NEWS

_ALLOWED_SCHEMES = {"http", "https"}


def _parsed_allowed_host(url: str) -> str:
    """Parse URL and validate scheme, hostname, and credentials.

    Args:
        url: URL to parse

    Returns:
        Lowercased hostname with trailing dot stripped

    Raises:
        ValueError: If scheme is not http/https, hostname is missing, or credentials present
    """
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise ValueError(f"Unsupported URL scheme for {url}")
    if not parsed.hostname:
        raise ValueError(f"URL must include a hostname: {url}")
    if parsed.username or parsed.password:
        raise ValueError(f"URL must not include credentials: {url}")
    return parsed.hostname.lower().rstrip(".")


class WebMonitorTarget(BaseModel):
    """Configuration for a monitored web source target.

    All targets are disabled by default and require explicit admin enablement.
    Strict allowlist enforcement prevents open-ended crawling.
    """

    name: str = Field(..., description="Human-readable target name")
    source_type: str = Field(
        ...,
        description="Source classification (e.g., official_police_media, court_news)",
    )
    base_url: str = Field(..., description="Base URL of the source")
    allowed_domains: list[str] = Field(
        ...,
        description="Strict allowlist of domains (e.g., ['saskatoonpolice.ca'])",
    )
    start_urls: list[str] = Field(
        ...,
        description="Starting URLs for the monitor",
    )
    max_depth: int = Field(
        default=1,
        ge=0,
        le=3,
        description="Maximum crawl depth (0=start_urls only, max 3)",
    )
    max_requests: int = Field(
        default=25,
        ge=1,
        le=100,
        description="Maximum requests per run (enforced)",
    )
    concurrency: int = Field(
        default=2,
        ge=1,
        le=5,
        description="Concurrent requests (low by default)",
    )
    crawl_interval_hours: int = Field(
        default=24,
        ge=1,
        le=168,
        description="Hours between scheduled crawls",
    )
    source_tier: str = Field(
        default="news_only_context",
        description="Trust tier: news_only_context, official_police_open_data, etc.",
    )
    enabled: bool = Field(
        default=False,
        description="Whether this target is enabled (disabled by default)",
    )
    robots_txt_obey: bool = Field(
        default=True,
        description=(
            "Whether robots.txt must be respected for this target. "
            "When True, each URL is checked via urllib.robotparser before fetching. "
            "Enforcement uses a 5-second HTTP timeout; any error is permissive (allow). "
            "Always True for externally-hosted sources."
        ),
    )
    extractor_type: str = Field(
        ...,
        description="Extractor to use: police_release_index, court_news_index, etc.",
    )
    source_key: str = Field(
        ...,
        description="SourceRegistry key (lowercase letters, numbers, underscores, hyphens only)",
    )

    @field_validator("source_key")
    @classmethod
    def validate_source_key_format(cls, v: str) -> str:
        """Ensure source_key uses only safe identifier characters."""
        import re

        if not re.match(r"^[a-z0-9_-]+$", v):
            raise ValueError(
                "source_key must contain only lowercase letters, numbers, underscores, and hyphens"
            )
        return v

    @field_validator("allowed_domains")
    @classmethod
    def validate_domains_not_empty(cls, v):
        """Ensure allowlist is not empty."""
        if not v:
            raise ValueError("allowed_domains cannot be empty")
        return v

    @field_validator("start_urls")
    @classmethod
    def validate_start_urls_in_allowlist(cls, v, info):
        """Ensure all start URLs match allowed domains."""
        allowed_domains = info.data.get("allowed_domains", [])
        for url in v:
            try:
                domain = _parsed_allowed_host(url)
            except ValueError as e:
                raise ValueError(str(e))
            # Check if domain or its parent is in allowlist
            if not any(
                domain == allowed or domain.endswith(f".{allowed}")
                for allowed in allowed_domains
            ):
                raise ValueError(
                    f"Start URL {url} domain {domain} not in allowed_domains"
                )
        return v

    def is_url_allowed(self, url: str) -> bool:
        """Check if a URL is in the allowed domains list.

        Args:
            url: URL to check

        Returns:
            True if URL domain is in allowlist, False otherwise
        """
        try:
            domain = _parsed_allowed_host(url)
        except ValueError:
            return False

        # Check exact match or subdomain
        return any(
            domain == allowed or domain.endswith(f".{allowed}")
            for allowed in self.allowed_domains
        )

    def get_crawlee_config(self) -> dict:
        """Get Crawlee crawler configuration from this target.

        Returns:
            Dictionary of Crawlee configuration options
        """
        # Note: respect_robots_txt is not passed to HttpCrawler as Crawlee
        # doesn't expose direct control over robots.txt behavior
        return {
            "max_requests_per_crawl": self.max_requests,
            "max_crawl_depth": self.max_depth,
            "max_concurrency": self.concurrency,
        }


# Example target configurations (disabled by default)
# These are templates that can be enabled in admin panel

SASKATOON_POLICE_NEWS_TARGET = WebMonitorTarget(
    name="Saskatoon Police News Releases",
    source_type="news_only_context",
    base_url="https://saskatoonpolice.ca",
    allowed_domains=["saskatoonpolice.ca"],
    start_urls=["https://saskatoonpolice.ca/news/"],
    max_depth=1,
    max_requests=25,
    concurrency=2,
    source_tier="news_only_context",
    enabled=False,  # Disabled by default - must be enabled by admin
    extractor_type="police_release_index",
    source_key=WEB_MONITOR_SASKATOON_POLICE_NEWS,
)

# Additional example targets (all disabled)
COURT_NEWS_EXAMPLE_TARGET = WebMonitorTarget(
    name="Example Court News Page",
    source_type="court_news",
    base_url="https://example-court.gov",
    allowed_domains=["example-court.gov"],
    start_urls=["https://example-court.gov/news/"],
    max_depth=1,
    max_requests=15,
    concurrency=1,
    source_tier="news_only_context",
    enabled=False,
    extractor_type="court_news_index",
    source_key="web_monitor_court_news_example",
)

CITY_OPEN_DATA_EXAMPLE_TARGET = WebMonitorTarget(
    name="Example City Open Data",
    source_type="city_open_data",
    base_url="https://data.examplecity.gov",
    allowed_domains=["data.examplecity.gov"],
    start_urls=["https://data.examplecity.gov/datasets/"],
    max_depth=1,
    max_requests=20,
    concurrency=2,
    source_tier="official_government_statistics",
    enabled=False,
    extractor_type="city_open_data_landing_page",
    source_key="web_monitor_city_open_data_example",
)


# Registry of available targets (all disabled by default)
EXAMPLE_TARGETS = {
    "saskatoon_police_news": SASKATOON_POLICE_NEWS_TARGET,
    "court_news_example": COURT_NEWS_EXAMPLE_TARGET,
    "city_open_data_example": CITY_OPEN_DATA_EXAMPLE_TARGET,
}
