import type { AlphaReadinessStatus } from "@/lib/api/status";

type Props = {
  status: AlphaReadinessStatus;
};

function badgeClass(value: boolean): string {
  return value
    ? "rounded border border-green-300 bg-green-50 px-2 py-0.5 text-green-700"
    : "rounded border border-red-300 bg-red-50 px-2 py-0.5 text-red-700";
}

export function AlphaReadinessPanel({ status }: Props) {
  return (
    <section className="space-y-4 rounded border p-4">
      <div className="rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
        This system is an alpha. Public-facing records require human review and evidence snapshots. Production readiness is false.
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 text-sm">
        <div>
          <div className="text-xs text-muted-foreground">Alpha gate</div>
          <span className={badgeClass(status.alpha_gate_passed)}>
            {status.alpha_gate_passed ? "passed" : "failed"}
          </span>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Production readiness</div>
          <span className={badgeClass(status.production_ready)}>
            {status.production_ready ? "true" : "false"}
          </span>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Proof chain</div>
          <span className={badgeClass(status.proof_chain_complete)}>
            {status.proof_chain_complete ? "complete" : "incomplete"}
          </span>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Archive self-verifying</div>
          <span className={badgeClass(status.archive_self_verifying)}>
            {status.archive_self_verifying ? "true" : "false"}
          </span>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Runnable sources</div>
          <div>{status.runnable_sources} / {status.total_sources}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Enable-ready sources</div>
          <div>{status.enable_ready_sources}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Deprecated sources</div>
          <div>{status.deprecated_sources}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Evidence store</div>
          <div>{status.evidence_store}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Public review gate</div>
          <div>{status.public_review_gate}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Experimental live map</div>
          <div>{status.experimental_live_map}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Workflow admin</div>
          <div>{status.workflow_admin}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Storage backend</div>
          <div>{status.storage_backend}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Queue backend</div>
          <div>{status.queue_backend}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Rate limit backend</div>
          <div>{status.rate_limit_backend}</div>
        </div>
      </div>

      <div>
        <h3 className="text-sm font-medium">Warnings</h3>
        {status.warnings.length === 0 ? (
          <p className="text-sm text-muted-foreground">No warnings reported.</p>
        ) : (
          <ul className="list-disc pl-5 text-sm">
            {status.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
