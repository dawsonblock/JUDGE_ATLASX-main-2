"use client";

import React, { useState } from "react";
import { SectionCard } from "@/components/shared/SectionCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  ExternalLink,
  CheckCircle,
  XCircle,
  Clock,
  Lock,
  ShieldCheck,
  Play,
  Loader2,
  RefreshCw,
  FlaskConical,
} from "lucide-react";
import { AdminSourceItem, SourceDryRunResult, SourceRunResult } from "@/lib/api";
import { authorityColour, sourceClassLabel, sourceClassColour, lifecycleStateLabel, lifecycleStateColour } from "@/lib/sourceContracts";

function AuthorityBadge({ authority }: { authority: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${authorityColour(authority)}`}
    >
      <ShieldCheck className="h-3 w-3" />
      {authority.replace(/_/g, " ")}
    </span>
  );
}

export function SourceControlCard({
  source: initialSource,
}: {
  source: AdminSourceItem;
}) {
  const [source, setSource] = useState<AdminSourceItem>(initialSource);
  const [toggleLoading, setToggleLoading] = useState(false);
  const [runLoading, setRunLoading] = useState(false);
  const [dryRunLoading, setDryRunLoading] = useState(false);
  const [retryLoading, setRetryLoading] = useState(false);
  const [runResult, setRunResult] = useState<SourceRunResult | null>(null);
  const [dryRunResult, setDryRunResult] = useState<SourceDryRunResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [csrfToken, setCsrfToken] = useState<string | null>(null);

  async function getCsrfToken(): Promise<string> {
    if (csrfToken) {
      return csrfToken;
    }
    const resp = await fetch("/api/admin/csrf", {
      method: "GET",
      cache: "no-store",
    });
    const data = await resp.json();
    const token = data?.csrf_token;
    if (!resp.ok || typeof token !== "string" || token.length < 16) {
      throw new Error("Failed to acquire CSRF token for admin mutation");
    }
    setCsrfToken(token);
    return token;
  }

  async function adminPost(path: string): Promise<Response> {
    const token = await getCsrfToken();
    return fetch(path, {
      method: "POST",
      headers: { "x-jta-csrf-token": token },
    });
  }

  const creates: string[] = (() => {
    if (!source.creates) return [];
    try {
      const parsed = JSON.parse(source.creates);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  })();
  const location = [source.city, source.province_state, source.country]
    .filter(Boolean)
    .join(", ");
  const canRun = source.runnable_now;
  const enableBlockers = source.enable_blockers ?? [];
  const canEnable = source.enable_ready ?? (canRun && enableBlockers.length === 0);

  async function handleToggle() {
    setToggleLoading(true);
    setError(null);
    try {
      const action = source.is_active ? "disable" : "enable";
      const resp = await adminPost(
        `/api/admin/sources/${source.source_key}/${action}`,
      );
      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(
          data?.detail || data?.error || `${action} failed: ${resp.status}`,
        );
      }
      setSource(data as AdminSourceItem);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Toggle failed");
    } finally {
      setToggleLoading(false);
    }
  }

  async function handleRun() {
    setRunLoading(true);
    setError(null);
    setRunResult(null);
    try {
      const resp = await adminPost(`/api/admin/sources/${source.source_key}/run`);
      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(
          data?.detail || data?.error || `Run failed: ${resp.status}`,
        );
      }
      setRunResult(data as SourceRunResult);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Run failed");
    } finally {
      setRunLoading(false);
    }
  }

  async function handleDryRun() {
    setDryRunLoading(true);
    setError(null);
    setDryRunResult(null);
    try {
      const resp = await adminPost(`/api/admin/sources/${source.source_key}/dry-run`);
      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(
          data?.detail || data?.error || `Dry-run failed: ${resp.status}`,
        );
      }
      setDryRunResult(data as SourceDryRunResult);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Dry-run failed");
    } finally {
      setDryRunLoading(false);
    }
  }

  async function handleRetry() {
    if (!runResult?.run_id) return;
    setRetryLoading(true);
    setError(null);
    try {
      const resp = await adminPost(
        `/api/admin/ingestion-runs/${runResult.run_id}/retry`,
      );
      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(
          data?.detail || data?.error || `Retry failed: ${resp.status}`,
        );
      }
      setRunResult(data as SourceRunResult);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Retry failed");
    } finally {
      setRetryLoading(false);
    }
  }

  return (
    <SectionCard title={source.source_name}>
      <div className="space-y-3 text-sm">
        {/* Status row */}
        <div className="flex items-center gap-2 flex-wrap">
          {source.is_active ? (
            <span className="flex items-center gap-1 text-green-700 font-medium">
              <CheckCircle className="h-3.5 w-3.5" /> Active
            </span>
          ) : (
            <span className="flex items-center gap-1 text-gray-400">
              <XCircle className="h-3.5 w-3.5" /> Disabled
            </span>
          )}
          <Badge variant="outline" className="text-xs">
            {source.source_type}
          </Badge>
          {source.category && (
            <Badge variant="secondary" className="text-xs">
              {source.category}
            </Badge>
          )}
          {source.source_class && (
            <span
              className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${sourceClassColour(source.source_class)}`}
            >
              {sourceClassLabel(source.source_class)}
            </span>
          )}
          {source.lifecycle_state && (
            <span
              className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${lifecycleStateColour(source.lifecycle_state)}`}
            >
              {lifecycleStateLabel(source.lifecycle_state)}
            </span>
          )}
          {source.automation_status && (
            <Badge variant="outline" className="text-xs">
              {source.automation_status.replace(/_/g, " ")}
            </Badge>
          )}
        </div>

        {/* Authority */}
        <AuthorityBadge authority={source.public_record_authority} />

        {/* Location / jurisdiction */}
        {location && (
          <p className="text-xs text-muted-foreground">{location}</p>
        )}
        {source.jurisdiction && (
          <p className="text-xs text-muted-foreground">
            Jurisdiction: {source.jurisdiction}
          </p>
        )}

        {/* Creates */}
        {creates.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {creates.map((t) => (
              <Badge key={t} variant="outline" className="text-xs">
                {t}
              </Badge>
            ))}
          </div>
        )}

        {/* Parser / priority */}
        <div className="flex gap-3 text-xs text-muted-foreground">
          {source.parser && (
            <span>
              Parser: <code className="font-mono">{source.parser}</code>
            </span>
          )}
          {source.parser_version && <span>Parser version: {source.parser_version}</span>}
          <span>Priority: {source.priority}</span>
        </div>

        {/* Review gate notice */}
        {source.requires_manual_review && (
          <p className="text-xs text-amber-700 font-medium">
            Requires manual review before publish
          </p>
        )}

        {!source.is_active && enableBlockers.length > 0 && (
          <div className="rounded border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
            <p className="font-medium">Cannot enable yet:</p>
            <ul className="mt-1 list-disc space-y-0.5 pl-4">
              {enableBlockers.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Last fetched / health */}
        <div className="flex items-center gap-1 text-xs text-muted-foreground">
          <Clock className="h-3 w-3" />
          {source.last_ingested_at
            ? `Last ingested: ${new Date(
                source.last_ingested_at,
              ).toLocaleDateString()}`
            : "Never ingested"}
          {" · "}
          Health: {Math.round(source.health_score * 100)}%
        </div>

        {/* Links */}
        <div className="flex gap-3 pt-1 flex-wrap">
          {source.base_url && (
            <a
              href={source.base_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-xs text-blue-600 hover:underline"
            >
              Source <ExternalLink className="h-3 w-3" />
            </a>
          )}
          {source.terms_url && (
            <a
              href={source.terms_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-xs text-blue-600 hover:underline"
            >
              Terms <ExternalLink className="h-3 w-3" />
            </a>
          )}
        </div>

        {/* Admin notes */}
        {source.admin_notes && (
          <p className="text-xs text-muted-foreground italic">
            {source.admin_notes}
          </p>
        )}

        {/* Controls */}
        <div className="flex gap-2 pt-1 flex-wrap">
          <Button
            size="sm"
            variant="outline"
            disabled={dryRunLoading}
            onClick={handleDryRun}
            className="h-7 text-xs"
          >
            {dryRunLoading ? (
              <Loader2 className="h-3 w-3 animate-spin mr-1" />
            ) : (
              <FlaskConical className="h-3 w-3 mr-1" />
            )}
            Dry Run
          </Button>

          <Button
            size="sm"
            variant={source.is_active ? "outline" : "default"}
            disabled={toggleLoading || (!source.is_active && !canEnable)}
            title={
              !source.is_active && !canEnable
                ? enableBlockers.join("; ") || "Source is not enable-ready."
                : undefined
            }
            onClick={handleToggle}
            className="h-7 text-xs"
          >
            {toggleLoading ? (
              <Loader2 className="h-3 w-3 animate-spin mr-1" />
            ) : source.is_active ? (
              <XCircle className="h-3 w-3 mr-1" />
            ) : (
              <CheckCircle className="h-3 w-3 mr-1" />
            )}
            {source.is_active ? "Disable" : "Enable"}
          </Button>

          {source.is_active && canRun && (
            <Button
              size="sm"
              variant="secondary"
              disabled={runLoading}
              onClick={handleRun}
              className="h-7 text-xs"
            >
              {runLoading ? (
                <Loader2 className="h-3 w-3 animate-spin mr-1" />
              ) : (
                <Play className="h-3 w-3 mr-1" />
              )}
              Run Now
            </Button>
          )}
        </div>

        {/* Deprecated source warning */}
        {source.lifecycle_state === "deprecated" && (
          <div className="rounded border border-rose-200 bg-rose-50 px-2 py-1 text-xs text-rose-800">
            <strong>Deprecated.</strong>{" "}
            {source.canonical_replacement_key
              ? <>
                  Replaced by: <code className="font-mono">{source.canonical_replacement_key}</code>.
                </>
              : "This source has been superseded."}
            {source.status_reason && <span> {source.status_reason}</span>}
          </div>
        )}

        {/* Status reason */}
        {source.status_reason && source.lifecycle_state !== "deprecated" && (
          <p className="text-xs text-muted-foreground italic">{source.status_reason}</p>
        )}

        {/* Operator next step */}
        {source.operator_next_step && (
          <p className="text-xs text-muted-foreground">
            <strong>Next step:</strong> {source.operator_next_step}
          </p>
        )}

        {/* Lock notice for non-runnable sources */}
        {!canRun && source.source_class && source.lifecycle_state !== "deprecated" && (
          <p className="flex items-center gap-1 text-xs text-muted-foreground">
            <Lock className="h-3 w-3" />
            {sourceClassLabel(source.source_class)} — not eligible for automated
            ingestion.
          </p>
        )}

        {/* Run result */}
        {runResult && (
          <div
            className={`rounded p-2 text-xs ${
              runResult.success
                ? "bg-green-50 text-green-800"
                : "bg-red-50 text-red-800"
            }`}
          >
            {runResult.success ? "✓ Run completed" : "✗ Run failed"} ·{" "}
            {runResult.adapter_records ?? runResult.records_fetched} fetched ·{" "}
            {runResult.created_records} created ·{" "}
            {runResult.duplicates_skipped ?? runResult.records_skipped} skipped
            {runResult.errors.length > 0 && (
              <ul className="mt-1 space-y-0.5 list-disc pl-4">
                {runResult.errors.map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            )}
            {canRun && (
              <Button
                size="sm"
                variant="outline"
                disabled={retryLoading}
                onClick={handleRetry}
                className="mt-2 h-7 text-xs"
              >
                {retryLoading ? (
                  <Loader2 className="h-3 w-3 animate-spin mr-1" />
                ) : (
                  <RefreshCw className="h-3 w-3 mr-1" />
                )}
                Retry
              </Button>
            )}
          </div>
        )}

        {dryRunResult && (
          <div
            className={`rounded p-2 text-xs ${
              dryRunResult.success
                ? "bg-sky-50 text-sky-900"
                : "bg-amber-50 text-amber-900"
            }`}
          >
            <p className="font-medium">
              Dry-run {dryRunResult.success ? "passed" : "reported issues"}
            </p>
            <p>
              Reachable: {dryRunResult.source_reachable ? "yes" : "no"} · Sample: {dryRunResult.sample_records_found} · Parsed: {dryRunResult.parser_matched_records}
            </p>
            <p>
              Legal note: {dryRunResult.legal_note_present ? "present" : "missing"} · Snapshot: {dryRunResult.evidence_snapshot_would_be_created ? "yes" : "no"} · Claims: {dryRunResult.claims_would_be_extracted ? "yes" : "no"}
            </p>
            {dryRunResult.warnings.length > 0 && (
              <ul className="mt-1 space-y-0.5 list-disc pl-4">
                {dryRunResult.warnings.map((warning, i) => (
                  <li key={`dry-warning-${i}`}>{warning}</li>
                ))}
              </ul>
            )}
            {dryRunResult.errors.length > 0 && (
              <ul className="mt-1 space-y-0.5 list-disc pl-4">
                {dryRunResult.errors.map((dryError, i) => (
                  <li key={`dry-error-${i}`}>{dryError}</li>
                ))}
              </ul>
            )}
          </div>
        )}

        {/* Error */}
        {error && (
          <p className="rounded bg-red-50 p-2 text-xs text-red-700">{error}</p>
        )}
      </div>
    </SectionCard>
  );
}
