import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../i18n.dart';
import '../state/providers.dart';
import '../theme.dart';

/// Lets the user set the server address at run time — no rebuild needed when
/// the network or server IP changes. Persisted via SecureStore.
Future<void> showServerDialog(BuildContext context, WidgetRef ref) async {
  final current = ref.read(authProvider).serverUrl;
  final controller = TextEditingController(text: current);
  final saved = await showDialog<String>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text(tr(ctx, 'server_address')),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            tr(ctx, 'server_help'),
            style: TextStyle(fontSize: 13, color: Theme.of(ctx).hintColor),
          ),
          const SizedBox(height: 14),
          TextField(
            controller: controller,
            autofocus: true,
            keyboardType: TextInputType.url,
            autocorrect: false,
            enableSuggestions: false,
            decoration: const InputDecoration(
              labelText: 'http://<ip>:8000',
              prefixIcon: Icon(Icons.dns_outlined),
            ),
          ),
        ],
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx), child: Text(tr(ctx, 'cancel'))),
        FilledButton(
          onPressed: () => Navigator.pop(ctx, controller.text.trim()),
          child: Text(tr(ctx, 'save')),
        ),
      ],
    ),
  );
  if (saved != null && saved.isNotEmpty) {
    await ref.read(authProvider.notifier).setServer(saved);
    if (context.mounted) {
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(SnackBar(
          behavior: SnackBarBehavior.floating,
          backgroundColor: AppTheme.accent,
          content: Text('${tr(context, 'server_set_to')} $saved'),
        ));
    }
  }
}
