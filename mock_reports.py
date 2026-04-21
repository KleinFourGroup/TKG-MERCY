"""
Planning artifact for MERCY Steps 18 + 19.

Generates three mock PDFs into ./mock_reports/ demonstrating different designs
for the productivity-rate report (Step 18) with embedded reportlab-native charts
(Step 19). Hardcoded data, not production code — this exists so the team can
compare layouts and pick one.

Run: ./Scripts/python.exe mock_reports.py

See MERGE_PLAN.md §13.5 / §13.6 for context. Note that these reports feed
costing globals; they are NOT an HR/performance dashboard.
"""
import os

from reportlab.graphics.shapes import Drawing, String
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.legends import Legend
from reportlab.lib import colors
from reportlab.lib.units import inch

from report import PDFReport


OUTPUT_DIR = "mock_reports"


# ---- Mock data ---------------------------------------------------------------

PARTS = ["Widget A", "Widget B", "Bracket C", "Gear D"]
ACTIONS = ["Pressing", "Sanding", "Finishing"]

# (part, action) -> {employee: (qty, hours)}
MOCK = {
    ("Widget A", "Pressing"):   {"Alice": (200, 4.0), "Bob": (180, 3.5), "Carol": (210, 4.0)},
    ("Widget A", "Sanding"):    {"Bob": (150, 5.0), "Dan": (170, 5.5)},
    ("Widget A", "Finishing"):  {"Alice": (120, 4.5), "Carol": (110, 4.0)},
    ("Widget B", "Pressing"):   {"Alice": (260, 4.0), "Bob": (240, 4.0)},
    ("Widget B", "Sanding"):    {"Carol": (195, 6.0), "Dan": (180, 5.5)},
    ("Widget B", "Finishing"):  {"Alice": (140, 4.5), "Dan": (130, 4.5)},
    ("Bracket C", "Pressing"):  {"Bob": (320, 4.0), "Carol": (300, 4.0)},
    ("Bracket C", "Finishing"): {"Alice": (175, 4.5), "Carol": (165, 4.0)},
    ("Gear D", "Pressing"):     {"Dan": (90, 4.0), "Alice": (100, 4.5)},
    ("Gear D", "Sanding"):      {"Bob": (70, 5.0), "Dan": (75, 5.0)},
}

# "Fleet average" (all-time baseline) for comparison columns.
FLEET_AVG = {"Pressing": 52.0, "Sanding": 32.5, "Finishing": 29.0}


def avgRate(part: str, action: str):
    rows = MOCK.get((part, action))
    if not rows:
        return None, 0.0, 0.0
    totalQ = sum(q for (q, _) in rows.values())
    totalH = sum(h for (_, h) in rows.values())
    if totalH <= 0:
        return None, totalQ, totalH
    return totalQ / totalH, totalQ, totalH


# ---- Chart helpers -----------------------------------------------------------

PALETTE = [
    colors.HexColor("#4C72B0"),
    colors.HexColor("#DD8452"),
    colors.HexColor("#55A868"),
    colors.HexColor("#C44E52"),
]


def groupedBarChart(categories, seriesLabels, seriesData, title=None,
                    width=460, height=220):
    """
    categories: x-axis labels
    seriesLabels: one label per series (used in legend)
    seriesData: list parallel to seriesLabels; each item parallel to categories
    """
    extra = 22 if title else 0
    d = Drawing(width, height + extra)

    if title:
        d.add(String(width / 2, height + 6, title,
                     textAnchor="middle", fontName="Times-Bold", fontSize=11))

    chart = VerticalBarChart()
    chart.x = 55
    chart.y = 30
    chart.width = width - 110
    chart.height = height - 50
    chart.data = seriesData
    chart.categoryAxis.categoryNames = categories
    chart.categoryAxis.labels.boxAnchor = "n"
    chart.categoryAxis.labels.fontSize = 8
    chart.valueAxis.valueMin = 0
    chart.valueAxis.labels.fontSize = 8
    chart.groupSpacing = 12
    chart.barSpacing = 1

    for i, _ in enumerate(seriesData):
        chart.bars[i].fillColor = PALETTE[i % len(PALETTE)]
        chart.bars[i].strokeColor = colors.black
        chart.bars[i].strokeWidth = 0.25

    d.add(chart)

    legend = Legend()
    legend.x = width - 8
    legend.y = height - 6
    legend.boxAnchor = "ne"
    legend.colorNamePairs = [
        (PALETTE[i % len(PALETTE)], label) for i, label in enumerate(seriesLabels)
    ]
    legend.fontName = "Times-Roman"
    legend.fontSize = 8
    legend.columnMaximum = len(seriesLabels)
    legend.deltay = 10
    d.add(legend)

    return d


def drawChart(report: PDFReport, drawing: Drawing):
    """Centered placement of a Drawing at the report's current y-cursor."""
    h = drawing.height
    if report.lastLine - h < report.bottom:
        report.nextPage()
    y = report.lastLine - h
    x = report.left + (report.right - report.left - drawing.width) / 2.0
    drawing.drawOn(report.pdf, x, y)
    report.lastLine -= h + report.fontSize * report.lineSpace * 0.5


# ---- Mock 1: Part × Action primary, employee sub-rows ------------------------

def mock1_PartActionPrimary(path: str):
    r = PDFReport(db=None, path=path)
    r.setupPage()
    r.drawTitle("Productivity Rates — by Part & Action")
    r.drawText("Design A · Hierarchical · Period: mock data")
    r.skipLines(0.5)
    r.drawParagraph(
        "Primary cut is (part, action). Each group shows the aggregate rate "
        "— the number that would feed the costing global — plus per-employee "
        "sub-rows to indicate spread. Employee rows are for judging spread, "
        "not for ranking. Read: 'Widget A pressing averages X u/hr across "
        "these three people.'"
    )
    r.skipLines(0.5)

    # Grouped bar: x = part, bar per action
    categories = PARTS
    seriesData = []
    for action in ACTIONS:
        row = []
        for part in PARTS:
            rate, _, _ = avgRate(part, action)
            row.append(round(rate, 1) if rate is not None else 0)
        seriesData.append(row)

    drawChart(r, groupedBarChart(
        categories, ACTIONS, seriesData,
        title="Aggregate rate (units/hr) by part, grouped by action",
    ))
    r.skipLines(0.5)

    headers = ["Part", "Action", "Employee", "Qty", "Hours", "Rate (u/hr)"]
    widths = [inch * 1.1, inch * 1.0, inch * 1.2, inch * 0.7, inch * 0.7, inch * 0.9]
    data = []
    for part in PARTS:
        for action in ACTIONS:
            rows = MOCK.get((part, action))
            if not rows:
                continue
            rate, totalQ, totalH = avgRate(part, action)
            data.append([
                part, action, "— all —",
                f"{totalQ:g}", f"{totalH:g}",
                f"{rate:.1f}" if rate is not None else "-",
            ])
            for emp, (q, h) in rows.items():
                data.append([
                    "", "", emp,
                    f"{q:g}", f"{h:g}",
                    f"{q / h:.1f}" if h > 0 else "-",
                ])
    r.drawTable(data, headers, widths)
    r.pdf.save()


# ---- Mock 2: Flat rollup with fleet-average comparison -----------------------

def mock2_FleetComparison(path: str):
    r = PDFReport(db=None, path=path)
    r.setupPage()
    r.drawTitle("Productivity Rates — Rollup vs Fleet Average")
    r.drawText("Design B · Flat · Period: mock data")
    r.skipLines(0.5)
    r.drawParagraph(
        "One row per (part, action). Current-period rate sits next to the "
        "fleet all-time average so shifts are visible at a glance. Good for "
        "answering 'is sanding Widget B getting slower?' — the delta column "
        "is the signal."
    )
    r.skipLines(0.5)

    # Bar chart: two bars per (part,action) — current vs fleet
    categories = []
    currentSeries = []
    fleetSeries = []
    for part in PARTS:
        for action in ACTIONS:
            rate, _, totalH = avgRate(part, action)
            if rate is None:
                continue
            categories.append(f"{part[:6]}·{action[:3]}")
            currentSeries.append(round(rate, 1))
            fleetSeries.append(FLEET_AVG[action])

    drawChart(r, groupedBarChart(
        categories, ["Current", "Fleet avg"], [currentSeries, fleetSeries],
        title="Current-period rate vs fleet average (units/hr)",
    ))
    r.skipLines(0.5)

    headers = ["Part", "Action", "Qty", "Hours", "Rate", "Fleet avg", "Δ vs fleet"]
    widths = [inch * 1.1, inch * 1.0, inch * 0.7, inch * 0.7,
              inch * 0.7, inch * 0.8, inch * 0.9]
    data = []
    for part in PARTS:
        for action in ACTIONS:
            rate, totalQ, totalH = avgRate(part, action)
            if rate is None:
                continue
            fleet = FLEET_AVG[action]
            delta = rate - fleet
            sign = "+" if delta >= 0 else ""
            data.append([
                part, action,
                f"{totalQ:g}", f"{totalH:g}",
                f"{rate:.1f}",
                f"{fleet:.1f}",
                f"{sign}{delta:.1f} ({sign}{(delta / fleet) * 100:.0f}%)",
            ])
    r.drawTable(data, headers, widths)
    r.pdf.save()


# ---- Mock 3: Action × Part matrix --------------------------------------------

def mock3_ActionMatrix(path: str):
    r = PDFReport(db=None, path=path)
    r.setupPage()
    r.drawTitle("Productivity Rates — Action × Part Matrix")
    r.drawText("Design C · Matrix · Period: mock data")
    r.skipLines(0.5)
    r.drawParagraph(
        "Rows are actions, columns are parts. Each cell is the aggregate "
        "rate in units/hour. Densest view — good for spotting that 'sanding "
        "is slow everywhere' vs 'just slow on Widget B'. Blank cells are "
        "combinations that never occur (e.g. no sanding on brackets)."
    )
    r.skipLines(0.5)

    # Chart: x = action, grouped bars per part
    categories = ACTIONS
    seriesData = []
    for part in PARTS:
        row = []
        for action in ACTIONS:
            rate, _, _ = avgRate(part, action)
            row.append(round(rate, 1) if rate is not None else 0)
        seriesData.append(row)

    drawChart(r, groupedBarChart(
        categories, PARTS, seriesData,
        title="Rate (units/hr) by action, grouped by part",
    ))
    r.skipLines(0.5)

    headers = ["Action"] + PARTS + ["Fleet avg"]
    widths = [inch * 1.1] + [inch * 0.9] * len(PARTS) + [inch * 0.9]
    data = []
    for action in ACTIONS:
        row = [action]
        for part in PARTS:
            rate, _, _ = avgRate(part, action)
            row.append(f"{rate:.1f}" if rate is not None else "—")
        row.append(f"{FLEET_AVG[action]:.1f}")
        data.append(row)
    r.drawTable(data, headers, widths)

    r.skipLines(0.5)
    r.drawParagraph(
        "Costing implication: the matrix view is most convenient to read "
        "back when populating costing globals, since the globals are keyed "
        "by (action, part) already. One-to-one with how the numbers are "
        "consumed downstream."
    )
    r.pdf.save()


# ---- Entry point -------------------------------------------------------------

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    outputs = [
        ("mock_A_part_action_primary.pdf", mock1_PartActionPrimary),
        ("mock_B_fleet_comparison.pdf",    mock2_FleetComparison),
        ("mock_C_action_matrix.pdf",       mock3_ActionMatrix),
    ]
    for filename, fn in outputs:
        path = os.path.join(OUTPUT_DIR, filename)
        fn(path)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
