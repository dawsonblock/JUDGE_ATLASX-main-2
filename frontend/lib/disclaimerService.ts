/**
 * Centralized source of truth for all public disclaimers.
 * Used across map legend, chat responses, record details, and warnings.
 */

export type DisclaimerVariant =
  | "map_legend"
  | "chat_response"
  | "record_detail"
  | "deprecated_warning"
  | "defendant_alert"
  | "source_coverage";

export const NEUTRAL_PUBLIC_DISCLAIMER =
  "Records shown are sourced from publicly available court and government records and are provided for research and informational purposes only. " +
  "Display of any record does not imply guilt, misconduct, corruption, dangerousness, legal fault, or any adverse legal conclusion. " +
  "Judicial conduct information does not reflect on the quality or impartiality of any judicial officer. " +
  "This platform does not provide legal advice and makes no representation as to the accuracy, currency, or completeness of any record. " +
  "Coverage is limited to sources actively monitored by this platform and may not reflect all proceedings, outcomes, or jurisdictions.";

export const DISCLAIMER_TEXT: Record<DisclaimerVariant, string> = {
  map_legend: NEUTRAL_PUBLIC_DISCLAIMER,
  chat_response: NEUTRAL_PUBLIC_DISCLAIMER,
  record_detail: NEUTRAL_PUBLIC_DISCLAIMER,
  deprecated_warning:
    "This source is deprecated and no longer ingesting new data. Please use the replacement source.",
  defendant_alert: NEUTRAL_PUBLIC_DISCLAIMER,
  source_coverage:
    "Source coverage is limited to jurisdictions and time periods for which public data is available. " +
    "Records may be incomplete, delayed, or absent for jurisdictions not yet onboarded to this platform.",
};

export const DISCLAIMER_STYLES: Record<DisclaimerVariant, string> = {
  map_legend: "text-xs text-gray-600 italic",
  chat_response: "text-sm text-gray-700 bg-gray-50 p-2 rounded",
  record_detail: "text-xs text-gray-600",
  deprecated_warning: "text-sm text-rose-700 bg-rose-50 p-3 rounded",
  defendant_alert: "text-sm text-amber-700 bg-amber-50 p-3 rounded",
  source_coverage: "text-xs text-blue-700 bg-blue-50 p-2 rounded",
};

export function getDisclaimer(variant: DisclaimerVariant) {
  return {
    text: DISCLAIMER_TEXT[variant],
    className: DISCLAIMER_STYLES[variant],
  };
}

/**
 * Component hook for disclaimer rendering
 * Usage in React component:
 *   const {text, className} = getDisclaimer("map_legend");
 *   return <div className={className}>{text}</div>;
 */
