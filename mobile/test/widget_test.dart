// Smoke test: the app boots to its auth gate without throwing.
import 'package:asw_mobile/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('App boots without error', (tester) async {
    await tester.pumpWidget(const ProviderScope(child: AswApp()));
    await tester.pump();
    expect(find.byType(MaterialApp), findsOneWidget);
  });
}
