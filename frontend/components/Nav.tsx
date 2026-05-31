import Link from "next/link";

export default function Nav() {
  return (
    <header className="topbar">
      <Link className="brand" href="/">
        <span className="brand-mark">JT</span>
        <span>
          <span className="brand-title">JudgeTracker Atlas</span>
          <span className="brand-subtitle"> Court-event tracker prototype</span>
        </span>
      </Link>
      <nav className="topnav" aria-label="Primary">
        <Link href="/">Dashboard</Link>
        <Link href="/map">Map</Link>
        <Link href="/judges">Judges</Link>
        <Link href="/sources">Sources</Link>
        <Link href="/admin/review">Admin Review</Link>
        <Link href="/admin/sources">Sources</Link>
        <Link href="/admin/ai-checks">AI Checks</Link>
      </nav>
    </header>
  );
}
