import MapWorkspace from "./MapWorkspace";

export const metadata = {
  title: "Public Records Map | JUDGE",
  description:
    "Explore publicly available court event records and reported incidents on an interactive map. All data is sourced from public records only.",
};

export default function MapPage() {
  return <MapWorkspace />;
}
