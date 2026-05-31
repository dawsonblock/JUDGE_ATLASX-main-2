"use client";

/**
 * JudgeMapClient.tsx — dynamically imports JudgeMap with ssr:false to prevent
 * maplibre-gl from running during Next.js server rendering.
 */

import dynamic from "next/dynamic";
import { ReactNode } from "react";

const JudgeMapDynamic = dynamic(() => import("./JudgeMap"), { ssr: false });

type Props = {
  children?: ReactNode;
  className?: string;
};

export default function JudgeMapClient({ children, className }: Props) {
  return <JudgeMapDynamic className={className}>{children}</JudgeMapDynamic>;
}
