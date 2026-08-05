import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../i18n.dart';
import '../state/providers.dart';
import '../widgets/server_dialog.dart';

/// Account, security (biometric), connection and sign-out — pushed from the
/// home app-bar menu.
class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final auth = ref.watch(authProvider);
    final notifier = ref.read(authProvider.notifier);
    final user = auth.user;
    final themeMode = ref.watch(themeProvider);
    final locale = ref.watch(localeProvider);

    return Scaffold(
      appBar: AppBar(title: Text(tr(context, 'settings'))),
      body: ListView(
        children: [
          _header(context, tr(context, 'account')),
          ListTile(
            leading: const CircleAvatar(child: Icon(Icons.person)),
            title: Text(user?.name ?? user?.username ?? '—'),
            subtitle: Text('${user?.username ?? ''} · ${user?.role ?? ''}'),
          ),
          const Divider(),

          _header(context, tr(context, 'language')),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 10),
            child: SegmentedButton<String>(
              showSelectedIcon: false,
              segments: const [
                ButtonSegment(value: 'en', label: Text('English')),
                ButtonSegment(value: 'ur', label: Text('اردو')),
              ],
              selected: {locale.languageCode},
              onSelectionChanged: (s) =>
                  ref.read(localeProvider.notifier).setLang(s.first),
            ),
          ),
          const Divider(),

          _header(context, tr(context, 'appearance')),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 10),
            child: SegmentedButton<ThemeMode>(
              showSelectedIcon: false,
              segments: [
                ButtonSegment(
                    value: ThemeMode.system,
                    icon: const Icon(Icons.brightness_auto, size: 18),
                    label: Text(tr(context, 'system'))),
                ButtonSegment(
                    value: ThemeMode.light,
                    icon: const Icon(Icons.light_mode, size: 18),
                    label: Text(tr(context, 'light'))),
                ButtonSegment(
                    value: ThemeMode.dark,
                    icon: const Icon(Icons.dark_mode, size: 18),
                    label: Text(tr(context, 'dark'))),
              ],
              selected: {themeMode},
              onSelectionChanged: (s) =>
                  ref.read(themeProvider.notifier).setMode(s.first),
            ),
          ),
          const Divider(),

          _header(context, tr(context, 'security')),
          if (auth.biometricAvailable)
            SwitchListTile(
              secondary: const Icon(Icons.fingerprint),
              title: Text('${auth.biometricLabel} ${tr(context, 'unlock_suffix')}'),
              subtitle: Text(auth.biometricEnabled
                  ? tr(context, 'bio_on_sub')
                  : tr(context, 'bio_off_sub')),
              value: auth.biometricEnabled,
              onChanged: (on) =>
                  on ? notifier.enableBiometric() : notifier.disableBiometric(),
            )
          else
            ListTile(
              leading: const Icon(Icons.fingerprint),
              title: Text(tr(context, 'biometric_unlock')),
              subtitle: Text(tr(context, 'not_available_device')),
            ),
          ListTile(
            leading: const Icon(Icons.shield_outlined),
            title: Text(tr(context, 'session_security')),
            subtitle: Text(tr(context, 'session_security_sub')),
          ),
          const Divider(),

          _header(context, tr(context, 'connection')),
          ListTile(
            leading: const Icon(Icons.dns_outlined),
            title: Text(tr(context, 'server')),
            subtitle: Text(auth.serverUrl.isEmpty ? tr(context, 'not_set') : auth.serverUrl),
            trailing: const Icon(Icons.edit_outlined, size: 18),
            onTap: () => showServerDialog(context, ref),
          ),
          const Divider(),

          const SizedBox(height: 8),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: OutlinedButton.icon(
              onPressed: () => notifier.logout(),
              style: OutlinedButton.styleFrom(
                minimumSize: const Size.fromHeight(48),
                foregroundColor: Theme.of(context).colorScheme.error,
              ),
              icon: const Icon(Icons.logout),
              label: Text(tr(context, 'sign_out')),
            ),
          ),
          const SizedBox(height: 24),
          Center(
            child: Text('Abdul Sattar Woods · v0.2.1',
                style: TextStyle(color: Theme.of(context).hintColor, fontSize: 12)),
          ),
          const SizedBox(height: 24),
        ],
      ),
    );
  }

  Widget _header(BuildContext context, String t) => Padding(
        padding: const EdgeInsets.fromLTRB(16, 18, 16, 6),
        child: Text(t.toUpperCase(),
            style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w800,
                letterSpacing: 1.2,
                color: Theme.of(context).colorScheme.primary)),
      );
}
