"use client";

import { useCallback, useMemo, useState } from "react";
import {
  ps3ReportPdfUrl,
  streamPs3Analysis,
  toApiRequestError,
  type AnalysisProgressEvent,
  type AnalysisStartedEvent,
  type AnalysisStreamStep,
  type Ps3ReportResponse,
  type RequirementReport,
} from "@/lib/api";

type RunState = "idle" | "running" | "complete" | "error";

const STATUS_TONE: Record<string, "ready" | "partial" | "needs-prep"> = {
  COMPLIANT: "ready",
  PARTIAL: "partial",
  GAP: "needs-prep",
};

const DEFAULT_STEPS: AnalysisStreamStep[] = [
  { id: "load_requirements", label: "Parse policies" },
  { id: "collect_evidence", label: "Collect evidence" },
  { id: "embed", label: "Embed text" },
  { id: "link_evidence", label: "Link evidence" },
  { id: "evaluate_quality", label: "Evaluate quality" },
  { id: "generate_narratives", label: "Write narratives" },
  { id: "assemble_report", label: "Assemble report" },
];

function tone(status: string) {
  return STATUS_TONE[status] ?? "needs-prep";
}

function pct(value: number) {
  return `${Math.round(value)}%`;
}

function confidencePct(value: number) {
  return `${Math.round(value * 100)}%`;
}

function StatusPill({ status }: { status: string }) {
  return (
    <span className={`rk-status-pill rk-status-${tone(status)}`}>
      <span />
      {status}
    </span>
  );
}

function SummaryMetric({
  label,
  value,
  toneName = "neutral",
}: {
  label: string;
  value: string | number;
  toneName?: "neutral" | "ready" | "partial" | "needs-prep";
}) {
  return (
    <div className={`rk-summary-metric rk-summary-${toneName}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function RequirementRow({
  requirement,
  selected,
  onSelect,
}: {
  requirement: RequirementReport;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      className={`rk-control-row ${selected ? "is-selected" : ""}`}
      onClick={onSelect}
      type="button"
    >
      <span className="rk-control-main">
        <strong>{requirement.id}</strong>
        <small>{requirement.text}</small>
      </span>
      <StatusPill status={requirement.status} />
      <span className="rk-confidence">{confidencePct(requirement.confidence)}</span>
      <span className="rk-gap-count">{(requirement.gaps ?? []).length}</span>
    </button>
  );
}

function RequirementDetail({ requirement }: { requirement: RequirementReport | null }) {
  if (!requirement) {
    return (
      <aside className="rk-panel rk-detail-panel">
        <p className="rk-muted">Select a requirement to inspect the evidence and narrative.</p>
      </aside>
    );
  }

  const evidence = requirement.linked_evidence ?? [];

  return (
    <aside className="rk-panel rk-detail-panel">
      <div className="rk-detail-header">
        <div>
          <span className="rk-eyebrow">
            {requirement.id} · {(requirement.frameworks ?? []).join(", ")}
          </span>
          <h2>{requirement.text}</h2>
        </div>
        <StatusPill status={requirement.status} />
      </div>

      <div className="rk-detail-summary">
        <div>
          <span>Confidence</span>
          <strong>{confidencePct(requirement.confidence)}</strong>
        </div>
        <div>
          <span>Freshness SLA</span>
          <strong>{requirement.freshness_sla_days}d</strong>
        </div>
        <div>
          <span>Next review</span>
          <strong>{requirement.next_review_date || "--"}</strong>
        </div>
      </div>

      <section className="rk-focus-block">
        <span>Auditor narrative</span>
        <p>{requirement.narrative}</p>
      </section>

      <section className="rk-detail-section">
        <h3>Audit cadence</h3>
        <p>
          {requirement.audit_frequency} — evidence must be within {requirement.freshness_sla_days} days.
        </p>
      </section>

      <section className="rk-detail-section">
        <h3>Why this status</h3>
        <p>{requirement.confidence_rationale}</p>
      </section>

      {(requirement.gaps ?? []).length ? (
        <section className="rk-detail-section">
          <h3>Gaps</h3>
          <ul className="rk-detail-list">
            {(requirement.gaps ?? []).map((gap, index) => (
              <li key={index}>{gap}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <details className="rk-fold" open>
        <summary>Linked evidence ({evidence.length})</summary>
        {evidence.length ? (
          <div className="rk-evidence-list">
            {evidence.map((item) => (
              <div className="rk-evidence-item" key={item.evidence_id}>
                <strong>
                  {item.evidence_id} · {item.type}
                </strong>
                <span>
                  {item.framework} / collected {item.collection_date} / {item.freshness_days}d old /
                  conf {item.confidence_score?.toFixed?.(2) ?? item.confidence_score} / link{" "}
                  {item.link_confidence?.toFixed?.(2) ?? item.link_confidence}
                </span>
                <code>{(item.flags ?? []).join(", ") || "acceptable"}</code>
              </div>
            ))}
          </div>
        ) : (
          <p className="rk-muted">No evidence linked to this requirement.</p>
        )}
      </details>
    </aside>
  );
}

export default function Home() {
  const [report, setReport] = useState<Ps3ReportResponse | null>(null);
  const [runState, setRunState] = useState<RunState>("idle");
  const [progress, setProgress] = useState<AnalysisProgressEvent[]>([]);
  const [steps, setSteps] = useState<AnalysisStreamStep[]>(DEFAULT_STEPS);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [framework, setFramework] = useState<string>("All");

  const handlers = useCallback(
    () => ({
      onStarted: (event: AnalysisStartedEvent) => {
        setSteps(event.steps.length ? event.steps : DEFAULT_STEPS);
      },
      onProgress: (event: AnalysisProgressEvent) => {
        setProgress((current) => [...current.filter((p) => p.step !== event.step), event]);
      },
      onComplete: (response: Ps3ReportResponse) => {
        setReport(response);
        setSelectedId(response.requirements?.[0]?.id ?? null);
        setRunState("complete");
      },
      onError: (err: Error) => {
        setError(toApiRequestError(err).message);
        setRunState("error");
      },
    }),
    [],
  );

  const runAnalysis = async () => {
    setRunState("running");
    setProgress([]);
    setError(null);
    try {
      await streamPs3Analysis(handlers());
    } catch (err) {
      setError(toApiRequestError(err).message);
      setRunState("error");
    }
  };

  const frameworks = useMemo(() => ["All", ...(report?.summary.frameworks ?? [])], [report]);

  const visibleRequirements = useMemo(() => {
    const reqs = report?.requirements ?? [];
    if (framework === "All") return reqs;
    return reqs.filter((r) => (r.frameworks ?? []).includes(framework));
  }, [report, framework]);

  const selected = useMemo(
    () => visibleRequirements.find((r) => r.id === selectedId) ?? visibleRequirements[0] ?? null,
    [visibleRequirements, selectedId],
  );

  const progressPct = progress.length
    ? Math.max(...progress.map((p) => p.progress))
    : 0;

  if (runState === "idle" || runState === "running") {
    return (
      <main className="rk-app rk-app-center">
        <section className="rk-run-hero ps3-hero">
          <span className="rk-eyebrow">Automated Compliance Evidence &amp; Audit</span>
          <h1>Compliance Evidence Auditor</h1>
          <p className="rk-muted">
            Parse policy requirements, auto-collect evidence, link it semantically, evaluate
            freshness against each requirement&apos;s audit-frequency SLA, and generate an
            auditor-ready report.
          </p>
          <button
            className="rk-button rk-button-primary"
            onClick={runAnalysis}
            type="button"
            disabled={runState === "running"}
          >
            {runState === "running" ? "Analysing…" : "Run compliance analysis"}
          </button>

          {runState === "running" ? (
            <div className="ps3-run">
              <div className="ps3-progress-track">
                <span style={{ width: `${progressPct}%` }} />
              </div>
              <ul className="ps3-steps">
                {steps.map((step) => {
                  const done = progress.some((p) => p.step === step.id);
                  const event = progress.find((p) => p.step === step.id);
                  return (
                    <li className="ps3-step" key={step.id}>
                      <span className={`ps3-dot ${done ? "is-done" : ""}`} />
                      <strong>{step.label}</strong>
                      <small>{event?.message ?? ""}</small>
                    </li>
                  );
                })}
              </ul>
            </div>
          ) : null}
        </section>
      </main>
    );
  }

  if (runState === "error") {
    return (
      <main className="rk-app rk-app-center">
        <section className="rk-retry-panel">
          <h1>Analysis failed</h1>
          <p className="rk-muted">{error}</p>
          <button className="rk-button rk-button-primary" onClick={runAnalysis} type="button">
            Retry
          </button>
        </section>
      </main>
    );
  }

  const summary = report!.summary;

  return (
    <main className="rk-app">
      <header className="rk-report-top">
        <div className="rk-brand rk-brand-compact">
          <span className="rk-brand-mark">C</span>
          <div>
            <strong>CompAud</strong>
            <span>Compliance evidence audit</span>
          </div>
        </div>
        <div className="rk-report-actions">
          <select
            className="rk-button rk-button-secondary"
            value={framework}
            onChange={(event) => setFramework(event.target.value)}
            aria-label="Filter by framework"
          >
            {frameworks.map((fw) => (
              <option key={fw} value={fw}>
                {fw === "All" ? "All frameworks" : fw}
              </option>
            ))}
          </select>
          <button className="rk-button rk-button-secondary" onClick={runAnalysis} type="button">
            Re-run
          </button>
          <a
            className="rk-button rk-button-primary"
            href={ps3ReportPdfUrl()}
            target="_blank"
            rel="noreferrer"
          >
            Download PDF
          </a>
        </div>
      </header>

      <section className="rk-report-title">
        <span className="rk-eyebrow">{summary.total_requirements} requirements · {summary.total_evidence} evidence auto-collected</span>
        <h1>Compliance audit report</h1>
        <div className="rk-exec-summary-box">
          <span className="rk-exec-summary-title">Executive Summary</span>
          <p>{summary.exec_summary}</p>
        </div>
      </section>

      <section className="rk-summary-strip">
        <SummaryMetric label="Compliance" toneName="ready" value={pct(summary.overall_compliance_pct)} />
        <SummaryMetric label="Coverage" toneName="ready" value={pct(summary.coverage_pct)} />
        <SummaryMetric label="Freshness" toneName="partial" value={pct(summary.freshness_pct)} />
        <SummaryMetric label="Automated" toneName="ready" value={pct(summary.auto_collected_pct)} />
      </section>

      <section className="rk-summary-strip">
        <SummaryMetric label="Compliant" toneName="ready" value={summary.compliant_count} />
        <SummaryMetric label="Partial" toneName="partial" value={summary.partial_count} />
        <SummaryMetric label="Gap" toneName="needs-prep" value={summary.gap_count} />
        <SummaryMetric label="Orphan evidence" toneName="neutral" value={summary.orphan_count} />
      </section>

      <section className="rk-main-grid">
        <section className="rk-panel rk-controls-panel">
          <div className="rk-panel-header">
            <div>
              <span className="rk-eyebrow">Requirements</span>
              <h2>
                {visibleRequirements.length}
                {framework !== "All" ? ` ${framework}` : ""} requirement(s)
              </h2>
            </div>
          </div>

          <div className="rk-control-table">
            <div className="rk-control-header" aria-hidden="true">
              <span>Requirement</span>
              <span>Status</span>
              <span>Confidence</span>
              <span>Gaps</span>
            </div>
            {visibleRequirements.map((requirement) => (
              <RequirementRow
                key={requirement.id}
                requirement={requirement}
                onSelect={() => setSelectedId(requirement.id)}
                selected={selected?.id === requirement.id}
              />
            ))}
          </div>
        </section>

        <RequirementDetail requirement={selected} />
      </section>

      {report!.disclaimer ? <footer className="rk-disclaimer">{report!.disclaimer}</footer> : null}
    </main>
  );
}
