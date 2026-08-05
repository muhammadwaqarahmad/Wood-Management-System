import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../i18n.dart';
import '../state/providers.dart';
import '../widgets/auth_shell.dart';

/// Shown when a saved session exists but is locked behind biometrics.
/// Auto-prompts fingerprint/face on open; offers a password fallback.
class LockScreen extends ConsumerStatefulWidget {
  const LockScreen({super.key});
  @override
  ConsumerState<LockScreen> createState() => _LockScreenState();
}

class _LockScreenState extends ConsumerState<LockScreen> {
  @override
  void initState() {
    super.initState();
    // Prompt as soon as the screen appears.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(authProvider.notifier).unlockWithBiometric();
    });
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authProvider);
    final label = auth.biometricLabel;
    final icon = label.contains('Face') ? Icons.face_retouching_natural : Icons.fingerprint;

    return AuthShell(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (auth.lastUsername != null)
            Text('${tr(context, 'signed_in_as')} ${auth.lastUsername}',
                textAlign: TextAlign.center,
                style: TextStyle(color: Theme.of(context).hintColor)),
          const SizedBox(height: 16),
          Icon(icon, size: 64, color: Theme.of(context).colorScheme.primary),
          const SizedBox(height: 14),
          Text('${tr(context, 'unlock_with')} $label',
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
          if (auth.error != null) ...[
            const SizedBox(height: 10),
            Text(auth.error!,
                textAlign: TextAlign.center,
                style: TextStyle(color: Theme.of(context).colorScheme.error, fontSize: 13)),
          ],
          const SizedBox(height: 22),
          FilledButton.icon(
            onPressed: auth.loading
                ? null
                : () => ref.read(authProvider.notifier).unlockWithBiometric(),
            style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(48)),
            icon: auth.loading
                ? const SizedBox(
                    width: 18, height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                : Icon(icon),
            label: Text(auth.loading ? tr(context, 'unlocking') : tr(context, 'unlock')),
          ),
          const SizedBox(height: 8),
          TextButton(
            onPressed: () => ref.read(authProvider.notifier).logout(),
            child: Text(tr(context, 'use_password')),
          ),
        ],
      ),
    );
  }
}
