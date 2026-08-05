import 'package:flutter/material.dart';

/// Branded background + centered card used by the login and lock screens —
/// the mobile echo of the desktop sign-in look (green ground, app name, card).
class AuthShell extends StatelessWidget {
  const AuthShell({super.key, required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    return Scaffold(
      body: Container(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: dark
                ? [const Color(0xFF0E1A14), const Color(0xFF0B0F0C)]
                : [const Color(0xFF14684A), const Color(0xFF0E8C63)],
          ),
        ),
        child: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 420),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    // brand monogram
                    Container(
                      width: 66,
                      height: 66,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        color: Colors.white.withValues(alpha: dark ? 0.08 : 0.16),
                        borderRadius: BorderRadius.circular(18),
                      ),
                      child: const Icon(Icons.forest, color: Colors.white, size: 34),
                    ),
                    const SizedBox(height: 14),
                    const Text('Abdul Sattar Woods',
                        style: TextStyle(
                            color: Colors.white,
                            fontSize: 22,
                            fontWeight: FontWeight.w800)),
                    const SizedBox(height: 4),
                    Text('Timber Trading Manager',
                        style: TextStyle(
                            color: Colors.white.withValues(alpha: 0.8), fontSize: 13)),
                    const SizedBox(height: 26),
                    // the card
                    Card(
                      elevation: 8,
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(18)),
                      child: Padding(
                        padding: const EdgeInsets.fromLTRB(22, 24, 22, 24),
                        child: child,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
