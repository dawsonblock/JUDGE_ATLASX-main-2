/**
 * Map Filters Component
 * Provides jurisdiction, date range, and category filtering for map view.
 */

import React, { useState, useCallback } from "react";
import { MapFilterState, JURISDICTIONS, CATEGORIES } from "@/types/filters";

interface MapFiltersProps {
  onFilterChange: (filters: MapFilterState) => void;
  initialFilters?: MapFilterState;
}

export const MapFilters: React.FC<MapFiltersProps> = ({
  onFilterChange,
  initialFilters = {},
}) => {
  const [selectedJurisdictions, setSelectedJurisdictions] = useState<string[]>(
    initialFilters.jurisdiction || []
  );
  const [selectedCategories, setSelectedCategories] = useState<string[]>(
    initialFilters.category || []
  );
  const [dateRange, setDateRange] = useState({
    startDate: initialFilters.dateRange?.startDate || "",
    endDate: initialFilters.dateRange?.endDate || "",
  });

  const handleJurisdictionChange = useCallback(
    (code: string, checked: boolean) => {
      const updated = checked
        ? [...selectedJurisdictions, code]
        : selectedJurisdictions.filter((c) => c !== code);
      setSelectedJurisdictions(updated);
      onFilterChange({
        ...initialFilters,
        jurisdiction: updated,
      });
    },
    [selectedJurisdictions, initialFilters, onFilterChange]
  );

  const handleCategoryChange = useCallback(
    (code: string, checked: boolean) => {
      const updated = checked
        ? [...selectedCategories, code]
        : selectedCategories.filter((c) => c !== code);
      setSelectedCategories(updated);
      onFilterChange({
        ...initialFilters,
        category: updated,
      });
    },
    [selectedCategories, initialFilters, onFilterChange]
  );

  const handleDateChange = useCallback(
    (field: "startDate" | "endDate", value: string) => {
      const updated = { ...dateRange, [field]: value };
      setDateRange(updated);
      onFilterChange({
        ...initialFilters,
        dateRange: updated,
      });
    },
    [dateRange, initialFilters, onFilterChange]
  );

  return (
    <div className="bg-white rounded-lg shadow p-4 space-y-4">
      {/* Jurisdiction Filter */}
      <div className="border-b pb-4">
        <h3 className="text-sm font-semibold text-gray-900 mb-3">
          Jurisdiction
        </h3>
        <div className="grid grid-cols-2 gap-2 max-h-48 overflow-y-auto">
          {JURISDICTIONS.map((jurisdiction) => (
            <label
              key={jurisdiction.code}
              className="flex items-center space-x-2 cursor-pointer"
            >
              <input
                type="checkbox"
                checked={selectedJurisdictions.includes(jurisdiction.code)}
                onChange={(e) =>
                  handleJurisdictionChange(jurisdiction.code, e.target.checked)
                }
                className="w-4 h-4 text-blue-600 rounded"
              />
              <span className="text-sm text-gray-700">
                {jurisdiction.label}
              </span>
            </label>
          ))}
        </div>
      </div>

      {/* Date Range Filter */}
      <div className="border-b pb-4">
        <h3 className="text-sm font-semibold text-gray-900 mb-3">
          Date Range
        </h3>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="block text-xs text-gray-600 mb-1">
              Start Date
            </label>
            <input
              type="date"
              value={dateRange.startDate}
              onChange={(e) => handleDateChange("startDate", e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-600 mb-1">
              End Date
            </label>
            <input
              type="date"
              value={dateRange.endDate}
              onChange={(e) => handleDateChange("endDate", e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        </div>
      </div>

      {/* Category Filter */}
      <div>
        <h3 className="text-sm font-semibold text-gray-900 mb-3">Category</h3>
        <div className="grid grid-cols-1 gap-2 max-h-40 overflow-y-auto">
          {CATEGORIES.map((category) => (
            <label
              key={category.code}
              className="flex items-center space-x-2 cursor-pointer"
            >
              <input
                type="checkbox"
                checked={selectedCategories.includes(category.code)}
                onChange={(e) =>
                  handleCategoryChange(category.code, e.target.checked)
                }
                className="w-4 h-4 text-blue-600 rounded"
              />
              <span className="text-sm text-gray-700">{category.label}</span>
            </label>
          ))}
        </div>
      </div>

      {/* Clear Filters Button */}
      <div className="pt-2 border-t">
        <button
          onClick={() => {
            setSelectedJurisdictions([]);
            setSelectedCategories([]);
            setDateRange({ startDate: "", endDate: "" });
            onFilterChange({});
          }}
          className="w-full px-3 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded hover:bg-gray-200 transition"
        >
          Clear All Filters
        </button>
      </div>
    </div>
  );
};

export default MapFilters;
