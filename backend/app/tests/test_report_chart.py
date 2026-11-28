from app.viz.report import build_report_chart

COLUMNS = ["project", "kind", "total"]
ROWS = [["P1", "No PO", 10], ["P1", "Variance", 5], ["P2", "No PO", 7]]


def test_stacked_chart_pivots_rows_into_series():
    chart = build_report_chart(
        {"type": "stacked", "x": ["project"], "y": ["total"], "series": "kind"}, COLUMNS, ROWS
    )
    assert chart["xAxis"]["data"] == ["P1", "P2"]
    assert [(s["name"], s["data"]) for s in chart["series"]] == [
        ("No PO", [10, 7]),
        ("Variance", [5, None]),
    ]
    assert "legend" in chart


def test_single_series_has_no_legend_and_joins_label_columns():
    chart = build_report_chart({"type": "hbar", "x": ["project", "kind"], "y": ["total"]}, COLUMNS, ROWS)
    assert chart["yAxis"]["data"][0] == "P1 - No PO"
    assert "legend" not in chart


def test_no_chart_for_missing_spec_columns_or_rows():
    assert build_report_chart(None, COLUMNS, ROWS) is None
    assert build_report_chart({"type": "bar", "y": ["nope"]}, COLUMNS, ROWS) is None
    assert build_report_chart({"type": "bar", "y": ["total"]}, COLUMNS, []) is None
