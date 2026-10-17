"""Private, bounded reporting. Configuration/data/rendering/delivery stay separate."""

import csv, hashlib, io, json, threading
from contextlib import contextmanager
from datetime import timezone
from pathlib import Path
from html import escape
from flask import g, abort
from sqlalchemy import select, or_, and_
from olumira.extensions import db
from olumira.models import (
    CareProfile,
    Observation,
    RoutineSession,
    CaregiverTask as Task,
    CaregiverHandoff as Handoff,
)
from services import insights
from services.journal import aware
from services.workspaces import require

SECTIONS = {
    "overview": "Overview",
    "routines": "Routine completions and trends",
    "observations": "Observation summary",
    "details": "Observation details",
    "tasks": "Completed caregiver tasks",
    "handoffs": "Handoffs created in the period",
}
MAX_ROWS = 500
MAX_TEXT_UNITS = 100_000


def configure(values, sections):
    require("reports.generate")
    title = (values.get("title") or "").strip()
    if not title or len(title) > 120 or any(ord(c) < 32 for c in title):
        raise ValueError(
            "Enter a report title of 1–120 characters without control characters."
        )
    selected = [key for key in SECTIONS if key in sections]
    if not selected or any(key not in SECTIONS for key in sections):
        raise ValueError("Choose at least one valid report section.")
    output = values.get("format", "pdf")
    if output not in ["pdf", "csv"]:
        raise ValueError("Choose PDF or CSV.")
    if values.get("scope_workspace") != g.workspace_id:
        raise ValueError("Your workspace changed. Reopen the report builder.")
    profile_id = values.get("profile_id") or None
    if profile_id and not db.session.scalar(
        select(CareProfile.id).where(
            CareProfile.id == profile_id, CareProfile.workspace_id == g.workspace_id
        )
    ):
        abort(404)
    category = (values.get("category") or "").strip()
    if len(category) > 60:
        raise ValueError("Choose a category of up to 60 characters.")
    return dict(
        title=title,
        sections=selected,
        format=output,
        profile_id=profile_id,
        period=insights.period(values),
        category=category,
    )


@contextmanager
def profile_scope(identity):
    original = (g.profile_id, g.profile)
    g.profile_id = identity
    g.profile = db.session.get(CareProfile, identity) if identity else None
    try:
        yield
    finally:
        g.profile_id, g.profile = original


def iso(value):
    return aware(value).astimezone(timezone.utc).isoformat() if value else ""


def build(config):
    require("reports.generate")
    with profile_scope(config["profile_id"]):
        p = config["period"]
        data = insights.calculate(p, config["category"])
        result = dict(
            title=config["title"],
            profile=g.profile.display_name if g.profile else "Workspace-wide records",
            period=p.label,
            sections=config["sections"],
            format=config["format"],
            category=config["category"],
            generated_at=iso(data["generated_at"]),
            analytics=data,
            datasets={},
        )
        remaining = MAX_ROWS

        def collect(key, query, convert):
            nonlocal remaining
            rows = list(db.session.scalars(query.limit(remaining + 1)))
            if len(rows) > remaining:
                raise ValueError(
                    f"This report exceeds the {MAX_ROWS}-record export limit. Shorten the date range or select fewer detail sections; no records were exported."
                )
            remaining -= len(rows)
            result["datasets"][key] = [convert(row) for row in rows]

        if "routines" in config["sections"]:
            collect(
                "routines",
                select(RoutineSession)
                .where(
                    insights.scoped(RoutineSession),
                    RoutineSession.status == "completed",
                    insights.interval(RoutineSession.completed_at, p),
                )
                .order_by(RoutineSession.completed_at, RoutineSession.id),
                lambda r: dict(
                    id=r.id,
                    title=r.title,
                    completed_at_utc=iso(r.completed_at),
                    scheduled="yes" if r.occurrence_id else "no",
                ),
            )
        if "details" in config["sections"]:
            query = select(Observation).where(
                insights.scoped(Observation),
                Observation.archived_at.is_(None),
                or_(
                    insights.interval(Observation.observed_at, p),
                    and_(
                        Observation.observed_at.is_(None),
                        Observation.date >= p.first.isoformat(),
                        Observation.date <= p.last.isoformat(),
                    ),
                ),
            )
            if config["category"]:
                query = query.where(Observation.category == config["category"])
            collect(
                "observations",
                query.order_by(
                    Observation.date, Observation.observed_at, Observation.id
                ),
                lambda r: dict(
                    id=str(r.id),
                    title=r.activity,
                    category=r.category,
                    observed_at_utc=iso(r.observed_at),
                    original_date=r.date,
                    clock_time="known" if r.observed_at else "unknown",
                    recorded_at_utc=iso(r.created_at),
                    description=r.notes or "",
                    tags=r.tags or "",
                    author_id=r.author_id or "unknown (legacy)",
                    session_id=r.session_id or "",
                    task_id=r.task_id or "",
                ),
            )
        if "observations" in result["datasets"]:
            rows = result["datasets"]["observations"]
            from olumira.models import User

            ids = [r["author_id"] for r in rows if r["author_id"] != "unknown (legacy)"]
            authors = (
                dict(
                    db.session.execute(
                        select(User.id, User.display_name).where(User.id.in_(ids))
                    ).all()
                )
                if ids
                else {}
            )
            for row in rows:
                row["author"] = authors.get(
                    row.pop("author_id"), "Unknown (legacy record)"
                )
        if "tasks" in config["sections"]:
            collect(
                "tasks",
                select(Task)
                .where(
                    insights.scoped(Task),
                    Task.status == "completed",
                    insights.interval(Task.completed_at, p),
                )
                .order_by(Task.completed_at, Task.id),
                lambda r: dict(
                    id=r.id,
                    title=r.title,
                    description=r.description,
                    completed_at_utc=iso(r.completed_at),
                    status=r.status,
                ),
            )
        if "handoffs" in config["sections"]:
            collect(
                "handoffs",
                select(Handoff)
                .where(
                    insights.scoped(Handoff), insights.interval(Handoff.created_at, p)
                )
                .order_by(Handoff.created_at, Handoff.id),
                lambda r: dict(
                    id=r.id, summary=r.summary, created_at_utc=iso(r.created_at)
                ),
            )
        if "handoffs" in config["sections"] and result["datasets"]["handoffs"]:
            from olumira.models import HandoffRecipient
            from sqlalchemy import func

            ids = [r["id"] for r in result["datasets"]["handoffs"]]
            counts = {
                identity: (total, ack)
                for identity, total, ack in db.session.execute(
                    select(
                        HandoffRecipient.handoff_id,
                        func.count(),
                        func.count(HandoffRecipient.acknowledged_at),
                    )
                    .where(HandoffRecipient.handoff_id.in_(ids))
                    .group_by(HandoffRecipient.handoff_id)
                )
            }
            for row in result["datasets"]["handoffs"]:
                total, ack = counts.get(row["id"], (0, 0))
                row["recipients"] = str(total)
                row["acknowledged_now"] = str(ack)
        text_units = sum(
            len(str(value)) + 20 * str(value).count("\n")
            for rows in result["datasets"].values()
            for row in rows
            for value in row.values()
        )
        if text_units > MAX_TEXT_UNITS:
            raise ValueError(
                "This report contains too much detailed text for an interactive export. Shorten the date range or choose fewer detail sections; no records were exported."
            )
        return result


def fingerprint(report):
    # No content is stored in a URL or a cookie. Reject download if records changed
    # since preview rather than exporting a different report silently.
    payload = dict(report)
    payload.pop("generated_at")
    data = dict(payload["analytics"])
    data.pop("generated_at")
    data["period"] = data["period"].label
    payload["analytics"] = data
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


def safe_cell(value):
    text = str(value)
    # Excel can ignore leading spaces/control characters before a formula.
    import re

    stripped = re.sub(r"^[\s\x00-\x1f\ufeff]+", "", text)
    if stripped.startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


def csv_bytes(report):
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(["dataset", "record_id", "field", "value"])

    def emit(dataset, identity, values):
        for key, value in values.items():
            writer.writerow(
                [
                    safe_cell(dataset),
                    safe_cell(identity),
                    safe_cell(key),
                    safe_cell(value),
                ]
            )

    emit(
        "report",
        "",
        dict(
            title=report["title"],
            profile=report["profile"],
            period=report["period"],
            generated_at_utc=report["generated_at"],
            observation_category=report["category"] or "all",
            informational_use="Family coordination and recordkeeping; not a clinical assessment.",
        ),
    )
    data = report["analytics"]
    if "overview" in report["sections"]:
        emit(
            "overview",
            "",
            dict(
                data["stats"],
                scheduled_completion_rate="unavailable",
                scheduled_completion_rate_reason=data["completion_rate"]["reason"],
            ),
        )
    if "observations" in report["sections"]:
        emit(
            "observation_summary",
            "",
            dict(
                known_time=data["stats"]["observations"],
                date_only=data["stats"]["date_only_observations"],
            ),
        )
        for category, count in data["categories"]:
            emit("observation_category", category, dict(count=count))
    if "routines" in report["sections"]:
        for point in data["chart"]:
            emit(
                "routine_trend",
                point["label"],
                dict(completed_sessions=point["routines"]),
            )
    if "observations" in report["sections"]:
        for point in data["chart"]:
            emit(
                "observation_trend",
                point["label"],
                dict(known_time_observations=point["observations"]),
            )
    for dataset, rows in report["datasets"].items():
        for row in rows:
            emit(dataset, row["id"], {k: v for k, v in row.items() if k != "id"})
    for label, definition in insights.DEFINITIONS:
        emit("metric_definition", label, dict(definition=definition))
    return ("\ufeff" + output.getvalue()).encode("utf-8")


_font_lock = threading.Lock()


def pdf_bytes(report):
    from reportlab import rl_config
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
        KeepTogether,
    )
    from reportlab.lib.pagesizes import A4
    import reportlab

    with _font_lock:
        if "Olumira" not in pdfmetrics.getRegisteredFontNames():
            fonts = Path(__file__).resolve().parents[1] / "assets" / "fonts"
            pdfmetrics.registerFont(
                TTFont("Olumira", str(fonts / "NotoSans-Regular.ttf"))
            )
            pdfmetrics.registerFont(
                TTFont("OlumiraBold", str(fonts / "NotoSans-Bold.ttf"))
            )
            pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
            pdfmetrics.registerFontFamily(
                "Olumira",
                normal="Olumira",
                bold="OlumiraBold",
                italic="Olumira",
                boldItalic="OlumiraBold",
            )
    available = pdfmetrics.getFont("Olumira").face.charToGlyph

    def text(value):
        pieces = []
        for char in str(value):
            n = ord(char)
            if char == "\n":
                pieces.append("<br/>")
            elif char == "\t":
                pieces.append("    ")
            elif n in available:
                pieces.append(escape(char))
            elif 0x3000 <= n <= 0x9FFF:
                pieces.append('<font name="STSong-Light">' + escape(char) + "</font>")
            else:
                pieces.append(f"[U+{n:04X}]")
        return "".join(pieces)

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="CareBody",
            fontName="Olumira",
            fontSize=9,
            leading=14,
            textColor=colors.HexColor("#254638"),
            spaceAfter=8,
            wordWrap="CJK",
        )
    )
    styles.add(
        ParagraphStyle(
            name="CareTitle",
            parent=styles["CareBody"],
            fontName="OlumiraBold",
            fontSize=23,
            leading=29,
            spaceAfter=16,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CareHeading",
            parent=styles["CareBody"],
            fontName="OlumiraBold",
            fontSize=14,
            leading=20,
            spaceBefore=14,
            spaceAfter=10,
            keepWithNext=True,
        )
    )

    def para(value, style="CareBody"):
        return Paragraph(text(value), styles[style])

    stream = io.BytesIO()
    doc = SimpleDocTemplate(
        stream,
        pagesize=A4,
        rightMargin=42,
        leftMargin=42,
        topMargin=54,
        bottomMargin=62,
        title="Olumira caregiver report",
        author="Olumira",
        pageCompression=1,
    )
    content = [
        para("OLUMIRA", "CareHeading"),
        para(report["title"], "CareTitle"),
        para(report["profile"]),
        para(report["period"]),
        para("Generated (UTC): " + report["generated_at"]),
        para(
            "Informational use for family coordination and recordkeeping. Not a clinical assessment or diagnosis."
        ),
        para("Observation category: " + (report["category"] or "All categories")),
    ]
    data = report["analytics"]

    def heading(label):
        content.append(para(label, "CareHeading"))

    def table(rows, widths=None):
        t = Table(
            [[para(value) for value in row] for row in rows],
            colWidths=widths,
            repeatRows=1,
            hAlign="LEFT",
        )
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e7f1eb")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#ccdcd2")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        content.append(t)

    if "overview" in report["sections"]:
        heading("Overview")
        table(
            [["Metric", "Value"]]
            + [
                [key.replace("_", " ").capitalize(), str(value)]
                for key, value in data["stats"].items()
            ],
            [370, 140],
        )
        content.append(
            para("Scheduled completion rate: " + data["completion_rate"]["reason"])
        )
    if "routines" in report["sections"] or "observations" in report["sections"]:
        heading("Activity trends")
        headers = ["Period"]
        keys = []
        if "routines" in report["sections"]:
            headers.append("Guided completions")
            keys.append("routines")
        if "observations" in report["sections"]:
            headers.append("Known-time observations")
            keys.append("observations")
        table(
            [headers]
            + [[p["label"]] + [str(p[k]) for k in keys] for p in data["chart"]],
            [230] + [280 / len(keys)] * len(keys),
        )
    if "observations" in report["sections"]:
        heading("Observation summary")
        content.append(
            para(
                f"Known-time observations: {data['stats']['observations']}. Date-only entries with unknown clock time: {data['stats']['date_only_observations']}."
            )
        )
        table(
            [["Category", "Count"]]
            + [[category, str(count)] for category, count in data["categories"]],
            [370, 140],
        )
    for dataset, rows in report["datasets"].items():
        heading(
            {
                "routines": "Completed guided routines",
                "observations": "Observation details",
                "tasks": "Completed caregiver tasks",
                "handoffs": "Handoffs created during the period",
            }[dataset]
        )
        if not rows:
            content.append(para("No matching records."))
        for row in rows:
            # Long descriptions remain splittable paragraphs; headings stay with
            # their metadata. Never put an unbounded note in one table row.
            content.append(
                para(row.get("title", f"Handoff {row['id'][:8]}"), "CareHeading")
            )
            for key, value in row.items():
                if key not in ["title", "id"] and value:
                    content.append(
                        para(key.replace("_", " ").capitalize() + ": " + str(value))
                    )
    heading("Metric definitions and document notes")
    for label, definition in insights.DEFINITIONS:
        content.append(para(label + ": " + definition))
    content.append(
        para(
            "This PDF is not tagged for PDF/UA. The HTML preview and CSV offer accessible alternatives. Unsupported glyphs are represented by their Unicode code point, for example [U+1F331]; supported CJK characters use a PDF standard CJK font. Text shaping for complex scripts is not provided."
        )
    )

    def footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#ccdcd2"))
        canvas.line(42, 44, A4[0] - 42, 44)
        canvas.setFont("Olumira", 8)
        canvas.setFillColor(colors.HexColor("#254638"))
        canvas.drawString(
            42,
            31,
            "Olumira | Informational family record | " + report["generated_at"][:10],
        )
        canvas.drawRightString(A4[0] - 42, 31, f"Page {document.page}")
        canvas.restoreState()

    doc.build(content, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()
