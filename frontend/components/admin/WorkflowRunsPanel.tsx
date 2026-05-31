/**
 * Admin Workflow Runs Panel component.
 *
 * This component displays workflow run information for administrators,
 * including status, step progress, error messages, artifact counts, and
 * action buttons for managing workflow runs.
 */

"use client";

import { useState, useEffect, useCallback } from "react";
import { format } from "date-fns";

interface WorkflowRun {
  id: number;
  run_id: string;
  workflow_name: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  workspace_path: string | null;
  source_key: string | null;
  created_at: string;
  updated_at: string;
}

interface WorkflowStep {
  id: number;
  step_id: string;
  run_id: number;
  step_name: string;
  step_type: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  output: any;
  retry_count: number;
}

interface WorkflowRunsPanelProps {
  workflowName?: string;
  onRunNow?: (workflowName: string) => void;
  onPause?: (runId: string) => void;
  onResume?: (runId: string) => void;
  onRetryFailedStep?: (runId: string, stepId: string) => void;
  onOpenArtifacts?: (runId: string) => void;
  onOpenLogs?: (runId: string) => void;
  onOpenReviewQueue?: (runId: string) => void;
}

interface AdminCapabilities {
  workflow_admin?: boolean;
}

export function WorkflowRunsPanel({
  workflowName,
  onRunNow,
  onPause,
  onResume,
  onRetryFailedStep,
  onOpenArtifacts,
  onOpenLogs,
  onOpenReviewQueue,
}: WorkflowRunsPanelProps) {
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<WorkflowRun | null>(null);
  const [steps, setSteps] = useState<WorkflowStep[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [workflowEnabled, setWorkflowEnabled] = useState<boolean | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/admin/capabilities", {
      signal: controller.signal,
      cache: "no-store",
    })
      .then((res) => {
        if (!res.ok) throw new Error(`Capabilities request failed (${res.status})`);
        return res.json() as Promise<AdminCapabilities>;
      })
      .then((data) => {
        setWorkflowEnabled(data.workflow_admin === true);
      })
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setWorkflowEnabled(false);
        setError(
          err instanceof Error
            ? err.message
            : "Failed to load admin capabilities",
        );
      });
    return () => controller.abort();
  }, []);

  const fetchRuns = useCallback(async () => {
    if (workflowEnabled !== true) {
      setRuns([]);
      setSelectedRun(null);
      setSteps([]);
      return;
    }
    setIsLoading(true);
    setError(null);

    try {
      const url = workflowName
        ? `/api/admin/workflows/runs?workflow_name=${workflowName}`
        : "/api/admin/workflows/runs";

      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      setRuns(data.runs || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setIsLoading(false);
    }
  }, [workflowName, workflowEnabled]);

  useEffect(() => {
    fetchRuns();
  }, [fetchRuns]);

  const fetchSteps = async (runId: string) => {
    try {
      const response = await fetch(`/api/admin/workflows/runs/${runId}/steps`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      setSteps(data.steps || []);
    } catch (err) {
      console.error("Failed to fetch steps:", err);
    }
  };

  const handleRunClick = (run: WorkflowRun) => {
    setSelectedRun(run);
    fetchSteps(run.run_id);
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "success":
        return "bg-green-100 text-green-800";
      case "failed":
        return "bg-red-100 text-red-800";
      case "running":
        return "bg-blue-100 text-blue-800";
      case "pending":
        return "bg-gray-100 text-gray-800";
      case "cancelled":
        return "bg-yellow-100 text-yellow-800";
      default:
        return "bg-gray-100 text-gray-800";
    }
  };

  const getStepStatusColor = (status: string) => {
    switch (status) {
      case "success":
        return "text-green-600";
      case "failed":
        return "text-red-600";
      case "running":
        return "text-blue-600";
      case "pending":
        return "text-gray-600";
      case "skipped":
        return "text-yellow-600";
      case "blocked":
        return "text-orange-600";
      default:
        return "text-gray-600";
    }
  };

  return (
    <div className="flex flex-col h-full bg-white border-r border-gray-200">
      {workflowEnabled === false && (
        <div className="m-4 rounded border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          Workflow admin is disabled for this environment.
        </div>
      )}
      {/* Header */}
      <div className="p-4 border-b border-gray-200">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold">Workflow Runs</h2>
          {workflowName && workflowEnabled === true && (
            <button
              onClick={() => onRunNow?.(workflowName)}
              className="px-3 py-1 text-sm bg-blue-500 text-white rounded hover:bg-blue-600"
            >
              Run Now
            </button>
          )}
        </div>
        <button
          onClick={fetchRuns}
          disabled={isLoading || workflowEnabled !== true}
          className="px-3 py-1 text-sm bg-gray-200 text-gray-700 rounded hover:bg-gray-300 disabled:opacity-50"
        >
          {isLoading ? "Loading..." : "Refresh"}
        </button>
      </div>

      {/* Error state */}
      {error && (
        <div className="p-4 bg-red-50 border-b border-red-200">
          <p className="text-sm text-red-600">Error: {error}</p>
        </div>
      )}

      {/* Content */}
      <div className="flex flex-1 overflow-hidden">
        {/* Runs list */}
        <div className="flex-1 overflow-y-auto border-r border-gray-200">
          {workflowEnabled !== true ? (
            <div className="p-8 text-center text-gray-500">
              <p>Workflow admin disabled</p>
            </div>
          ) : runs.length === 0 ? (
            <div className="p-8 text-center text-gray-500">
              <p>No workflow runs found</p>
            </div>
          ) : (
            <div className="divide-y divide-gray-100">
              {runs.map((run) => (
                <div
                  key={run.id}
                  className={`p-3 hover:bg-gray-50 cursor-pointer ${
                    selectedRun?.id === run.id ? "bg-blue-50" : ""
                  }`}
                  onClick={() => handleRunClick(run)}
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex-1">
                      <div className="text-sm font-medium">{run.workflow_name}</div>
                      <div className="text-xs text-gray-500">{run.run_id}</div>
                    </div>
                    <span
                      className={`px-2 py-0.5 text-xs rounded ${getStatusColor(
                        run.status
                      )}`}
                    >
                      {run.status}
                    </span>
                  </div>
                  <div className="text-xs text-gray-600">
                    {run.started_at && (
                      <span>
                        Started: {format(new Date(run.started_at), "MMM d, HH:mm")}
                      </span>
                    )}
                    {run.completed_at && (
                      <span className="ml-2">
                        Completed: {format(new Date(run.completed_at), "HH:mm")}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Run details */}
        {selectedRun && (
          <div className="flex-1 overflow-y-auto">
            <div className="p-4 border-b border-gray-200">
              <h3 className="text-sm font-semibold mb-2">Run Details</h3>
              <div className="space-y-1 text-xs">
                <div>
                  <span className="text-gray-600">Run ID:</span>{" "}
                  {selectedRun.run_id}
                </div>
                <div>
                  <span className="text-gray-600">Workflow:</span>{" "}
                  {selectedRun.workflow_name}
                </div>
                <div>
                  <span className="text-gray-600">Source:</span>{" "}
                  {selectedRun.source_key || "N/A"}
                </div>
                <div>
                  <span className="text-gray-600">Status:</span>{" "}
                  <span
                    className={`px-1.5 py-0.5 rounded ${getStatusColor(
                      selectedRun.status
                    )}`}
                  >
                    {selectedRun.status}
                  </span>
                </div>
                {selectedRun.started_at && (
                  <div>
                    <span className="text-gray-600">Started:</span>{" "}
                    {format(new Date(selectedRun.started_at), "MMM d, HH:mm:ss")}
                  </div>
                )}
                {selectedRun.completed_at && (
                  <div>
                    <span className="text-gray-600">Completed:</span>{" "}
                    {format(new Date(selectedRun.completed_at), "HH:mm:ss")}
                  </div>
                )}
                {selectedRun.error_message && (
                  <div>
                    <span className="text-gray-600">Error:</span>{" "}
                    <span className="text-red-600">{selectedRun.error_message}</span>
                  </div>
                )}
              </div>

              {/* Actions */}
              <div className="flex gap-2 mt-4">
                {selectedRun.status === "running" && (
                  <button
                    onClick={() => onPause?.(selectedRun.run_id)}
                    className="px-2 py-1 text-xs bg-yellow-500 text-white rounded hover:bg-yellow-600"
                  >
                    Pause
                  </button>
                )}
                {selectedRun.status === "pending" && (
                  <button
                    onClick={() => onResume?.(selectedRun.run_id)}
                    className="px-2 py-1 text-xs bg-green-500 text-white rounded hover:bg-green-600"
                  >
                    Resume
                  </button>
                )}
                <button
                  onClick={() => onOpenArtifacts?.(selectedRun.run_id)}
                  className="px-2 py-1 text-xs bg-blue-500 text-white rounded hover:bg-blue-600"
                >
                  Open Artifacts
                </button>
                <button
                  onClick={() => onOpenLogs?.(selectedRun.run_id)}
                  className="px-2 py-1 text-xs bg-gray-500 text-white rounded hover:bg-gray-600"
                >
                  Open Logs
                </button>
                <button
                  onClick={() => onOpenReviewQueue?.(selectedRun.run_id)}
                  className="px-2 py-1 text-xs bg-purple-500 text-white rounded hover:bg-purple-600"
                >
                  Open Review Queue
                </button>
              </div>
            </div>

            {/* Steps */}
            <div className="p-4 border-b border-gray-200">
              <h3 className="text-sm font-semibold mb-2">Step Progress</h3>
              {steps.length === 0 ? (
                <p className="text-xs text-gray-500">No steps found</p>
              ) : (
                <div className="space-y-2">
                  {steps.map((step) => (
                    <div
                      key={step.id}
                      className="p-2 border border-gray-200 rounded"
                    >
                      <div className="flex items-center justify-between mb-1">
                        <div className="text-xs font-medium">{step.step_name}</div>
                        <span
                          className={`text-xs ${getStepStatusColor(step.status)}`}
                        >
                          {step.status}
                        </span>
                      </div>
                      <div className="text-xs text-gray-600">
                        <span className="text-gray-500">Type:</span> {step.step_type}
                      </div>
                      {step.retry_count > 0 && (
                        <div className="text-xs text-yellow-600">
                          Retries: {step.retry_count}
                        </div>
                      )}
                      {step.error_message && (
                        <div className="text-xs text-red-600 mt-1">
                          Error: {step.error_message}
                        </div>
                      )}
                      {step.status === "failed" && (
                        <button
                          onClick={() =>
                            onRetryFailedStep?.(selectedRun.run_id, step.step_id)
                          }
                          className="mt-2 px-2 py-1 text-xs bg-orange-500 text-white rounded hover:bg-orange-600"
                        >
                          Retry Step
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
