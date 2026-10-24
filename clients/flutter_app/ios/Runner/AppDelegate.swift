import Flutter
import UIKit

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
    if let appleRegistrar = engineBridge.pluginRegistry.registrar(
      forPlugin: "AppleAuthorizationBridge"
    ) {
      AppleAuthorizationBridge.register(with: appleRegistrar)
    }
    if let googleRegistrar = engineBridge.pluginRegistry.registrar(
      forPlugin: "GoogleAuthorizationBridge"
    ) {
      GoogleAuthorizationBridge.register(with: googleRegistrar)
    }
  }
}
