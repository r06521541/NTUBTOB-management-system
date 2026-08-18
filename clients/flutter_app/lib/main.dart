import 'package:flutter/widgets.dart';
import 'foundation.dart';

const _flavorName = String.fromEnvironment('APP_FLAVOR');

void main() => runApp(DemoApp(flavor: FlavorConfig.parse(_flavorName)));
