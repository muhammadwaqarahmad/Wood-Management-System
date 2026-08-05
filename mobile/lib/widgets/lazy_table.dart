import 'package:flutter/material.dart';

/// One column definition for [LazyTable].
class TableCol {
  const TableCol(this.label, this.width, {this.numeric = false});
  final String label;
  final double width;
  final bool numeric; // right-align header + cells
}

/// A virtualized table: only the rows currently on screen are built (via
/// [ListView.builder] with a fixed [rowHeight]), so it stays fast whether there
/// are 10 rows or 10,000. Columns keep fixed widths so everything stays aligned,
/// and the whole table pans horizontally as one unit (header + rows together).
///
/// Must be given a bounded height — place it inside an [Expanded] or a SizedBox.
class LazyTable extends StatelessWidget {
  const LazyTable({
    super.key,
    required this.columns,
    required this.rowCount,
    required this.cellsBuilder,
    this.onRefresh,
    this.onRowTap,
    this.rowHeight = 48,
  });

  final List<TableCol> columns;
  final int rowCount;

  /// Builds the cells for row [index] — one widget per column, in order.
  final List<Widget> Function(int index) cellsBuilder;

  final Future<void> Function()? onRefresh;
  final void Function(int index)? onRowTap;
  final double rowHeight;

  @override
  Widget build(BuildContext context) {
    final totalWidth = columns.fold<double>(0, (s, c) => s + c.width);
    final hint = Theme.of(context).hintColor;
    final divider = Theme.of(context).dividerColor;

    Widget cell(Widget child, TableCol c) => SizedBox(
          width: c.width,
          child: Align(
            alignment: c.numeric ? Alignment.centerRight : Alignment.centerLeft,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8),
              child: child,
            ),
          ),
        );

    final header = Container(
      height: 40,
      decoration: BoxDecoration(
        border: Border(bottom: BorderSide(color: divider)),
      ),
      child: Row(
        children: [
          for (final c in columns)
            cell(
              Text(
                c.label.toUpperCase(),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 0.4,
                    color: hint),
              ),
              c,
            ),
        ],
      ),
    );

    Widget list = ListView.builder(
      itemCount: rowCount,
      itemExtent: rowHeight, // fixed extent → no per-row measuring, very fast
      itemBuilder: (ctx, i) {
        final cells = cellsBuilder(i);
        final row = DecoratedBox(
          decoration: BoxDecoration(
            border: Border(bottom: BorderSide(color: divider.withValues(alpha: 0.5))),
          ),
          child: Row(
            children: [
              for (var k = 0; k < columns.length; k++)
                cell(cells[k], columns[k]),
            ],
          ),
        );
        if (onRowTap == null) return row;
        return InkWell(onTap: () => onRowTap!(i), child: row);
      },
    );
    if (onRefresh != null) {
      list = RefreshIndicator(onRefresh: onRefresh!, child: list);
    }

    return Scrollbar(
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: SizedBox(
          width: totalWidth,
          child: Column(children: [header, Expanded(child: list)]),
        ),
      ),
    );
  }
}
