"use client";

import { useState } from "react";
import { chatAboutEvidence } from "@/lib/api";
import type { ChatResponse, ChatCitation, LegalContextCitation } from "@/lib/api";
import { getDisclaimer } from "@/lib/disclaimerService";

interface EvidenceChatPanelProps {
  incidentId?: number;
  caseId?: number;
}

export function getEvidenceChatGroups(response: ChatResponse) {
  return {
    primaryCitations: response.citations,
    legalContextCitations: response.legal_context_citations,
    safetyNotes: response.safety_notes ?? [],
    unsupportedClaims: response.unsupported_claims ?? [],
  };
}

export function EvidenceChatPanel({ incidentId, caseId }: EvidenceChatPanelProps) {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<ChatResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isDisabled = incidentId == null && caseId == null;
  const neutralDisclaimer = getDisclaimer("chat_response").text;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim() || isDisabled) return;
    setLoading(true);
    setError(null);
    setResponse(null);
    try {
      const result = await chatAboutEvidence(question.trim(), {
        incident_id: incidentId,
        case_id: caseId,
      });
      setResponse(result);
    } catch {
      setError("Failed to get a response. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  if (isDisabled) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-6 text-center">
        <p className="text-slate-400 text-sm">
          Select an incident or case to ask questions about its evidence.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="shrink-0 p-3 border-b border-slate-200">
        <h3 className="text-sm font-semibold text-slate-800">Evidence Chat</h3>
        <p className="text-xs text-slate-500 mt-0.5">
          Ask questions about the evidence for this incident.
        </p>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-4">
        {response && (
          <>
            <div className="rounded-md bg-slate-50 border border-slate-200 p-3">
              <p className="text-xs font-medium text-slate-500 mb-1">Answer</p>
              <p className="text-sm text-slate-800 leading-relaxed whitespace-pre-wrap">
                {response.answer}
              </p>
            </div>

            {response.citations.length > 0 && (
              <div>
                <p className="text-xs font-medium text-slate-500 mb-2">
                  Citations ({response.citations.length})
                </p>
                <ul className="space-y-2">
                  {response.citations.map((c: ChatCitation) => (
                    <li
                      key={c.evidence_id}
                      className="rounded-md border border-slate-200 bg-white p-2 text-xs"
                    >
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <span className="font-medium text-slate-700 truncate">
                          {c.evidence_source}
                        </span>
                        <span className="shrink-0 rounded-full bg-blue-50 px-2 py-0.5 text-blue-700 font-medium">
                          {Math.round(c.confidence * 100)}%
                        </span>
                      </div>
                      <div className="text-slate-500 capitalize mb-1">
                        {c.relationship_type.replace(/_/g, " ")} &middot; {c.evidence_type}
                      </div>
                      {c.excerpt && (
                        <p className="text-slate-600 line-clamp-3 italic">&ldquo;{c.excerpt}&rdquo;</p>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {response.legal_context_citations.length > 0 && (
              <div>
                <p className="text-xs font-medium text-slate-500 mb-2">
                  Legal Context ({response.legal_context_citations.length})
                </p>
                <ul className="space-y-2">
                  {response.legal_context_citations.map((c: LegalContextCitation) => (
                    <li
                      key={`${c.legal_instrument_id}-${c.legal_section_id}`}
                      className="rounded-md border border-amber-200 bg-amber-50 p-2 text-xs"
                    >
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <span className="font-medium text-slate-700">{c.title}</span>
                        <span className="shrink-0 rounded-full bg-white px-2 py-0.5 text-amber-700 font-medium uppercase">
                          {c.language}
                        </span>
                      </div>
                      <div className="text-slate-500 mb-1">Section {c.section_label}</div>
                      {c.excerpt && <p className="text-slate-600 italic">&ldquo;{c.excerpt}&rdquo;</p>}
                      {c.source_url && (
                        <a
                          href={c.source_url}
                          target="_blank"
                          rel="noreferrer"
                          className="mt-2 inline-block text-amber-700 underline underline-offset-2"
                        >
                          View source
                        </a>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {!response.incident_found && response.legal_context_citations.length > 0 && (
              <div className="rounded-md border border-amber-200 bg-amber-50 p-3">
                <p className="text-xs text-amber-800">
                  No public incident-specific evidence was found. The citations above are legal context only.
                </p>
              </div>
            )}

            {response.safety_notes && response.safety_notes.length > 0 && (
              <div className="rounded-md border border-blue-200 bg-blue-50 p-3">
                <p className="text-xs font-medium text-blue-800 mb-1">Safety Notes</p>
                <ul className="list-disc pl-4 space-y-1">
                  {response.safety_notes.map((note) => (
                    <li key={note} className="text-xs text-blue-800">
                      {note}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {response.unsupported_claims && response.unsupported_claims.length > 0 && (
              <div className="rounded-md border border-red-200 bg-red-50 p-3">
                <p className="text-xs font-medium text-red-800 mb-1">Unsupported Claims</p>
                <ul className="list-disc pl-4 space-y-1">
                  {response.unsupported_claims.map((claim) => (
                    <li key={claim} className="text-xs text-red-800">
                      {claim}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <p className="text-xs text-slate-400 italic">{neutralDisclaimer}</p>
          </>
        )}

        {error && (
          <div className="rounded-md bg-red-50 border border-red-200 p-3">
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}
      </div>

      <form onSubmit={handleSubmit} className="shrink-0 border-t border-slate-200 p-3 flex gap-2">
        <input
          className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
          placeholder="Ask about this evidence…"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={loading}
        />
        <button
          type="submit"
          disabled={loading || !question.trim()}
          className="rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? "…" : "Ask"}
        </button>
      </form>
    </div>
  );
}
