import logging
from typing import Any

from app.models.auditor import (
    AuditorEvaluation,
    ControlAuditorResult,
    ToolTraceEntry,
)
from app.models.compliance import ComplianceEvaluation, ControlComplianceResult
from app.models.controls import ControlRequirement
from app.models.risk import ControlRiskResult, RiskEvaluation

logger = logging.getLogger(__name__)


READY_QUESTION_OVERRIDES = {
    "FT-DPDP-02": "Can you prove raw PAN is not stored and CVV/CVC is never retained after authorization?",
}

SUGGESTIONS = {
    "FT-IAM-01": "Enable MFA for dev_priya or upload an approved exception with compensating controls and expiry date.",
    "FT-IAM-02": "Upload a privileged access review covering service accounts, database admins, production breakglass users, review outcome, reviewer, and remediation.",
    "FT-DPDP-01": "Upload the consent enforcement rule, suppression-list job evidence, or incident ticket explaining the post-revocation processing event.",
    "FT-DPDP-02": "Keep the encryption and data protection policy with load balancer configuration, KMS key rotation evidence, tokenization configuration, and PAN masking screenshots for the final audit package.",
    "FT-VAPT-01": "Upload a patch ticket, exception approval, compensating control, updated retest report, and passing quarterly ASV scan after remediation.",
    "FT-LOG-01": "Upload SIEM or cloud logging configuration evidence showing retention_days=180 and tamper-protection settings.",
    "FT-IR-01": "Keep the playbook attached and add a future tabletop drill record to strengthen execution evidence.",
}

RISK_SUMMARIES = {
    "FT-IAM-01": "One active developer account lacks MFA, creating a direct audit gap for production access readiness.",
    "FT-IAM-02": "Human access review exists, but privileged service and database access remain unsupported.",
    "FT-DPDP-01": "Consent records exist, but post-revocation processing creates a privacy readiness gap.",
    "FT-DPDP-02": "Encryption and cardholder data protection policy evidence is review-ready for the demo scope.",
    "FT-VAPT-01": "A high-risk vulnerability is active beyond the demo SLA and has caused the quarterly PCI-DSS ASV scan to fail.",
    "FT-LOG-01": "Critical logs exist and are centralized, but retention evidence is incomplete.",
    "FT-IR-01": "Incident reporting policy evidence is review-ready for the demo scope.",
}

CONTROL_TOOLS = {
    "FT-IAM-01": ("parse_csv", "iam-users.csv"),
    "FT-IAM-02": ("parse_csv", "access-review.csv"),
    "FT-DPDP-01": ("search_log_events", "dpdp consent and processing artifacts"),
    "FT-DPDP-02": ("search_text", "dpdp-encryption-policy.txt"),
    "FT-VAPT-01": ("search_text", "vapt-summary.txt"),
    "FT-LOG-01": ("search_log_events", "cloud-logging-export.log"),
    "FT-IR-01": ("search_text", "incident-response-policy.txt"),
}


def prepare_auditor_output(
    controls: list[ControlRequirement],
    compliance: ComplianceEvaluation,
    risk: RiskEvaluation,
    llm_enrichments: dict[str, dict[str, Any]] | None = None,
    regulatory_contexts: dict[str, list[dict[str, Any]]] | None = None,
) -> AuditorEvaluation:
    control_by_id = {control.id: control for control in controls}
    compliance_by_id = {
        result.control_id: result for result in compliance.control_results
    }
    enrichments = llm_enrichments or {}
    reg_contexts = regulatory_contexts or {}

    return AuditorEvaluation(
        control_results=[
            prepare_control_auditor_output(
                control=control_by_id[risk_result.control_id],
                compliance_result=compliance_by_id[risk_result.control_id],
                risk_result=risk_result,
                llm_enrichment=enrichments.get(risk_result.control_id),
                regulatory_context=reg_contexts.get(risk_result.control_id, []),
            )
            for risk_result in risk.control_results
        ]
    )


def prepare_control_auditor_output(
    control: ControlRequirement,
    compliance_result: ControlComplianceResult,
    risk_result: ControlRiskResult,
    llm_enrichment: dict[str, Any] | None = None,
    regulatory_context: list[dict[str, Any]] | None = None,
) -> ControlAuditorResult:
    llm_auditor = _run_llm_auditor(
        control=control,
        risk_result=risk_result,
        llm_enrichment=llm_enrichment,
        regulatory_context=regulatory_context or [],
    )

    return ControlAuditorResult(
        control_id=control.id,
        reviewer_question=llm_auditor.get(
            "reviewer_question",
            _reviewer_question(control=control, risk_result=risk_result),
        ),
        suggestion=llm_auditor.get(
            "suggestion",
            _suggestion(control=control, risk_result=risk_result),
        ),
        risk_summary=llm_auditor.get(
            "risk_summary",
            _risk_summary(control=control, risk_result=risk_result),
        ),
        agent_plan=_agent_plan(control=control),
        tool_trace=_tool_trace(
            control=control,
            compliance_result=compliance_result,
            risk_result=risk_result,
        ),
    )


def _reviewer_question(
    control: ControlRequirement,
    risk_result: ControlRiskResult,
) -> str:
    if risk_result.status == "Ready" and control.id in READY_QUESTION_OVERRIDES:
        return READY_QUESTION_OVERRIDES[control.id]

    return control.common_reviewer_questions[0]


def _suggestion(
    control: ControlRequirement,
    risk_result: ControlRiskResult,
) -> str:
    if control.id in SUGGESTIONS:
        return SUGGESTIONS[control.id]

    if risk_result.gaps:
        return f"Upload evidence that resolves this gap: {risk_result.gaps[0]}"

    return "Keep the cited evidence in the audit package and add execution proof when available."


def _risk_summary(
    control: ControlRequirement,
    risk_result: ControlRiskResult,
) -> str:
    if control.id in RISK_SUMMARIES:
        return RISK_SUMMARIES[control.id]

    if risk_result.status == "Ready":
        return f"{control.name} evidence is review-ready for the demo scope."

    return f"{control.name} has {len(risk_result.gaps)} audit readiness gap(s)."


def _agent_plan(control: ControlRequirement) -> list[str]:
    return [
        f"Load {control.id} requirements.",
        f"Review evidence for {control.name}.",
        "Select reviewer-facing question and remediation guidance.",
        "Generate deterministic risk summary for the report.",
    ]


def _tool_trace(
    control: ControlRequirement,
    compliance_result: ControlComplianceResult,
    risk_result: ControlRiskResult,
) -> list[ToolTraceEntry]:
    tool, tool_input = CONTROL_TOOLS.get(
        control.id,
        ("review_evidence", ", ".join(control.target_artifacts)),
    )
    result = (
        f"{risk_result.satisfied_elements}/{risk_result.total_elements} evidence "
        f"elements satisfied; status={risk_result.status}"
    )

    return [
        ToolTraceEntry(
            tool=tool,
            input=tool_input,
            result=result,
        ),
        ToolTraceEntry(
            tool="select_auditor_guidance",
            input=f"{len(risk_result.gaps)} gap(s), {compliance_result.target_chunk_count} target chunk(s)",
            result=_guidance_result(risk_result),
        ),
    ]


def _guidance_result(risk_result: ControlRiskResult) -> str:
    if risk_result.gaps:
        return risk_result.gaps[0]

    return "no gaps; preserve evidence and strengthen with execution proof"


def _run_llm_auditor(
    control: ControlRequirement,
    risk_result: ControlRiskResult,
    llm_enrichment: dict[str, Any] | None,
    regulatory_context: list[dict[str, Any]],
) -> dict[str, Any]:
    """Use LLM to generate contextual auditor output. Falls back to empty dict on failure."""
    if llm_enrichment is None:
        return {}

    try:
        from app.llm.client import llm_json
        from app.llm.prompts import AUDITOR_SYSTEM, AUDITOR_USER

        reg_lines = []
        for r in regulatory_context[:10]:
            reg_lines.append(
                f"- [{r.get('rule_id', '?')}] {r.get('framework', '?')} "
                f"§{r.get('clause_reference', '?')}: {r.get('rule_text', '')[:180]}"
            )
        reg_text = "\n".join(reg_lines) or "No regulatory context available."

        user_prompt = AUDITOR_USER.format(
            control_id=control.id,
            control_name=control.name,
            priority=control.priority,
            status=risk_result.status,
            confidence=risk_result.confidence,
            letter_score=llm_enrichment.get("letter_of_law_score", "N/A"),
            spirit_score=llm_enrichment.get("spirit_of_law_score", "N/A"),
            effort_score=llm_enrichment.get("compliance_effort_score", "N/A"),
            compliance_reasoning=llm_enrichment.get("reasoning", "No LLM reasoning available."),
            gaps=", ".join(llm_enrichment.get("gaps_identified", risk_result.gaps)) or "None",
            regulatory_context=reg_text,
            satisfied_count=risk_result.satisfied_elements,
            total_count=risk_result.total_elements,
            negative_count=risk_result.negative_hit_count,
        )

        return llm_json(system_prompt=AUDITOR_SYSTEM, user_prompt=user_prompt)
    except Exception:
        logger.warning("LLM auditor failed for %s, using deterministic fallback", control.id, exc_info=True)
        return {}
