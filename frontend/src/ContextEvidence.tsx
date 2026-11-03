import { useEffect, useState } from "react";
import { post, request } from "./api";
import type { ContextGap, EvidenceSource } from "./types";

type Report = {
  retrieval_trace?: {
    action_ref: string;
    source: string;
    requirement_ids: string[];
    executed: boolean;
    status: string;
    evidence_refs: string[];
    failures: { reason: string }[];
  }[];
  plan: { profile_version: string; artifact_type: string; outcome: string };
  gap_report: ContextGap[];
  package: Record<string, unknown> | null;
};
type Update = {
  record_id: string;
  source: string;
  source_version: string;
  domain: string;
};
type Source = {
  category: string;
  name: string;
  configured_adapters: string[];
  reference_urls: string[];
  local_project_sources: boolean;
};

export default function ContextEvidence({
  projectId,
  planRef,
  readOnly = false,
}: {
  projectId: string;
  planRef: string;
  readOnly?: boolean;
}) {
  const [report, setReport] = useState<Report | null>(null),
    [sources, setSources] = useState<Source[]>([]),
    [updates, setUpdates] = useState<Update[]>([]),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [comparisons, setComparisons] = useState<Record<string, string>>({});
  const [fingerprints, setFingerprints] = useState<Record<string, string>>({});
  useEffect(() => {
    let active = true;
    setError("");
    setReport(null);
    Promise.all([
      request<Report>(`/projects/${projectId}/context/plans/${planRef}`),
      request<Source[]>(`/projects/${projectId}/context/sources`),
      request<Update[]>(`/projects/${projectId}/context/updates`),
    ])
      .then(([r, s, u]) => {
        if (active) {
          setReport(r);
          setSources(s);
          setUpdates(u);
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [projectId, planRef]);
  const evidence = new Map<string, EvidenceSource>();
  Object.values(report?.package || {}).forEach((value) => {
    if (Array.isArray(value))
      value.forEach((raw) => {
        if (raw && typeof raw === "object" && "original_uri" in raw) {
          const item = raw as EvidenceSource;
          evidence.set(`${item.source_id}:${item.source_version}`, item);
        }
      });
  });
  async function review(recordId: string, approved: boolean) {
    setBusy(true);
    setError("");
    try {
      await post(`/projects/${projectId}/context/updates/${recordId}/review`, {
        approved,
        expected_fingerprint: fingerprints[recordId],
      });
      setUpdates(updates.filter((u) => u.record_id !== recordId));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="evidence-review" aria-label="Context evidence review">
      <h4>Context evidence</h4>
      {error && <p role="alert">{error}</p>}
      {!report && !error && <p role="status">Loading evidence…</p>}
      {report && (
        <>
          <p>
            {report.plan.artifact_type} profile {report.plan.profile_version} ·{" "}
            {report.plan.outcome.replaceAll("_", " ")}
          </p>
          <p className="muted">
            Evidence is selected for this task. Missing or uncertain sources
            qualify the draft; they do not imply live SAP verification.
          </p>
          <h5>Gaps and qualifications</h5>
          {report.gap_report.length ? (
            report.gap_report.map((gap, i) => (
              <p role="note" key={gap.requirement_id + i}>
                <strong>{gap.gap_type.replaceAll("_", " ")}</strong>:{" "}
                {gap.reason}
                <br />
                <small>{gap.qualification}</small>
              </p>
            ))
          ) : (
            <p>No unresolved context gaps recorded.</p>
          )}
          <h5>Original sources</h5>
          {!!report.retrieval_trace?.length && (
            <details>
              <summary>Retrieval attempts</summary>
              {report.retrieval_trace.map((attempt) => (
                <p key={attempt.action_ref}>
                  <strong>{attempt.source}</strong>:{" "}
                  {attempt.executed ? "Executed" : "Not executed"} ·{" "}
                  {attempt.status}
                  <br />
                  <small>
                    Requirements: {attempt.requirement_ids.join(", ")} ·
                    Evidence: {attempt.evidence_refs.length}
                    {attempt.failures.map((f) => " · " + f.reason).join("")}
                  </small>
                </p>
              ))}
            </details>
          )}
          {Array.isArray(report.package?.assumptions) &&
            report.package.assumptions.length > 0 && (
              <div>
                <h5>Explicit assumptions and inferences</h5>
                {report.package.assumptions.map((item, i) => (
                  <p key={i}>{String(item)}</p>
                ))}
              </div>
            )}
          {[...evidence.values()].map((item) => (
            <p key={`${item.source_id}:${item.source_version}`}>
              <strong>{item.original_uri || item.source}</strong>
              <br />
              {item.scope} · {item.domain} · version{" "}
              {item.source_version || "not recorded"} ·{" "}
              {item.evidence_status || "unknown"}
              <br />
              <small>{item.rights}</small>
            </p>
          ))}
          <details>
            <summary>Source availability</summary>
            {sources.map((source) => (
              <p key={source.category}>
                <strong>{source.name}</strong>:{" "}
                {source.local_project_sources
                  ? "Project source"
                  : source.configured_adapters.length
                    ? "Configured: " + source.configured_adapters.join(", ")
                    : "No adapter configured"}
                {source.reference_urls.map((url) => (
                  <span key={url}>
                    <br />
                    <a href={url} target="_blank" rel="noreferrer">
                      Reference website
                    </a>{" "}
                    (a reference link, not a connection)
                  </span>
                ))}
              </p>
            ))}
          </details>
          {updates.length > 0 && (
            <>
              <h5>Source changes awaiting review</h5>
              {updates.map((update) => (
                <div key={update.record_id}>
                  <p>
                    {update.source} · proposed version{" "}
                    {update.source_version || "unknown"}. Reconciliation changes
                    knowledge copies; it does not rewrite approved artifacts.
                  </p>
                  <button
                    disabled={busy}
                    onClick={async () => {
                      try {
                        const result = await request<{
                          diff: string;
                          metadata: unknown;
                          current_fingerprint: string;
                        }>(
                          `/projects/${projectId}/context/updates/${update.record_id}`,
                        );
                        setComparisons({
                          ...comparisons,
                          [update.record_id]:
                            result.diff +
                            "\n\nSource metadata\n" +
                            JSON.stringify(result.metadata, null, 2),
                        });
                        setFingerprints({
                          ...fingerprints,
                          [update.record_id]: result.current_fingerprint,
                        });
                      } catch (e) {
                        setError((e as Error).message);
                      }
                    }}
                  >
                    Compare source changes
                  </button>
                  {comparisons[update.record_id] && (
                    <pre className="upload-comparison">
                      {comparisons[update.record_id]}
                    </pre>
                  )}
                  <button
                    disabled={
                      busy || readOnly || !comparisons[update.record_id]
                    }
                    onClick={() => review(update.record_id, true)}
                  >
                    Accept source update
                  </button>
                  <button
                    disabled={busy || readOnly}
                    onClick={() => review(update.record_id, false)}
                  >
                    Keep current source copy
                  </button>
                </div>
              ))}
            </>
          )}
        </>
      )}
    </section>
  );
}
