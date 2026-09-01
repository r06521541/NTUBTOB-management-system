import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';

import 'anonymous_crash.dart';
import 'basic_app.dart';
import 'foundation.dart';
import 'integration.dart';
import 'production_demo.dart';

Future<void> main() async {
  final config = AppConfig.fromEnvironment();
  if (config.mode == ClientMode.fake) {
    WidgetsFlutterBinding.ensureInitialized();
    runApp(composeRoot(config));
    return;
  }

  AnonymousCrashHooks? activeHooks;
  await (runZonedGuarded<Future<void>>(
        () async {
          // Binding initialization and runApp must remain in the same zone.
          WidgetsFlutterBinding.ensureInitialized();
          final store = SecureStore();
          late final AnonymousCrashQueue queue;
          try {
            final installationId =
                await ensureInstallationId(store, SecureIds());
            queue = AnonymousCrashQueue(store, installationId);
          } on Object {
            // Optional diagnostics must not prevent the existing fail-closed
            // boot UI from handling unavailable secure storage.
            runApp(BasicBootstrapApp(config: config, store: store));
            return;
          }
          final hooks = AnonymousCrashHooks(AnonymousCrashReporter(
            queue: queue,
            appFlavor: config.flavor,
            platformClass: switch (defaultTargetPlatform) {
              TargetPlatform.android => 'android',
              TargetPlatform.iOS => 'ios',
              _ => 'other',
            },
          ));
          activeHooks = hooks;
          final previousFlutter = FlutterError.onError;
          final previousPlatform = PlatformDispatcher.instance.onError;
          FlutterError.onError =
              (details) => hooks.flutter(details, previousFlutter);
          PlatformDispatcher.instance.onError = (error, stackTrace) =>
              hooks.platform(error, stackTrace, previousPlatform);
          runApp(BasicBootstrapApp(
            config: config,
            store: store,
            crashQueue: queue,
          ));
        },
        (error, stackTrace) {
          final hooks = activeHooks;
          if (hooks == null) {
            FlutterError.presentError(
              FlutterErrorDetails(exception: error, stack: stackTrace),
            );
            return;
          }
          hooks.zone(
            error,
            stackTrace,
            (error, stackTrace) => FlutterError.presentError(
              FlutterErrorDetails(exception: error, stack: stackTrace),
            ),
          );
        },
      ) ??
      Future<void>.value());
}

Widget composeRoot(AppConfig config) => config.mode == ClientMode.fake
    ? ProductionDemoApp(flavor: FlavorConfig(config.flavor))
    : BasicBootstrapApp(config: config);
