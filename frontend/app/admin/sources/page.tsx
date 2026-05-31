import { cookies } from "next/headers";
import { PageHeader } from "@/components/layout/PageHeader";
import { fetchJson, AdminSourceItem } from "@/lib/api";
import { SourceControlCard } from "@/components/SourceControlCard";
import { LIFECYCLE_STATE_LABELS } from "@/lib/sourceContracts";

function getErrorMessage(err: unknown): string {
  const msg = err instanceof Error ? err.message : String(err);
  if (msg.includes("401") || msg.includes("403")) {
    return "Access denied — admin authentication failed.";
  }
  if (msg.includes("503")) {
    return "Admin authentication failed. Check server auth configuration.";
  }
  if (msg.includes("500")) {
    return "Backend error (500) — check backend logs.";
  }
  return `Failed to load sources: ${msg}`;
}

type SearchParamValue = string | string[] | undefined;

function firstParam(value: SearchParamValue): string {
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function buildFilterQuery(searchParams: Record<string, SearchParamValue> | undefined): string {
  const params = new URLSearchParams();
  const lifecycle = firstParam(searchParams?.lifecycle_state);
  const jurisdiction = firstParam(searchParams?.jurisdiction);
  const authority = firstParam(searchParams?.public_record_authority);
  const runnable = firstParam(searchParams?.runnable);
  const showDeprecated = firstParam(searchParams?.show_deprecated);

  if (lifecycle) params.set("lifecycle_state", lifecycle);
  if (jurisdiction) params.set("jurisdiction", jurisdiction);
  if (authority) params.set("public_record_authority", authority);
  if (runnable === "true" || runnable === "false") params.set("runnable", runnable);

  // Default is hide deprecated unless explicitly enabled.
  if (showDeprecated === "true") {
    params.set("show_deprecated", "true");
  }

  return params.toString();
}

export default async function AdminSourcesPage({
  searchParams,
}: {
  searchParams?: Record<string, SearchParamValue>;
}) {
  let sources: AdminSourceItem[] = [];
  let errorMessage: string | null = null;
  const query = buildFilterQuery(searchParams);
  const selectedLifecycle = firstParam(searchParams?.lifecycle_state);
  const selectedJurisdiction = firstParam(searchParams?.jurisdiction);
  const selectedAuthority = firstParam(searchParams?.public_record_authority);
  const selectedRunnable = firstParam(searchParams?.runnable);
  const showDeprecated = firstParam(searchParams?.show_deprecated) === "true";

  try {
    const cookieStore = cookies();
    const accessToken = cookieStore.get("jta_access_token")?.value ?? "";
    const path = query ? `/api/admin/sources?${query}` : "/api/admin/sources";
    sources = await fetchJson<AdminSourceItem[]>(path, {
      headers: accessToken ? { authorization: `Bearer ${accessToken}` } : {},
    });
  } catch (err) {
    errorMessage = getErrorMessage(err);
  }

  const activeSources = sources.filter((s) => s.is_active);
  const runnableSources = sources.filter((s) => s.runnable_now);
  const enableReadySources = sources.filter((s) => Boolean(s.enable_ready));
  const deprecatedSources = sources.filter((s) => s.lifecycle_state === "deprecated");
  const byAuthority = sources.reduce<Record<string, number>>((acc, s) => {
    acc[s.public_record_authority] = (acc[s.public_record_authority] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      <PageHeader
        title="Source Registry"
        subtitle={`${sources.length} visible · ${activeSources.length} active`}
      />

      <form className="grid gap-3 rounded border p-3 text-sm sm:grid-cols-6" method="GET" action="/admin/sources">
        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">Lifecycle</span>
          <select name="lifecycle_state" defaultValue={selectedLifecycle} className="rounded border px-2 py-1">
            <option value="">All lifecycle states</option>
            {Object.entries(LIFECYCLE_STATE_LABELS).map(
              ([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ),
            )}
          </select>
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">Jurisdiction</span>
          <input
            name="jurisdiction"
            defaultValue={selectedJurisdiction}
            placeholder="e.g. Canada or CA-SK"
            className="rounded border px-2 py-1"
          />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">Runnable</span>
          <select name="runnable" defaultValue={selectedRunnable} className="rounded border px-2 py-1">
            <option value="">All</option>
            <option value="true">Runnable now</option>
            <option value="false">Not runnable</option>
          </select>
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">Authority</span>
          <input
            name="public_record_authority"
            defaultValue={selectedAuthority}
            placeholder="e.g. official_legislation"
            className="rounded border px-2 py-1"
          />
        </label>

        <label className="flex items-center gap-2 pt-5 text-xs text-muted-foreground">
          <input type="checkbox" name="show_deprecated" value="true" defaultChecked={showDeprecated} />
          Show deprecated sources
        </label>

        <div className="flex items-end gap-2">
          <button type="submit" className="rounded border px-3 py-1.5 text-xs font-medium">Apply</button>
          <a href="/admin/sources" className="rounded border px-3 py-1.5 text-xs">
            Reset
          </a>
        </div>
      </form>

      {errorMessage && (
        <div className="rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {errorMessage}
        </div>
      )}

      {/* Summary bar */}
      {!errorMessage && (
        <div className="space-y-2">
          <div className="flex flex-wrap gap-2 text-xs">
            <span className="rounded border px-2 py-0.5">
              Runnable now: {runnableSources.length}
            </span>
            <span className="rounded border px-2 py-0.5">
              Enable-ready: {enableReadySources.length}
            </span>
            <span className="rounded border px-2 py-0.5">
              Deprecated: {deprecatedSources.length}
            </span>
          </div>
          <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
          {Object.entries(byAuthority).sort(([, a], [, b]) => b - a).map(([auth, count]) => (
            <span key={auth} className="rounded border px-2 py-0.5">
              {auth.replace(/_/g, " ")}: {count}
            </span>
          ))}
          </div>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {sources.map((source) => (
          <SourceControlCard key={source.id} source={source} />
        ))}
      </div>

      {!errorMessage && sources.length === 0 && (
        <p className="text-sm text-muted-foreground">No sources found.</p>
      )}
    </div>
  );
}


