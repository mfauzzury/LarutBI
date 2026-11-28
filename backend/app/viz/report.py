"""Charts for workflow report steps.

Unlike chat charts, a report step says which columns to draw:
    {"type": "bar" | "hbar" | "stacked" | "line",
     "x": [label columns], "y": [value columns], "series": column for "stacked"}
All values share one axis, so only put columns with the same unit in "y".
"""
from __future__ import annotations

# Fixed order, checked for colour-blind separation. Never cycled.
_COLORS = ["#257de0", "#f47230", "#00b894", "#f2a600", "#ee7fac", "#008a17", "#6a4ce2", "#ec4647"]
_INK = "#666666"
_GRID = "#e7e7e7"
_AXIS = "#c2c2c2"


def _title(column: str) -> str:
    return column.replace("_", " ")


def build_report_chart(spec: dict | None, columns: list[str], rows: list[list]) -> dict | None:
    """Return an ECharts option, or None when the step's data cannot be charted."""
    if not spec or not rows:
        return None
    kind = spec.get("type")
    x_cols = spec.get("x") or columns[:1]
    y_cols = spec.get("y") or []
    series_col = spec.get("series")
    needed = [*x_cols, *y_cols, *([series_col] if kind == "stacked" else [])]
    if kind not in {"bar", "hbar", "stacked", "line"} or not y_cols:
        return None
    if any(name not in columns for name in needed):
        return None

    index = {name: i for i, name in enumerate(columns)}
    labels = [" - ".join(str(row[index[c]]) for c in x_cols) for row in rows]

    if kind == "stacked":
        value = index[y_cols[0]]
        names = sorted({str(row[index[series_col]]) for row in rows})
        categories = list(dict.fromkeys(labels))
        totals: dict[tuple[str, str], float] = {}
        for label, row in zip(labels, rows):
            key = (label, str(row[index[series_col]]))
            totals[key] = totals.get(key, 0) + (row[value] or 0)
        data = [(name, [totals.get((c, name)) for c in categories]) for name in names]
    else:
        categories = labels
        data = [(_title(name), [row[index[name]] for row in rows]) for name in y_cols]

    if len(data) > len(_COLORS):
        return None

    series = []
    for (name, values), color in zip(data, _COLORS):
        item: dict = {"name": name, "data": values, "itemStyle": {"color": color}}
        if kind == "line":
            item.update(type="line", symbol="circle", symbolSize=8, lineStyle={"width": 2, "color": color})
        else:
            item.update(type="bar", barMaxWidth=24, barGap="15%")
            if kind == "stacked":
                item["stack"] = "total"
                item["itemStyle"].update(borderColor="#ffffff", borderWidth=1)
            else:
                item["itemStyle"]["borderRadius"] = [0, 4, 4, 0] if kind == "hbar" else [4, 4, 0, 0]
        series.append(item)

    category_axis: dict = {
        "type": "category", "data": categories,
        "axisLine": {"lineStyle": {"color": _AXIS}}, "axisTick": {"show": False},
        "axisLabel": {"color": _INK, "hideOverlap": True},
    }
    value_axis = {
        "type": "value", "axisLabel": {"color": _INK},
        "splitLine": {"lineStyle": {"color": _GRID}},
    }
    several = len(series) > 1
    option: dict = {
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "line" if kind == "line" else "shadow"}},
        "grid": {"left": 8, "right": 24, "bottom": 8, "top": 40 if several else 16, "containLabel": True},
        "series": series,
    }
    if several:
        option["legend"] = {"top": 0, "textStyle": {"color": _INK}}
    if kind == "hbar":
        option["xAxis"] = value_axis
        option["yAxis"] = {**category_axis, "inverse": True}
    else:
        option["xAxis"] = category_axis
        option["yAxis"] = value_axis
    return option
