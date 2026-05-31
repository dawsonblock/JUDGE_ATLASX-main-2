"use client";

import dynamic from "next/dynamic";

const JudgeNorthAmericaMap = dynamic(() => import("./JudgeNorthAmericaMap"), {
  ssr: false,
  loading: () => <div className="map-loading">Loading map...</div>,
});

export default JudgeNorthAmericaMap;
