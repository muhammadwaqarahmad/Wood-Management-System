import 'package:flutter/material.dart';

import '../i18n.dart';
import '../theme.dart';

/// Tells the user why a write action is unavailable. The mobile app is
/// deliberately read-only — data is entered on the desktop app.
void readOnlySnack(BuildContext context) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(
      behavior: SnackBarBehavior.floating,
      content: Row(children: [
        const Icon(Icons.lock_outline, size: 18, color: Colors.white),
        const SizedBox(width: 10),
        Expanded(child: Text(tr(context, 'view_only_msg'))),
      ]),
    ));
}

/// A write button (e.g. "Add Payment") rendered so the screen matches the
/// desktop, but dimmed with a small lock and inert: tapping only explains that
/// the app is read-only. It never opens a form.
class DisabledFab extends StatelessWidget {
  const DisabledFab({super.key, required this.icon, required this.label});
  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Opacity(
      opacity: 0.55,
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          FloatingActionButton.extended(
            heroTag: label,
            onPressed: () => readOnlySnack(context),
            backgroundColor: AppTheme.accent,
            foregroundColor: Colors.white,
            icon: Icon(icon),
            label: Text(label),
          ),
          Positioned(
            top: -4,
            right: -4,
            child: Container(
              padding: const EdgeInsets.all(3),
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.surface,
                shape: BoxShape.circle,
                border: Border.all(color: Theme.of(context).dividerColor),
              ),
              child: Icon(Icons.lock, size: 12, color: Theme.of(context).hintColor),
            ),
          ),
        ],
      ),
    );
  }
}

/// Inline dimmed pill used where the desktop shows an edit/action button inside
/// a row or toolbar. Inert, with a lock glyph.
class DisabledActionChip extends StatelessWidget {
  const DisabledActionChip({super.key, required this.icon, required this.label});
  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Opacity(
      opacity: 0.5,
      child: OutlinedButton.icon(
        onPressed: () => readOnlySnack(context),
        icon: Icon(icon, size: 16),
        label: Text(label),
        style: OutlinedButton.styleFrom(
          foregroundColor: Theme.of(context).hintColor,
          side: BorderSide(color: Theme.of(context).dividerColor),
        ),
      ),
    );
  }
}
