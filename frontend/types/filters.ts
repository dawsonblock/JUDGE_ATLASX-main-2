/**
 * Filter state types and constants for map and search interface.
 */

export interface MapFilterState {
  // Category filter
  category?: string[];

  // Jurisdiction Filter
  jurisdiction?: string[];

  // Date Range Filter
  dateRange?: {
    startDate?: string; // ISO 8601: YYYY-MM-DD
    endDate?: string;
  };

  // Existing filters
  sourceKey?: string;
  incidentStatus?: string;
  searchText?: string;
}

/**
 * Available Canadian jurisdictions
 * Used in jurisdiction filter dropdown
 */
export const JURISDICTIONS = [
  { code: "ON", label: "Ontario" },
  { code: "QC", label: "Quebec" },
  { code: "BC", label: "British Columbia" },
  { code: "AB", label: "Alberta" },
  { code: "MB", label: "Manitoba" },
  { code: "SK", label: "Saskatchewan" },
  { code: "NS", label: "Nova Scotia" },
  { code: "NB", label: "New Brunswick" },
  { code: "PE", label: "Prince Edward Island" },
  { code: "NL", label: "Newfoundland and Labrador" },
  { code: "YT", label: "Yukon" },
  { code: "NT", label: "Northwest Territories" },
  { code: "NU", label: "Nunavut" },
];

/**
 * Incident categories
 * Used in category filter
 */
export const CATEGORIES = [
  { code: "court_decision", label: "Court Decision" },
  { code: "criminal", label: "Criminal" },
  { code: "civil", label: "Civil" },
  { code: "administrative", label: "Administrative" },
];
