"""Auditor-ready PDF rendering for the PS3 report (ReportLab, pure-Python).

Renders a PS3ReportResponse into a paginated PDF: title, executive summary,
posture metrics, and a per-requirement section (status, frameworks, narrative,
next review, linked-evidence table, gaps).
"""

from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models.ps3 import PS3ReportResponse, RequirementReport

_STATUS_COLOR = {
    "COMPLIANT": colors.HexColor("#1f6b5a"),
    "PARTIAL": colors.HexColor("#b38a3c"),
    "GAP": colors.HexColor("#a9433a"),
}

_REPLACEMENTS = {
    "—": "-", "–": "-", "‘": "'", "’": "'",
    "“": '"', "”": '"', "…": "...", "�": "-",
    "&": "&amp;", "<": "&lt;", ">": "&gt;",
}


def _clean(text: str) -> str:
    """Escape XML and map common unicode punctuation to ASCII for ReportLab."""
    out = str(text)
    for src, dst in _REPLACEMENTS.items():
        out = out.replace(src, dst)
    return out


def _styles():
    base = getSampleStyleSheet()
    base.add(ParagraphStyle("PS3Title", parent=base["Title"], fontSize=20, spaceAfter=4))
    base.add(ParagraphStyle("PS3Sub", parent=base["Normal"], fontSize=9, textColor=colors.grey))
    base.add(ParagraphStyle("PS3H2", parent=base["Heading2"], fontSize=13, spaceBefore=10, spaceAfter=4))
    base.add(ParagraphStyle("PS3Body", parent=base["Normal"], fontSize=9.5, leading=13, alignment=TA_LEFT))
    base.add(ParagraphStyle("PS3Meta", parent=base["Normal"], fontSize=8, textColor=colors.HexColor("#555555")))
    base.add(ParagraphStyle("PS3Cell", parent=base["Normal"], fontSize=7.5, leading=9))
    return base


def render_report_pdf(report: PS3ReportResponse) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        title="Compliance Evidence Audit Report",
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    )
    s = _styles()
    story: list = []

    story.append(Paragraph("Compliance Evidence Audit Report", s["PS3Title"]))
    story.append(Paragraph(f"Generated {report.generated_at} &nbsp;·&nbsp; request {report.request_id}", s["PS3Sub"]))
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#dddddd")))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Executive Summary", s["PS3H2"]))
    story.append(Paragraph(_clean(report.summary.exec_summary), s["PS3Body"]))
    story.append(Spacer(1, 8))
    story.append(_metrics_table(report, s))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Requirements", s["PS3H2"]))
    for req in report.requirements:
        story.extend(_requirement_block(req, s))

    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#dddddd")))
    story.append(Paragraph(report.disclaimer, s["PS3Meta"]))

    doc.build(story)
    return buffer.getvalue()


def _metrics_table(report: PS3ReportResponse, s) -> Table:
    summary = report.summary
    data = [
        ["Overall compliance", "Coverage", "Evidence freshness", "Auto-collected"],
        [
            f"{summary.overall_compliance_pct:.0f}%",
            f"{summary.coverage_pct:.0f}%",
            f"{summary.freshness_pct:.0f}%",
            f"{summary.auto_collected_pct:.0f}%",
        ],
        [
            f"{summary.compliant_count} compliant",
            f"{summary.partial_count} partial",
            f"{summary.gap_count} gap",
            f"{summary.total_evidence} evidence",
        ],
    ]
    table = Table(data, colWidths=[42 * mm] * 4)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#11120f")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("FONTSIZE", (0, 1), (-1, 1), 14),
                ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
                ("TEXTCOLOR", (0, 2), (-1, 2), colors.grey),
            ]
        )
    )
    return table


def _requirement_block(req: RequirementReport, s) -> list:
    color = _STATUS_COLOR.get(req.status, colors.grey)
    flowables: list = [Spacer(1, 8)]

    header = Table(
        [[
            Paragraph(f"<b>{req.id}</b> &nbsp; {_clean(req.text)}", s["PS3Body"]),
            Paragraph(f'<font color="{color.hexval()}"><b>{req.status}</b></font>', s["PS3Body"]),
        ]],
        colWidths=[140 * mm, 28 * mm],
    )
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 1.2, color)]))
    flowables.append(header)

    flowables.append(
        Paragraph(
            f"Frameworks: {', '.join(req.frameworks) or 'n/a'} &nbsp;·&nbsp; "
            f"Audit: {req.audit_frequency} (SLA {req.freshness_sla_days}d) &nbsp;·&nbsp; "
            f"Confidence: {req.confidence:.0%} &nbsp;·&nbsp; Next review: {req.next_review_date}",
            s["PS3Meta"],
        )
    )
    flowables.append(Spacer(1, 3))
    flowables.append(Paragraph(_clean(req.narrative), s["PS3Body"]))

    if req.linked_evidence:
        flowables.append(Spacer(1, 4))
        flowables.append(_evidence_table(req, s))

    if req.gaps:
        flowables.append(Spacer(1, 3))
        for gap in req.gaps:
            flowables.append(Paragraph(f"- {_clean(gap)}", s["PS3Meta"]))

    return flowables


def _evidence_table(req: RequirementReport, s) -> Table:
    head = ["Evidence", "Type", "Collected", "Age", "Conf", "Link", "Flags"]
    rows = [head]
    for ev in req.linked_evidence:
        rows.append([
            Paragraph(ev.evidence_id, s["PS3Cell"]),
            Paragraph(ev.type, s["PS3Cell"]),
            Paragraph(ev.collection_date, s["PS3Cell"]),
            Paragraph(f"{ev.freshness_days}d", s["PS3Cell"]),
            Paragraph(f"{ev.confidence_score:.2f}", s["PS3Cell"]),
            Paragraph(f"{ev.link_confidence:.2f}", s["PS3Cell"]),
            Paragraph(", ".join(ev.flags), s["PS3Cell"]),
        ])
    table = Table(rows, colWidths=[30 * mm, 26 * mm, 22 * mm, 12 * mm, 12 * mm, 12 * mm, 34 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0ede3")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e0e0e0")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return table
