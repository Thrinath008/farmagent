import { ExternalLink } from "lucide-react";
import type { SourceRef } from "@/types/api";

export function SourceList({ sources, title = "Sources" }: { sources: SourceRef[]; title?: string }) {
  if (sources.length === 0) return null;
  return (
    <div>
      <h4 className="text-sm font-medium">{title}</h4>
      <ul className="mt-1 space-y-1 text-sm">
        {sources.map((source) => (
          <li key={source.id}>
            <a
              href={source.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-start gap-1.5 text-shoot-ink underline-offset-2 hover:underline"
            >
              <ExternalLink className="mt-1 size-3 shrink-0" aria-hidden="true" />
              <span>
                {source.title} <span className="text-muted-foreground">· {source.publisher}</span>
              </span>
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
