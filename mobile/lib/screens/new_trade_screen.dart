import 'package:flutter/material.dart';

import '../i18n.dart';
import '../theme.dart';
import '../widgets/read_only.dart';

/// Mirror of the desktop "Trade" (new buy/sell) entry screen, shown so the app
/// matches the desktop — but entirely read-only: the fields are disabled and
/// the Save button is inert. Trades are entered on the desktop app.
class NewTradeScreen extends StatelessWidget {
  const NewTradeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(tr(context, 'new_trade'))),
      body: AbsorbPointer(
        // Nothing here is interactive — the whole form is view-only.
        child: Opacity(
          opacity: 0.6,
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              _banner(context),
              const SizedBox(height: 16),
              _field(context, 'Type', 'Purchase / Sale', Icons.swap_vert),
              _field(context, 'Party', 'Select supplier / factory', Icons.person_outline),
              _field(context, 'Wood type', 'Select wood type', Icons.forest_outlined),
              _field(context, 'Weight (kg)', '0', Icons.scale_outlined),
              _field(context, 'Rate', '0', Icons.sell_outlined),
              _field(context, 'Freight', '0', Icons.local_shipping_outlined),
              _field(context, 'Vehicle no.', '', Icons.directions_car_outlined),
              const SizedBox(height: 16),
              FilledButton.icon(
                onPressed: null, // disabled
                icon: const Icon(Icons.save),
                label: Text(tr(context, 'save_trade')),
              ),
            ],
          ),
        ),
      ),
      // The only live control: it explains why the form is disabled.
      floatingActionButton:
          DisabledFab(icon: Icons.lock, label: tr(context, 'view_only')),
    );
  }

  Widget _banner(BuildContext context) => Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: AppTheme.accent.withValues(alpha: 0.10),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Row(children: [
          const Icon(Icons.lock_outline, color: AppTheme.accent),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              tr(context, 'trade_desktop_note'),
              style: TextStyle(color: Theme.of(context).textTheme.bodyMedium?.color),
            ),
          ),
        ]),
      );

  Widget _field(BuildContext context, String label, String hint, IconData icon) =>
      Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: TextField(
          enabled: false,
          decoration: InputDecoration(
            labelText: label,
            hintText: hint,
            prefixIcon: Icon(icon),
          ),
        ),
      );
}
