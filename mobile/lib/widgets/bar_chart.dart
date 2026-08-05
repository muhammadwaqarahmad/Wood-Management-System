import 'package:flutter/material.dart';

import '../api/models.dart';

/// One series in a grouped bar chart: a name, colour, and how to read its value
/// out of a bucket.
class ChartSeries {
  const ChartSeries(this.name, this.color, this.value);
  final String name;
  final Color color;
  final double Function(SeriesPoint) value;
}

/// Grouped bar chart matching the desktop: hairline grid, K/M ticks, rounded
/// bar tops, and a legend. Pure CustomPaint — native, fast.
class BarChart extends StatelessWidget {
  const BarChart({super.key, required this.data, required this.series, this.height = 220});
  final List<SeriesPoint> data;
  final List<ChartSeries> series;
  final double height;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // legend
        Wrap(
          spacing: 16,
          runSpacing: 4,
          children: [
            for (final s in series)
              Row(mainAxisSize: MainAxisSize.min, children: [
                Container(width: 10, height: 10, color: s.color),
                const SizedBox(width: 5),
                Text(s.name, style: TextStyle(fontSize: 11, color: theme.hintColor)),
              ]),
          ],
        ),
        const SizedBox(height: 10),
        SizedBox(
          height: height,
          width: double.infinity,
          child: data.isEmpty
              ? Center(
                  child: Text('No data for this period',
                      style: TextStyle(color: theme.hintColor)))
              : CustomPaint(
                  painter: _BarChartPainter(
                    data: data.length > 24 ? data.sublist(data.length - 24) : data,
                    series: series,
                    grid: theme.dividerColor,
                    muted: theme.hintColor,
                  ),
                ),
        ),
      ],
    );
  }
}

class _BarChartPainter extends CustomPainter {
  _BarChartPainter(
      {required this.data, required this.series, required this.grid, required this.muted});
  final List<SeriesPoint> data;
  final List<ChartSeries> series;
  final Color grid;
  final Color muted;

  @override
  void paint(Canvas canvas, Size size) {
    const padL = 48.0, padB = 22.0, padT = 8.0, padR = 6.0;
    final w = size.width, h = size.height;

    final vals = <double>[];
    for (final row in data) {
      for (final s in series) {
        vals.add(s.value(row));
      }
    }
    var maxV = 1.0, minV = 0.0;
    for (final v in vals) {
      if (v > maxV) maxV = v;
      if (v < minV) minV = v;
    }
    final span = (maxV - minV) == 0 ? 1.0 : (maxV - minV);

    double yy(double v) => padT + (h - padT - padB) * (1 - (v - minV) / span);

    final gridPaint = Paint()
      ..color = grid
      ..strokeWidth = 1;
    final labelStyle = TextStyle(color: muted, fontSize: 9);

    // grid + y labels
    for (var i = 0; i < 5; i++) {
      final tv = minV + span * i / 4;
      final gy = yy(tv);
      canvas.drawLine(Offset(padL, gy), Offset(w - padR, gy), gridPaint);
      final av = tv.abs();
      final lab = av >= 1e6
          ? '${(tv / 1e6).toStringAsFixed(1)}M'
          : av >= 1e3
              ? '${(tv / 1e3).toStringAsFixed(0)}K'
              : tv.toStringAsFixed(0);
      _text(canvas, lab, Offset(0, gy - 6), labelStyle, width: padL - 6, right: true);
    }

    // zero baseline
    final y0 = yy(0);
    canvas.drawLine(Offset(padL, y0), Offset(w - padR, y0),
        Paint()..color = grid..strokeWidth = 1.4);

    final n = data.length;
    final plotW = w - padL - padR;
    final groupW = plotW / (n == 0 ? 1 : n);
    final ns = series.length;
    const gap = 2.0;
    final barW = (((groupW - 8) / ns) - gap).clamp(3.0, 22.0);

    for (var i = 0; i < n; i++) {
      final row = data[i];
      final gx = padL + i * groupW + (groupW - ns * (barW + gap)) / 2;
      for (var j = 0; j < ns; j++) {
        final v = series[j].value(row);
        final top = yy(v) < y0 ? yy(v) : y0;
        final hgt = (yy(v) - y0).abs().clamp(2.0, double.infinity);
        final x = gx + j * (barW + gap);
        final r = Radius.circular((barW / 2).clamp(0, 4).toDouble());
        final rect = RRect.fromRectAndCorners(
          Rect.fromLTWH(x, top, barW, hgt),
          topLeft: v >= 0 ? r : Radius.zero,
          topRight: v >= 0 ? r : Radius.zero,
          bottomLeft: v < 0 ? r : Radius.zero,
          bottomRight: v < 0 ? r : Radius.zero,
        );
        canvas.drawRRect(rect, Paint()..color = series[j].color);
      }
      // x labels (thinned)
      if (n <= 8 || i % (n ~/ 8).clamp(1, n) == 0) {
        var lab = row.label;
        if (lab.length > 7) lab = lab.substring(5);
        _text(canvas, lab, Offset(padL + i * groupW, h - 15), labelStyle,
            width: groupW, center: true);
      }
    }
  }

  void _text(Canvas c, String s, Offset o, TextStyle style,
      {double? width, bool right = false, bool center = false}) {
    final tp = TextPainter(
      text: TextSpan(text: s, style: style),
      textDirection: TextDirection.ltr,
      textAlign: right ? TextAlign.right : center ? TextAlign.center : TextAlign.left,
    )..layout(minWidth: width ?? 0, maxWidth: width ?? double.infinity);
    tp.paint(c, o);
  }

  @override
  bool shouldRepaint(covariant _BarChartPainter old) =>
      old.data != data || old.series != series;
}
