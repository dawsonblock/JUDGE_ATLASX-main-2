"use client";

import { useEffect, useState } from "react";

/**
 * JudgeRelationshipArcs.tsx
 *
 * Renders relationship arc data from the backend when the server-side
 * publication policy allows it.  When ``arcs_enabled`` is false (the default),
 * this component remains a no-op — nothing is rendered and no arcs are exposed.
 *
 * The backend publication policy gates (Phase 2):
 *   1. ``enable_public_relationship_arcs`` feature flag must be True.
 *   2. Each edge must carry >= ``public_relationship_arc_min_evidence`` evidence refs.
 *   3. Edge predicates must not match any causal/blame/guilt pattern.
 *   4. Results are hard-capped at ``public_relationship_arc_max_results`` (default 250).
 *
 * When the policy allows arcs, future iterations of this component will render
 * a MapLibre ``line`` layer.  For now it remains a no-op even when the flag
 * is enabled, pending full frontend integration (Phase 8).
 */

interface ArcFeatureCollection {
  type: "FeatureCollection";
  features: unknown[];
  returned_count: number;
  arcs_enabled: boolean;
  disclaimer: string;
}

export default function JudgeRelationshipArcs() {
  const [arcsEnabled, setArcsEnabled] = useState(false);

  useEffect(() => {
    let cancelled = false;

    fetch("/api/map/relationship-arcs?limit=1")
      .then((res) => (res.ok ? res.json() : null))
      .then((data: ArcFeatureCollection | null) => {
        if (!cancelled && data?.arcs_enabled === true) {
          setArcsEnabled(true);
        }
      })
      .catch(() => {
        // Network failures are non-fatal; arcs remain hidden
      });

    return () => {
      cancelled = true;
    };
  }, []);

  // No arc rendering until Phase 8 frontend integration is complete.
  // arcsEnabled is tracked so the component re-renders cleanly when the flag
  // changes (useful for local dev / testing), but nothing is displayed yet.
  if (!arcsEnabled) {
    return null;
  }

  return null;
}

