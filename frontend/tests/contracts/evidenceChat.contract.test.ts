import { describe, expect, it } from "vitest";

import { getEvidenceChatGroups } from "@/components/crime-map/EvidenceChatPanel";
import type { ChatResponse } from "@/lib/api";


describe("evidence chat response contract", () => {
  it("separates primary and legal-context citations and renders safety fields", () => {
    const payload: ChatResponse = {
      question: "What happened?",
      answer: "Evidence-linked answer",
      citations: [
        {
          evidence_id: 1,
          relationship_type: "suspect",
          evidence_type: "source_record",
          evidence_source: "registry_source",
          excerpt: "excerpt",
          confidence: 0.8,
        },
      ],
      legal_context_citations: [
        {
          legal_instrument_id: 10,
          legal_section_id: 11,
          title: "Criminal Code",
          section_label: "s. 266",
          language: "en",
          excerpt: "assault",
          source_url: "https://laws.example",
        },
      ],
      disclaimer: "Not legal advice",
      incident_found: true,
      safety_notes: ["Evidence-linked summary only."],
      unsupported_claims: ["No citation for intent claim."],
    };

    const groups = getEvidenceChatGroups(payload);

    expect(groups.primaryCitations).toHaveLength(1);
    expect(groups.legalContextCitations).toHaveLength(1);
    expect(groups.safetyNotes).toEqual(["Evidence-linked summary only."]);
    expect(groups.unsupportedClaims).toEqual(["No citation for intent claim."]);
  });

  it("defaults optional safety fields to empty arrays", () => {
    const payload: ChatResponse = {
      question: "Any evidence?",
      answer: "No supporting evidence found.",
      citations: [],
      legal_context_citations: [],
      disclaimer: "Not legal advice",
      incident_found: false,
    };

    const groups = getEvidenceChatGroups(payload);

    expect(groups.safetyNotes).toEqual([]);
    expect(groups.unsupportedClaims).toEqual([]);
  });
});
