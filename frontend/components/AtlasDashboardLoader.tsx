"use client";

import dynamic from "next/dynamic";

const AtlasDashboard = dynamic(() => import("@/components/AtlasDashboard"), { ssr: false });

export default function AtlasDashboardLoader() {
  return <AtlasDashboard />;
}

