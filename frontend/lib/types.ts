// Core status types
export type LegalStatus =
  | "reported"
  | "alleged"
  | "charged"
  | "before_court"
  | "convicted"
  | "dismissed"
  | "withdrawn"
  | "acquitted"
  | "unknown";

export type SourceConfidence =
  | "high"
  | "medium"
  | "low"
  | "pending"
  | "conflicting"
  | "unverified";

export type LocationPrecision =
  | "exact"
  | "block"
  | "neighbourhood"
  | "city"
  | "region";

export type EvidenceType =
  | "court_record"
  | "news_report"
  | "government_document"
  | "witness_statement"
  | "police_report"
  | "academic"
  | "ngo_report"
  | "other";

export type IncidentCategory =
  | "corruption"
  | "misconduct"
  | "fraud"
  | "assault"
  | "homicide"
  | "property"
  | "drug"
  | "organized_crime"
  | "other";

// Legacy labels retained for backward compatibility in stored data,
// but excluded from public creation/filter surfaces.
export type LegacyIncidentCategory = "corruption" | "misconduct";
export type PublicIncidentCategory = Exclude<IncidentCategory, LegacyIncidentCategory>;

// Core data models
export interface CrimeIncident {
  id: string;
  title: string;
  summary: string;
  category: IncidentCategory;
  status: LegalStatus;
  confidence: SourceConfidence;
  date: string; // ISO date string
  location: {
    lat: number;
    lng: number;
    precision: LocationPrecision;
    address?: string;
    city: string;
    province: string;
    country: string;
  };
  sourceCount: number;
  evidenceCount: number;
  linkedCases: string[]; // case IDs
  linkedJudges: string[]; // judge IDs
  linkedDefendants: string[];
  tags: string[];
  sensitive: boolean;
}

export interface EvidenceSource {
  id: string;
  name: string;
  url?: string;
  type: EvidenceType;
  confidence: SourceConfidence;
  publishedAt?: string;
  summary?: string;
  verified: boolean;
  claims: string[];
}

export interface CourtCase {
  id: string;
  caseNumber: string;
  title: string;
  status: LegalStatus;
  court: string;
  jurisdiction: string;
  filedAt?: string;
  resolvedAt?: string;
  charges: string[];
  outcome?: string;
  linkedJudges: string[];
  linkedDefendants: string[];
  linkedIncidents: string[];
  evidenceSources: EvidenceSource[];
}

export interface JudgeProfile {
  id: string;
  name: string;
  court: string;
  jurisdiction: string;
  appointedAt?: string;
  status: "active" | "retired" | "suspended" | "removed";
  linkedCases: string[];
  allegedMisconductCount: number;
  sourceCount: number;
  notes?: string;
}

export interface AdminReviewItem {
  id: string;
  type: "incident" | "source" | "case" | "correction";
  title: string;
  submittedAt: string;
  submittedBy?: string;
  status: "pending" | "approved" | "rejected" | "needs_info";
  priority: "low" | "medium" | "high";
  notes?: string;
  entityId?: string;
}

export interface MapFilterState {
  search: string;
  category: PublicIncidentCategory | "";
  status: LegalStatus | "";
  confidence: SourceConfidence | "";
  province: string;
  dateFrom?: string;
  dateTo?: string;
  courtLinkedOnly: boolean;
  verifiedOnly: boolean;
  hideSensitive: boolean;
}
