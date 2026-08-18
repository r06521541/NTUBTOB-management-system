import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ntubtob_fictional_client/basic_app.dart';

void main() {
  for (final state in AuthViewState.values) {
    testWidgets('$state has distinguishable semantics', (tester) async {
      await tester.pumpWidget(MaterialApp(home: AuthStatePanel(state: state)));
      expect(find.byType(Icon), findsOneWidget);
      expect(find.bySemanticsLabel(RegExp('.+')), findsWidgets);
    });
  }
}
