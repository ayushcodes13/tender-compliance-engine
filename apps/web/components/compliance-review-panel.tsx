"use client";

import { useEffect, useState } from "react";
import { AlertCircle, Check, RefreshCw } from "lucide-react";

import {
  api,
  AssessmentCommentResponse,
  ComplianceAssessmentResponse,
  ComplianceStatus,
  RequirementComplianceReview,
} from "@/lib/api/client";

const STATUS_OPTIONS: ComplianceStatus[] = [
  "compliant",
  "non_compliant",
  "partial",
  "not_demonstrated",
  "conflict",
  "human_review_required",
];

const label = (value: string) =>
  value.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());

export function ComplianceReviewPanel(props: {
  projectId: string;
  requirementId: string;
}) {
  const { projectId, requirementId } = props;
  const [assessment, setAssessment] = useState<ComplianceAssessmentResponse | null>(null);
  const [review, setReview] = useState<RequirementComplianceReview | null>(null);
  const [comments, setComments] = useState<AssessmentCommentResponse[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [overrideStatus, setOverrideStatus] = useState<ComplianceStatus>("human_review_required");
  const [reason, setReason] = useState("");
  const [comment, setComment] = useState("");

  const reload = async () => {
    setError(null);
    try {
      const latest = await api.fetchComplianceAssessment(projectId, requirementId);
      setAssessment(latest);
      if (!latest) {
        setReview(null);
        setComments([]);
        return;
      }
      const [combined, nextComments] = await Promise.all([
        api.fetchRequirementComplianceReview(projectId, requirementId),
        api.fetchAssessmentComments(projectId, latest.id),
      ]);
      setReview(combined);
      setComments(nextComments);
      setOverrideStatus(latest.status);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load compliance review");
    }
  };

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, requirementId]);

  const run = async (key: string, action: () => Promise<unknown>) => {
    setBusy(key);
    setError(null);
    try {
      await action();
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Review action failed");
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="evidence-section">
      <div className="evidence-section-heading">
        <span>Compliance review</span>
        <button type="button" className="tiny-action" onClick={() => void reload()} disabled={busy !== null}>
          <RefreshCw size={12} aria-hidden="true" /> Refresh
        </button>
      </div>

      <p className="field-help">
        System assessment is a suggestion until a human confirms it. Missing evidence stays
        <strong> Not demonstrated</strong> / <strong>Human review required</strong>; it is not treated as non-compliance.
      </p>

      {error ? <p className="save-error" role="alert">{error}</p> : null}

      {!assessment ? (
        <button
          className="button button-primary button-small"
          type="button"
          disabled={busy !== null}
          onClick={() => void run("assess", () => api.assessRequirement(projectId, requirementId))}
        >
          {busy === "assess" ? "Assessing…" : "Run evidence-backed assessment"}
        </button>
      ) : (
        <>
          <div className="normalized-card">
            <span className="normalized-id">Assessment v{assessment.assessment_version}</span>
            <p><strong>{label(assessment.status)}</strong></p>
            <p>{assessment.reason_text ?? label(assessment.reason_code)}</p>
            <p className="field-help">
              Suggested: {label(assessment.suggested_status)}
              {assessment.is_confirmed_by_human ? " · Human confirmed" : " · Awaiting human confirmation"}
            </p>
          </div>

          {assessment.comparison_result?.comparison_rule ? (
            <dl className="requirement-facts">
              <div><dt>Rule</dt><dd>{assessment.comparison_result.comparison_rule}</dd></div>
              <div><dt>Tender</dt><dd>{assessment.comparison_result.tender_text ?? "—"}</dd></div>
              <div><dt>Vendor</dt><dd>{assessment.comparison_result.vendor_text ?? "—"}</dd></div>
            </dl>
          ) : null}

          <div className="inline-actions">
            {!assessment.is_confirmed_by_human ? (
              <button
                className="button button-primary button-small"
                type="button"
                disabled={busy !== null}
                onClick={() => void run("confirm", () => api.confirmAssessment(projectId, assessment.id))}
              >
                <Check size={12} aria-hidden="true" /> Confirm assessment
              </button>
            ) : (
              <button
                className="button button-secondary button-small"
                type="button"
                disabled={busy !== null}
                onClick={() => void run("reopen", () => api.reopenAssessment(projectId, assessment.id, "Reopened from browser review"))}
              >
                Reopen review
              </button>
            )}
          </div>

          <div style={{ marginTop: 12 }}>
            <label>
              <span className="detail-label">Override status</span>
              <select value={overrideStatus} onChange={(e) => setOverrideStatus(e.target.value as ComplianceStatus)}>
                {STATUS_OPTIONS.map((status) => <option key={status} value={status}>{label(status)}</option>)}
              </select>
            </label>
            <textarea
              className="review-textarea"
              rows={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Required reason for human override…"
              aria-label="Override reason"
            />
            <button
              className="button button-secondary button-small"
              type="button"
              disabled={!reason.trim() || busy !== null}
              onClick={() => void run("override", () =>
                api.overrideAssessment(projectId, assessment.id, {
                  status: overrideStatus,
                  reason: reason.trim(),
                }).then(() => setReason(""))
              )}
            >
              Apply audited override
            </button>
          </div>

          {review?.conflicts.length ? (
            <div style={{ marginTop: 14 }}>
              <strong>Conflicts ({review.conflicts.length})</strong>
              {review.conflicts.map((conflict) => (
                <div className="normalized-card" key={conflict.id}>
                  <p><strong>{label(conflict.conflict_type)}</strong> · {conflict.parameter ?? "unspecified parameter"}</p>
                  <p>{conflict.tender_claim ?? "Conflicting OEM evidence requires review."}</p>
                  <p className="field-help">Resolution: {label(conflict.resolution)}</p>
                  {conflict.resolution === "unresolved" ? (
                    <div className="inline-actions">
                      <button className="button button-secondary button-small" type="button"
                        onClick={() => void run(`conflict-${conflict.id}`, () => api.resolveConflict(projectId, conflict.id, "accepted", "Accepted during browser review"))}>
                        Accept conflict
                      </button>
                      <button className="button button-secondary button-small" type="button"
                        onClick={() => void run(`conflict-${conflict.id}`, () => api.resolveConflict(projectId, conflict.id, "rejected", "Rejected during browser review"))}>
                        Reject conflict
                      </button>
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}

          <div style={{ marginTop: 14 }}>
            <div className="evidence-section-heading">
              <span>Clarifications ({review?.clarifications.length ?? 0})</span>
              <button className="tiny-action" type="button" disabled={busy !== null}
                onClick={() => void run("clarify", () => api.autoGenerateClarifications(projectId, requirementId))}>
                Generate from unresolved gaps
              </button>
            </div>
            {review?.clarifications.map((item) => (
              <div className="normalized-card" key={item.id}>
                <p>{item.question}</p>
                <p className="field-help">{label(item.status)}{item.answer ? ` · Answer: ${item.answer}` : ""}</p>
              </div>
            ))}
          </div>

          {review?.deviations.length ? (
            <div style={{ marginTop: 14 }}>
              <strong>Deviations ({review.deviations.length})</strong>
              {review.deviations.map((item) => (
                <div className="normalized-card" key={item.id}>
                  <p><strong>{label(item.deviation_type)}</strong>: {item.proposed_alternative ?? "No alternative supplied"}</p>
                  <p className="field-help">Status: {label(item.status)}</p>
                  {item.status === "proposed" ? (
                    <div className="inline-actions">
                      <button className="button button-secondary button-small" type="button"
                        onClick={() => void run(`deviation-${item.id}`, () => api.reviewDeviation(projectId, item.id, "accepted"))}>
                        Accept
                      </button>
                      <button className="button button-secondary button-small" type="button"
                        onClick={() => void run(`deviation-${item.id}`, () => api.reviewDeviation(projectId, item.id, "rejected"))}>
                        Reject
                      </button>
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}

          <div style={{ marginTop: 14 }}>
            <strong>Assessment comments ({comments.length})</strong>
            {comments.map((item) => (
              <p className="field-help" key={item.id}>{item.comment}</p>
            ))}
            <textarea className="review-textarea" rows={2} value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Add an auditable reviewer comment…" />
            <button className="button button-secondary button-small" type="button"
              disabled={!comment.trim() || busy !== null}
              onClick={() => void run("comment", () =>
                api.addAssessmentComment(projectId, assessment.id, comment.trim()).then(() => setComment(""))
              )}>
              Add comment
            </button>
          </div>
        </>
      )}

      {review?.conflicts.some((c) => c.resolution === "unresolved") ? (
        <p className="save-error"><AlertCircle size={12} aria-hidden="true" /> Unresolved conflict remains. Do not finalize this requirement yet.</p>
      ) : null}
    </section>
  );
}
