import 'package:flutter/widgets.dart';
import 'basic_app.dart';
import 'foundation.dart';
import 'integration.dart';

void main() {
  final config = AppConfig.fromEnvironment();
  runApp(composeRoot(config));
}

Widget composeRoot(AppConfig config) => config.mode == ClientMode.fake
    ? DemoApp(flavor: FlavorConfig(config.flavor))
    : BasicBootstrapApp(config: config);
