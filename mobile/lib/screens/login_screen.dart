import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../i18n.dart';
import '../state/providers.dart';
import '../theme.dart';
import '../widgets/auth_shell.dart';
import '../widgets/server_dialog.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});
  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _user = TextEditingController();
  final _pass = TextEditingController();
  bool _obscure = true;
  bool _prefilled = false;

  @override
  void dispose() {
    _user.dispose();
    _pass.dispose();
    super.dispose();
  }

  void _submit() {
    FocusScope.of(context).unfocus();
    ref.read(authProvider.notifier).login(_user.text.trim(), _pass.text);
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authProvider);
    if (!_prefilled && auth.lastUsername != null && _user.text.isEmpty) {
      _user.text = auth.lastUsername!;
      _prefilled = true;
    }

    return AuthShell(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(tr(context, 'sign_in'),
              style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
          const SizedBox(height: 18),
          TextField(
            controller: _user,
            textInputAction: TextInputAction.next,
            autocorrect: false,
            enableSuggestions: false,
            decoration: InputDecoration(
              labelText: tr(context, 'username'),
              prefixIcon: const Icon(Icons.person_outline),
            ),
          ),
          const SizedBox(height: 14),
          TextField(
            controller: _pass,
            obscureText: _obscure,
            onSubmitted: (_) => _submit(),
            decoration: InputDecoration(
              labelText: tr(context, 'password'),
              prefixIcon: const Icon(Icons.lock_outline),
              suffixIcon: IconButton(
                icon: Icon(_obscure ? Icons.visibility_off : Icons.visibility),
                onPressed: () => setState(() => _obscure = !_obscure),
              ),
            ),
          ),
          if (auth.error != null) ...[
            const SizedBox(height: 14),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: AppTheme.bad.withValues(alpha: 0.10),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Row(children: [
                const Icon(Icons.error_outline, color: AppTheme.bad, size: 20),
                const SizedBox(width: 8),
                Expanded(
                    child: Text(auth.error!, style: const TextStyle(color: AppTheme.bad))),
              ]),
            ),
          ],
          const SizedBox(height: 22),
          FilledButton(
            onPressed: auth.loading ? null : _submit,
            style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(48)),
            child: auth.loading
                ? const SizedBox(
                    height: 22,
                    width: 22,
                    child: CircularProgressIndicator(strokeWidth: 2.5, color: Colors.white))
                : Text(tr(context, 'sign_in')),
          ),
          const SizedBox(height: 6),
          TextButton.icon(
            onPressed: () => showServerDialog(context, ref),
            icon: const Icon(Icons.dns_outlined, size: 16),
            label: Text(
              auth.serverUrl.isEmpty
                  ? tr(context, 'set_server')
                  : '${tr(context, 'server')}: ${auth.serverUrl}',
              style: const TextStyle(fontSize: 12),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }
}
