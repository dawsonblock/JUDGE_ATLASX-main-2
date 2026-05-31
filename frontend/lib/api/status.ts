import { fetchJson } from "@/lib/api";

export type AlphaReadinessStatus = {
  alpha_gate_passed: boolean;
  production_ready: boolean;
  proof_chain_complete: boolean;
  archive_self_verifying: boolean;
  runnable_sources: number;
  enable_ready_sources: number;
  deprecated_sources: number;
  total_sources: number;
  evidence_store: string;
  public_review_gate: string;
  experimental_live_map: string;
  workflow_admin: string;
  storage_backend: string;
  queue_backend: string;
  rate_limit_backend: string;
  warnings: string[];
};

export async function fetchAlphaReadinessStatus(): Promise<AlphaReadinessStatus> {
  return fetchJson<AlphaReadinessStatus>("/status/alpha-readiness");
}
