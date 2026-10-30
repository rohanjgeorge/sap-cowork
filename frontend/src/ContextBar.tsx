import { useState } from "react";
import { Gauge, Minimize2 } from "lucide-react";
import type { ContextStatus } from "./types";
export default function ContextBar({
  context,
  onCompact,
  busy,
}: {
  context: ContextStatus;
  onCompact: () => void;
  busy: boolean;
}) {
  const [details, setDetails] = useState(false);
  const labels: Record<string, string> = {
    healthy: "Healthy",
    watch: "Watch",
    compact_recommended: "Compact recommended",
    high_pressure: "High pressure",
  };
  const domains: Record<string, string> = {
    BUSINESS: "Business",
    SAP: "SAP",
    ORGANIZATION: "Org",
    HISTORICAL_DEVELOPMENT: "History",
    SDLC: "SDLC",
  };
  return (
    <section
      className={"context-bar " + context.band}
      aria-label="Working context"
    >
      <div className="context-overview">
        <button
          className="context-inspect"
          aria-expanded={details}
          onClick={() => setDetails(!details)}
        >
          <Gauge size={13} />
          <span>
            Context <strong>{context.usage_percent}%</strong>
          </span>
        </button>
        <div
          className="context-meter"
          role="progressbar"
          aria-label="Estimated context usage"
          aria-valuenow={Math.min(100, context.usage_percent)}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <span style={{ width: Math.min(100, context.usage_percent) + "%" }} />
        </div>
        <span className="context-band">{labels[context.band]}</span>
        <button className="compact-button" onClick={onCompact} disabled={busy}>
          <Minimize2 size={12} /> Compact
        </button>
      </div>
      <div className="context-domains">
        {context.active_domains.map((d) => (
          <span key={d}>{domains[d] || d}</span>
        ))}
      </div>
      {details && (
        <div className="context-details">
          <p>
            Estimated {context.used_tokens.toLocaleString()} tokens /{" "}
            {context.usable_context.toLocaleString()} usable tokens. Model
            window: {context.model_context_window.toLocaleString()}.
          </p>
          <p>
            {context.provider} / {context.model} · {context.compactions}{" "}
            compactions
          </p>
          <p>
            This meter describes working context. Project state, memory and
            stored artifacts are preserved when compacting.
          </p>
        </div>
      )}
      {context.band === "compact_recommended" && (
        <p className="context-recommendation">
          Compact context before the next large task.
        </p>
      )}
    </section>
  );
}
