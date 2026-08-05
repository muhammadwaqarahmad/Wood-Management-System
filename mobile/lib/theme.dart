import 'package:flutter/material.dart';

/// The app's visual identity — the SAME timber-green palette as the desktop,
/// so the phone and desktop feel like one product. Light + dark, Material 3.
class AppTheme {
  // Brand greens (match the desktop design system).
  static const accent = Color(0xFF14684A); // primary green
  static const accentDark = Color(0xFF54C392); // green on dark ground
  static const good = Color(0xFF1E7A4B);
  static const warn = Color(0xFF8A5A0B);
  static const bad = Color(0xFFA5341F);

  // KPI tile accent tones — the SAME palette as the desktop dashboard tiles.
  static const tones = {
    'indigo': Color(0xFF6366F1),
    'sky': Color(0xFF0EA5E9),
    'emerald': Color(0xFF10B981),
    'amber': Color(0xFFF59E0B),
    'rose': Color(0xFFF43F5E),
    'violet': Color(0xFF8B5CF6),
    'slate': Color(0xFF64748B),
  };
  static Color tone(String name) => tones[name] ?? tones['slate']!;

  // Chart series colours (CVD-validated, matching desktop _CAT_LIGHT/_DARK).
  static const catLight = [
    Color(0xFF2A78D6), Color(0xFF008300), Color(0xFFE87BA4), Color(0xFFEDA100)
  ];
  static const catDark = [
    Color(0xFF3987E5), Color(0xFF008300), Color(0xFFD55181), Color(0xFFC98500)
  ];

  /// Positive = green, negative = red, zero = muted — like the desktop.
  static Color amount(BuildContext context, num v) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    if (v > 0) return dark ? const Color(0xFF34D399) : const Color(0xFF059669);
    if (v < 0) return dark ? const Color(0xFFFB7185) : const Color(0xFFE11D48);
    return Theme.of(context).hintColor;
  }

  static ThemeData light() => _build(Brightness.light);
  static ThemeData dark() => _build(Brightness.dark);

  static ThemeData _build(Brightness b) {
    final dark = b == Brightness.dark;
    final scheme = ColorScheme.fromSeed(
      seedColor: accent,
      brightness: b,
      primary: dark ? accentDark : accent,
    );
    return ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      scaffoldBackgroundColor: dark ? const Color(0xFF0D100C) : const Color(0xFFF4F6F2),
      fontFamily: 'Roboto',
      cardTheme: CardThemeData(
        elevation: 0,
        color: dark ? const Color(0xFF151A13) : Colors.white,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(14),
          side: BorderSide(
            color: dark ? const Color(0xFF293127) : const Color(0xFFD6DDCF),
          ),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: const Size.fromHeight(52),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide.none,
        ),
      ),
    );
  }
}
