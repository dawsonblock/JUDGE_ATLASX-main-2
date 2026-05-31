/** Frontend tests for admin source status logic (Phase 9). */

import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SourceControlCard } from "@/components/SourceControlCard";
import { authorityColour, lifecycleStateColour, sourceClassColour } from "@/lib/sourceContracts";
import type { AdminSourceItem } from "@/lib/api";

describe("Source Status Logic", () => {
  describe("authorityColour", () => {
    it("returns correct colour for official_court_record", () => {
      expect(authorityColour("official_court_record")).toBe("bg-cyan-100 text-cyan-800");
    });

    it("returns correct colour for official_government", () => {
      expect(authorityColour("official_government")).toBe("bg-violet-100 text-violet-800");
    });

    it("returns fallback colour for unknown authority", () => {
      expect(authorityColour("unknown")).toBe("bg-gray-100 text-gray-600");
    });

    it("returns fallback colour for invalid authority", () => {
      expect(authorityColour("invalid_authority")).toBe("bg-gray-100 text-gray-600");
    });
  });

  describe("lifecycleStateColour", () => {
    it("returns correct colour for runnable state", () => {
      expect(lifecycleStateColour("runnable")).toBe("bg-green-100 text-green-800");
    });

    it("returns correct colour for deprecated state", () => {
      expect(lifecycleStateColour("deprecated")).toBe("bg-rose-100 text-rose-800");
    });

    it("returns fallback colour for null state", () => {
      expect(lifecycleStateColour(null)).toBe("bg-gray-100 text-gray-500");
    });

    it("returns fallback colour for invalid state", () => {
      expect(lifecycleStateColour("invalid_state")).toBe("bg-gray-100 text-gray-500");
    });
  });

  describe("sourceClassColour", () => {
    it("returns correct colour for machine_ingest", () => {
      expect(sourceClassColour("machine_ingest")).toBe("bg-green-100 text-green-800");
    });

    it("returns correct colour for requires_api_key", () => {
      expect(sourceClassColour("requires_api_key")).toBe("bg-orange-100 text-orange-800");
    });

    it("returns fallback colour for null class", () => {
      expect(sourceClassColour(null)).toBe("bg-gray-100 text-gray-500");
    });

    it("returns fallback colour for invalid class", () => {
      expect(sourceClassColour("invalid_class")).toBe("bg-gray-100 text-gray-500");
    });
  });
});

describe("SourceControlCard Status Display", () => {
  const mockSource: AdminSourceItem = {
    id: 1,
    source_key: "test_source",
    source_name: "Test Source",
    source_type: "court_record",
    source_tier: "official",
    category: "court_decisions",
    public_record_authority: "official_court_record",
    source_class: "machine_ingest",
    lifecycle_state: "runnable",
    automation_status: "machine_ready",
    is_active: true,
    enabled_default: false,
    auto_publish_enabled: false,
    public_publish_default: false,
    rate_limit_rpm: 30,
    runnable_now: true,
    enable_ready: true,
    enable_blockers: [],
    health_score: 0.95,
    last_successful_fetch: null,
    last_ingested_at: "2024-01-01T00:00:00Z",
    parser: "test_parser",
    parser_version: "1.0",
    priority: 1,
    requires_manual_review: false,
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-01-01T00:00:00Z",
    creates: '["ReviewItem"]',
    jurisdiction: "Canada",
    country: "Canada",
    province_state: "Ontario",
    city: "Toronto",
    base_url: "https://example.com",
    allowed_domains: "example.com",
    refresh_interval_minutes: 60,
    terms_url: "https://example.com/terms",
    admin_notes: "Test notes",
    status_reason: null,
    operator_next_step: null,
    canonical_replacement_key: null,
  };

  it("displays active status when is_active is true", () => {
    render(<SourceControlCard source={mockSource} />);
    expect(screen.getByText(/active/i)).toBeInTheDocument();
  });

  it("displays disabled status when is_active is false", () => {
    const disabledSource = { ...mockSource, is_active: false };
    render(<SourceControlCard source={disabledSource} />);
    expect(screen.getByText(/disabled/i)).toBeInTheDocument();
  });

  it("displays authority badge with correct styling", () => {
    render(<SourceControlCard source={mockSource} />);
    expect(screen.getByText(/official court record/i)).toBeInTheDocument();
  });

  it("displays lifecycle state badge", () => {
    render(<SourceControlCard source={mockSource} />);
    expect(screen.getByText(/runnable/i)).toBeInTheDocument();
  });

  it("displays automation status badge", () => {
    render(<SourceControlCard source={mockSource} />);
    expect(screen.getByText(/machine ready/i)).toBeInTheDocument();
  });

  it("displays health score", () => {
    render(<SourceControlCard source={mockSource} />);
    expect(screen.getByText(/95%/i)).toBeInTheDocument();
  });

  it("displays enable blockers when present", () => {
    const blockedSource = {
      ...mockSource,
      is_active: false,
      enable_ready: false,
      enable_blockers: ["Missing API key", "Configuration required"],
    };
    render(<SourceControlCard source={blockedSource} />);
    expect(screen.getByText(/cannot enable yet/i)).toBeInTheDocument();
    expect(screen.getByText(/missing api key/i)).toBeInTheDocument();
  });

  it("displays deprecated warning when lifecycle_state is deprecated", () => {
    const deprecatedSource = {
      ...mockSource,
      lifecycle_state: "deprecated",
      canonical_replacement_key: "new_source",
    };
    render(<SourceControlCard source={deprecatedSource} />);
    expect(screen.getAllByText(/deprecated/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/new_source/i)).toBeInTheDocument();
  });

  it("disables enable button when source is not enable_ready", () => {
    const blockedSource = {
      ...mockSource,
      is_active: false,
      enable_ready: false,
      enable_blockers: ["Blocked"],
    };
    render(<SourceControlCard source={blockedSource} />);
    const enableButton = screen.getByRole("button", { name: /enable/i });
    expect(enableButton).toBeDisabled();
  });

  it("shows run button when source is active and runnable", () => {
    render(<SourceControlCard source={mockSource} />);
    expect(screen.getByRole("button", { name: /run now/i })).toBeInTheDocument();
  });

  it("hides run button when source is not active", () => {
    const disabledSource = { ...mockSource, is_active: false };
    render(<SourceControlCard source={disabledSource} />);
    expect(screen.queryByRole("button", { name: /run now/i })).not.toBeInTheDocument();
  });

  it("hides run button when source is not runnable", () => {
    const nonRunnableSource = { ...mockSource, runnable_now: false };
    render(<SourceControlCard source={nonRunnableSource} />);
    expect(screen.queryByRole("button", { name: /run now/i })).not.toBeInTheDocument();
  });

  it("displays manual review notice when requires_manual_review is true", () => {
    const reviewRequiredSource = {
      ...mockSource,
      requires_manual_review: true,
    };
    render(<SourceControlCard source={reviewRequiredSource} />);
    expect(screen.getByText(/requires manual review/i)).toBeInTheDocument();
  });

  it("displays status reason when provided", () => {
    const sourceWithReason = {
      ...mockSource,
      status_reason: "Source is under maintenance",
    };
    render(<SourceControlCard source={sourceWithReason} />);
    expect(screen.getByText(/source is under maintenance/i)).toBeInTheDocument();
  });

  it("displays operator next step when provided", () => {
    const sourceWithNextStep = {
      ...mockSource,
      operator_next_step: "Configure API credentials",
    };
    render(<SourceControlCard source={sourceWithNextStep} />);
    expect(screen.getByText(/configure api credentials/i)).toBeInTheDocument();
  });
});
