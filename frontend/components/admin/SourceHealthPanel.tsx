/**
 * Source health panel for monitoring data source health and status.
 *
 * This component displays health metrics for various data sources including
 * fetch success rates, error counts, last fetch time, and overall health status.
 */
"use client";

import { useEffect, useState } from "react";

interface SourceHealth {
  source_key: string;
  source_name: string;
  source_type: string;
  health_status: "healthy" | "degraded" | "unhealthy" | "unknown";
  last_fetch_at: string | null;
  last_fetch_success: boolean;
  fetch_count_24h: number;
  error_count_24h: number;
  success_rate_24h: number;
  created_events_count: number;
  created_claims_count: number;
}

export default function SourceHealthPanel() {
  const [sources, setSources] = useState<SourceHealth[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchSourceHealth();
    const interval = setInterval(fetchSourceHealth, 60000); // Refresh every minute
    return () => clearInterval(interval);
  }, []);

  const fetchSourceHealth = async () => {
    try {
      const response = await fetch("/api/admin/sources/health");
      if (!response.ok) {
        throw new Error("Failed to fetch source health");
      }
      const data = await response.json();
      setSources(data.sources || []);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  const getHealthColor = (status: string) => {
    switch (status) {
      case "healthy":
        return "bg-green-500";
      case "degraded":
        return "bg-yellow-500";
      case "unhealthy":
        return "bg-red-500";
      default:
        return "bg-gray-500";
    }
  };

  const getHealthBadge = (status: string) => {
    switch (status) {
      case "healthy":
        return "bg-green-100 text-green-800";
      case "degraded":
        return "bg-yellow-100 text-yellow-800";
      case "unhealthy":
        return "bg-red-100 text-red-800";
      default:
        return "bg-gray-100 text-gray-800";
    }
  };

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow-lg p-6">
        <h2 className="text-lg font-semibold text-gray-700 mb-4">
          Source Health
        </h2>
        <div className="text-center text-gray-500 py-8">Loading...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white rounded-lg shadow-lg p-6">
        <h2 className="text-lg font-semibold text-gray-700 mb-4">
          Source Health
        </h2>
        <div className="text-center text-red-500 py-8">{error}</div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow-lg p-6">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-lg font-semibold text-gray-700">
          Source Health
        </h2>
        <button
          onClick={fetchSourceHealth}
          className="px-3 py-1 text-sm bg-blue-500 text-white rounded hover:bg-blue-600"
        >
          Refresh
        </button>
      </div>

      {sources.length === 0 ? (
        <div className="text-center text-gray-500 py-8">
          No sources found
        </div>
      ) : (
        <div className="space-y-4">
          {sources.map((source) => (
            <div
              key={source.source_key}
              className="border rounded-lg p-4 hover:bg-gray-50"
            >
              <div className="flex justify-between items-start mb-2">
                <div>
                  <h3 className="font-medium text-gray-800">
                    {source.source_name}
                  </h3>
                  <p className="text-sm text-gray-500">{source.source_key}</p>
                </div>
                <span
                  className={`px-2 py-1 text-xs rounded ${getHealthBadge(
                    source.health_status
                  )}`}
                >
                  {source.health_status}
                </span>
              </div>

              <div className="grid grid-cols-2 gap-4 mt-3 text-sm">
                <div>
                  <span className="text-gray-500">Type:</span>
                  <span className="ml-2 text-gray-700">{source.source_type}</span>
                </div>
                <div>
                  <span className="text-gray-500">Last Fetch:</span>
                  <span className="ml-2 text-gray-700">
                    {source.last_fetch_at
                      ? new Date(source.last_fetch_at).toLocaleString()
                      : "Never"}
                  </span>
                </div>
                <div>
                  <span className="text-gray-500">Fetches (24h):</span>
                  <span className="ml-2 text-gray-700">
                    {source.fetch_count_24h}
                  </span>
                </div>
                <div>
                  <span className="text-gray-500">Errors (24h):</span>
                  <span className="ml-2 text-gray-700">
                    {source.error_count_24h}
                  </span>
                </div>
                <div>
                  <span className="text-gray-500">Success Rate:</span>
                  <span className="ml-2 text-gray-700">
                    {source.success_rate_24h.toFixed(1)}%
                  </span>
                </div>
                <div>
                  <span className="text-gray-500">Events Created:</span>
                  <span className="ml-2 text-gray-700">
                    {source.created_events_count}
                  </span>
                </div>
                <div>
                  <span className="text-gray-500">Claims Created:</span>
                  <span className="ml-2 text-gray-700">
                    {source.created_claims_count}
                  </span>
                </div>
                <div>
                  <span className="text-gray-500">Last Status:</span>
                  <span
                    className={`ml-2 ${
                      source.last_fetch_success
                        ? "text-green-600"
                        : "text-red-600"
                    }`}
                  >
                    {source.last_fetch_success ? "Success" : "Failed"}
                  </span>
                </div>
              </div>

              {/* Success rate bar */}
              <div className="mt-3">
                <div className="w-full bg-gray-200 rounded-full h-2">
                  <div
                    className={`h-2 rounded-full ${getHealthColor(
                      source.health_status
                    )}`}
                    style={{ width: `${source.success_rate_24h}%` }}
                  ></div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
