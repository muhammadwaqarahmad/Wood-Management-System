"""Qt Charts helpers — chosen over matplotlib for native Urdu/RTL text."""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCharts import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QPieSeries,
    QValueAxis,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QLabel, QWidget

from timber import i18n

_MIN_HEIGHT = 260


def _empty(title: str) -> QLabel:
    placeholder = QLabel(f"{title}\n{i18n.tr('no_data')}")
    placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
    placeholder.setMinimumHeight(_MIN_HEIGHT)
    placeholder.setStyleSheet("color: gray; border: 1px solid #ddd; border-radius: 8px;")
    return placeholder


def make_bar_chart(title: str, data: list[tuple[str, Decimal]]) -> QWidget:
    """Vertical bar chart from (label, value) pairs."""
    if not data or all(v == 0 for _, v in data):
        return _empty(title)

    bar_set = QBarSet(title)
    labels: list[str] = []
    for label, value in data:
        bar_set.append(float(value))
        labels.append(str(label))

    series = QBarSeries()
    series.append(bar_set)

    chart = QChart()
    chart.addSeries(series)
    chart.setTitle(title)
    chart.legend().setVisible(False)

    axis_x = QBarCategoryAxis()
    axis_x.append(labels)
    chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
    series.attachAxis(axis_x)

    axis_y = QValueAxis()
    chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
    series.attachAxis(axis_y)

    view = QChartView(chart)
    view.setRenderHint(QPainter.RenderHint.Antialiasing)
    view.setMinimumHeight(_MIN_HEIGHT)
    return view


def make_grouped_bar_chart(
    title: str, categories: list[str], series: dict[str, list[float]]
) -> QWidget:
    """Grouped bar chart, e.g. cash In vs Out per month."""
    if not categories or not series:
        return _empty(title)

    bar_series = QBarSeries()
    for name, values in series.items():
        bar_set = QBarSet(name)
        for v in values:
            bar_set.append(float(v))
        bar_series.append(bar_set)

    chart = QChart()
    chart.addSeries(bar_series)
    chart.setTitle(title)

    axis_x = QBarCategoryAxis()
    axis_x.append([str(c) for c in categories])
    chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
    bar_series.attachAxis(axis_x)
    axis_y = QValueAxis()
    chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
    bar_series.attachAxis(axis_y)

    view = QChartView(chart)
    view.setRenderHint(QPainter.RenderHint.Antialiasing)
    view.setMinimumHeight(_MIN_HEIGHT)
    return view


def make_pie_chart(title: str, data: list[tuple[str, Decimal]]) -> QWidget:
    """Pie chart from (label, value) pairs (negatives clamped to 0)."""
    cleaned = [(label, float(v)) for label, v in data if v and float(v) > 0]
    if not cleaned:
        return _empty(title)

    series = QPieSeries()
    for label, value in cleaned:
        sl = series.append(f"{label}", value)
        sl.setLabelVisible(True)

    chart = QChart()
    chart.addSeries(series)
    chart.setTitle(title)

    view = QChartView(chart)
    view.setRenderHint(QPainter.RenderHint.Antialiasing)
    view.setMinimumHeight(_MIN_HEIGHT)
    return view
