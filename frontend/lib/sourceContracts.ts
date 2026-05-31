/**
 * Canonical authority and tier types for the source registry UI.
 *
 * `PublicRecordAuthority` must stay in sync with the `public_record_authority`
 * column values written by the database seed / YAML loader.
 *
 * `SourceTier` must stay in sync with the `source_tier` column values.
 */

// ---------------------------------------------------------------------------
// Authority
// ---------------------------------------------------------------------------

export type PublicRecordAuthority =
  | "official_open_data"
  | "official_statistics"
  | "official_government"
  | "official_legislation"
  | "official_court_record"
  | "news_context"
  | "unknown";

/** Tailwind colour classes keyed by authority.  Exhaustive — add here when adding to the DB. */
export const AUTHORITY_COLOURS: Record<PublicRecordAuthority, string> = {
  official_open_data: "bg-blue-100 text-blue-800",
  official_statistics: "bg-indigo-100 text-indigo-800",
  official_government: "bg-violet-100 text-violet-800",
  official_legislation: "bg-purple-100 text-purple-800",
  official_court_record: "bg-cyan-100 text-cyan-800",
  news_context: "bg-amber-100 text-amber-800",
  unknown: "bg-gray-100 text-gray-600",
};

/** Human-readable labels for authority values. */
export const AUTHORITY_LABELS: Record<PublicRecordAuthority, string> = {
  official_open_data: "Official Open Data",
  official_statistics: "Official Statistics",
  official_government: "Official Government",
  official_legislation: "Official Legislation",
  official_court_record: "Official Court Record",
  news_context: "News Context",
  unknown: "Unknown",
};

/**
 * Returns the Tailwind colour string for `authority`, falling back to
 * `unknown` when the value is not one of the canonical set.
 */
export function authorityColour(authority: string): string {
  return (
    AUTHORITY_COLOURS[authority as PublicRecordAuthority] ??
    AUTHORITY_COLOURS.unknown
  );
}

// ---------------------------------------------------------------------------
// Tier
// ---------------------------------------------------------------------------

export type SourceTier =
  | "court_record"
  | "official_police_open_data"
  | "official_government_statistics"
  | "verified_news_context"
  | "news_only_context";

export const SOURCE_TIER_COLOURS: Record<SourceTier, string> = {
  court_record: "bg-cyan-100 text-cyan-800",
  official_police_open_data: "bg-blue-100 text-blue-800",
  official_government_statistics: "bg-indigo-100 text-indigo-800",
  verified_news_context: "bg-amber-100 text-amber-800",
  news_only_context: "bg-gray-100 text-gray-600",
};

export const SOURCE_TIER_LABELS: Record<SourceTier, string> = {
  court_record: "Court Record",
  official_police_open_data: "Official Police Open Data",
  official_government_statistics: "Official Government Statistics",
  verified_news_context: "Verified News Context",
  news_only_context: "News Only Context",
};

/**
 * Returns the Tailwind colour string for `tier`, falling back to
 * `news_only_context` when the value is not one of the canonical set.
 */
export function tierColour(tier: string): string {
  return (
    SOURCE_TIER_COLOURS[tier as SourceTier] ??
    SOURCE_TIER_COLOURS.news_only_context
  );
}

// ---------------------------------------------------------------------------
// Source class
// ---------------------------------------------------------------------------

export type SourceClass =
  | "machine_ingest"
  | "portal_reference"
  | "manual_reference"
  | "requires_api_key"
  | "disabled_stub"
  | "needs_endpoint_configuration";

export const SOURCE_CLASS_LABELS: Record<SourceClass, string> = {
  machine_ingest: "Machine Ingest",
  portal_reference: "Portal Reference",
  manual_reference: "Manual Reference",
  requires_api_key: "Requires API Key",
  disabled_stub: "Disabled Stub",
  needs_endpoint_configuration: "Needs Endpoint Config",
};

export const SOURCE_CLASS_COLOURS: Record<SourceClass, string> = {
  machine_ingest: "bg-green-100 text-green-800",
  portal_reference: "bg-amber-100 text-amber-800",
  manual_reference: "bg-gray-100 text-gray-600",
  requires_api_key: "bg-orange-100 text-orange-800",
  disabled_stub: "bg-red-100 text-red-700",
  needs_endpoint_configuration: "bg-yellow-100 text-yellow-800",
};

// ---------------------------------------------------------------------------
// Lifecycle state
// ---------------------------------------------------------------------------

export type LifecycleState =
  | "runnable"
  | "runnable_disabled"
  | "portal_reference"
  | "adapter_missing"
  | "blocked_secret"
  | "disabled_stub"
  | "deprecated"
  | "manual_reference";

export const LIFECYCLE_STATE_LABELS: Record<LifecycleState, string> = {
  runnable: "Runnable",
  runnable_disabled: "Disabled (Runnable)",
  portal_reference: "Portal Reference",
  adapter_missing: "Adapter Missing",
  blocked_secret: "Blocked — Secret Required",
  disabled_stub: "Disabled Stub",
  deprecated: "Deprecated",
  manual_reference: "Manual Reference",
};

export const LIFECYCLE_STATE_COLOURS: Record<LifecycleState, string> = {
  runnable: "bg-green-100 text-green-800",
  runnable_disabled: "bg-yellow-100 text-yellow-800",
  portal_reference: "bg-amber-100 text-amber-800",
  adapter_missing: "bg-orange-100 text-orange-800",
  blocked_secret: "bg-red-100 text-red-700",
  disabled_stub: "bg-slate-100 text-slate-600",
  deprecated: "bg-rose-100 text-rose-800",
  manual_reference: "bg-gray-100 text-gray-600",
};

/** Human-readable label for a lifecycle_state value. */
export function lifecycleStateLabel(ls: string | null): string {
  if (!ls) return "Unknown";
  return LIFECYCLE_STATE_LABELS[ls as LifecycleState] ?? ls.replace(/_/g, " ");
}

/** Tailwind colour string for a lifecycle_state value. */
export function lifecycleStateColour(ls: string | null): string {
  if (!ls) return "bg-gray-100 text-gray-500";
  return LIFECYCLE_STATE_COLOURS[ls as LifecycleState] ?? "bg-gray-100 text-gray-500";
}

/** Human-readable label for a source_class value, falling back to the raw value. */
export function sourceClassLabel(sc: string | null): string {
  if (!sc) return "Unclassified";
  return SOURCE_CLASS_LABELS[sc as SourceClass] ?? sc.replace(/_/g, " ");
}

/** Tailwind colour string for a source_class value, falling back to disabled_stub colours. */
export function sourceClassColour(sc: string | null): string {
  if (!sc) return "bg-gray-100 text-gray-500";
  return SOURCE_CLASS_COLOURS[sc as SourceClass] ?? "bg-gray-100 text-gray-500";
}
