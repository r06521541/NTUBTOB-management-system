import Flutter
import GoogleSignIn
import UIKit

/// A per-request SDK nonce, not GoogleSignIn plugin initialization state.
/// No profile, server auth code, cached token or raw SDK error crosses the channel.
final class GoogleAuthorizationBridge: NSObject, FlutterPlugin {
  private var activeResult: FlutterResult?

  static func register(with registrar: FlutterPluginRegistrar) {
    let channel = FlutterMethodChannel(
      name: "tw.org.ntubtob.portal/google_authorization",
      binaryMessenger: registrar.messenger()
    )
    registrar.addMethodCallDelegate(GoogleAuthorizationBridge(), channel: channel)
  }

  func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
    guard call.method == "authorize" else {
      result(FlutterMethodNotImplemented)
      return
    }
    guard activeResult == nil else {
      result(Self.error())
      return
    }
    guard
      let arguments = call.arguments as? [String: Any], arguments.count == 3,
      let nonce = arguments["raw_nonce"] as? String,
      nonce.utf8.count == 43, Self.asciiNonce(nonce),
      let client = arguments["client_id"] as? String,
      let server = arguments["server_client_id"] as? String,
      Self.validClient(client), Self.validClient(server), client != server,
      Self.hasCallbackScheme(client),
      let presenter = Self.presenter()
    else {
      result(Self.error())
      return
    }

    let signIn = GIDSignIn.sharedInstance
    if let configuration = signIn.configuration {
      guard configuration.clientID == client, configuration.serverClientID == server else {
        result(Self.error())
        return
      }
    } else {
      // Fresh proof may be the first Google operation after process restart.
      // Only establish the exact supplied ordinary configuration, never replace it.
      signIn.configuration = GIDConfiguration(clientID: client, serverClientID: server)
    }
    activeResult = result
    signIn.signIn(
      withPresenting: presenter, hint: nil, additionalScopes: [], nonce: nonce
    ) { [weak self] response, error in
      guard let self = self else { return }
      guard error == nil, let token = response?.user.idToken?.tokenString,
        !token.isEmpty, token.utf8.count <= 16_384
      else {
        self.complete(Self.error())
        return
      }
      self.complete(["identity_token": token])
    }
  }

  private static func asciiNonce(_ value: String) -> Bool {
    value.utf8.allSatisfy { byte in
      (48...57).contains(byte) || (65...90).contains(byte) || (97...122).contains(byte)
        || byte == 45 || byte == 95
    }
  }

  private static func validClient(_ value: String) -> Bool {
    let pattern = "[0-9A-Za-z][0-9A-Za-z._-]{5,199}\\.apps\\.googleusercontent\\.com"
    guard value.utf8.count <= 227, let regex = try? NSRegularExpression(pattern: pattern) else {
      return false
    }
    let range = NSRange(value.startIndex..., in: value)
    return regex.firstMatch(in: value, range: range)?.range == range
  }

  private static func hasCallbackScheme(_ client: String) -> Bool {
    let expected = client.split(separator: ".").reversed().joined(separator: ".")
    let types = Bundle.main.object(forInfoDictionaryKey: "CFBundleURLTypes") as? [[String: Any]]
    return types?.contains { ($0["CFBundleURLSchemes"] as? [String])?.contains(expected) == true } == true
  }

  private static func presenter() -> UIViewController? {
    guard
      let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene })
        .first(where: { $0.activationState == .foregroundActive }),
      let root = scene.windows.first(where: { $0.isKeyWindow })?.rootViewController,
      root.presentedViewController == nil, root.viewIfLoaded?.window != nil
    else { return nil }
    // An already-presented native login/modal is not a fresh-proof presenter.
    return root
  }

  private static func error() -> FlutterError {
    FlutterError(code: "google_authorization_unavailable",
      message: "Google authorization did not complete", details: nil)
  }

  private func complete(_ value: Any) {
    let result = activeResult
    activeResult = nil
    result?(value)
  }
}
