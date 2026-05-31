import { SourceLink } from "@/lib/api";

type Props = {
  links: SourceLink[] | undefined;
};

function sourceTypeBadge(sourceType: string): string {
  switch (sourceType) {
    case "official":
    case "open_data":
    case "official_police_open_data":
      return "Official";
    case "court_record":
      return "Court record";
    case "news":
    case "news_article":
      return "News";
    default:
      return sourceType.replaceAll("_", " ");
  }
}

export default function SourceLinks({ links }: Props) {
  if (!links?.length) {
    return <p className="source-links-empty">No public source links attached.</p>;
  }
  return (
    <ul className="source-link-list">
      {links.map((link, i) => (
        <li key={`${link.url}-${i}`} className="source-link-item">
          <a href={link.url} target="_blank" rel="noreferrer" className="source-link-label">
            {link.label}
          </a>
          <span className="source-link-badge">{sourceTypeBadge(link.source_type)}</span>
          {link.supports_claim ? (
            <span className="source-link-claim"> — {link.supports_claim}</span>
          ) : null}
          {link.retrieved_at ? (
            <span className="source-link-meta">Retrieved {link.retrieved_at.slice(0, 10)}</span>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
