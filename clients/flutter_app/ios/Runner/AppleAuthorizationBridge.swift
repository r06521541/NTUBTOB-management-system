import AuthenticationServices
import CryptoKit
import Flutter
import UIKit

final class AppleAuthorizationBridge: NSObject, FlutterPlugin {
  private static let channelName = "tw.org.ntubtob.portal/apple_authorization"
  private var activeResult: FlutterResult?
  private var activeController: ASAuthorizationController?
  private var activeAnchor: ASPresentationAnchor?

  static func register(with registrar: FlutterPluginRegistrar) {
    let channel = FlutterMethodChannel(
      name: channelName,
      binaryMessenger: registrar.messenger()
    )
    let instance = AppleAuthorizationBridge()
    registrar.addMethodCallDelegate(instance, channel: channel)
  }

  func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
    guard call.method == "authorize" else {
      result(FlutterMethodNotImplemented)
      return
    }
    guard activeResult == nil else {
      result(Self.error("apple_authorization_in_progress"))
      return
    }
    guard
      let arguments = call.arguments as? [String: Any],
      arguments.count == 1,
      let rawNonce = arguments["raw_nonce"] as? String,
      Self.validRawNonce(rawNonce),
      let anchor = Self.presentationAnchor()
    else {
      result(Self.error("apple_authorization_unavailable"))
      return
    }

    let request = ASAuthorizationAppleIDProvider().createRequest()
    request.requestedScopes = []
    request.nonce = Self.sha256Hex(rawNonce)
    let controller = ASAuthorizationController(authorizationRequests: [request])
    activeResult = result
    activeController = controller
    activeAnchor = anchor
    controller.delegate = self
    controller.presentationContextProvider = self
    controller.performRequests()
  }

  static func sha256Hex(_ value: String) -> String {
    SHA256.hash(data: Data(value.utf8))
      .map { String(format: "%02x", $0) }
      .joined()
  }

  private static func validRawNonce(_ value: String) -> Bool {
    guard (16...128).contains(value.count) else { return false }
    return value.utf8.allSatisfy { byte in
      (byte >= 48 && byte <= 57)
        || (byte >= 65 && byte <= 90)
        || (byte >= 97 && byte <= 122)
        || byte == 45
        || byte == 95
    }
  }

  private static func presentationAnchor() -> ASPresentationAnchor? {
    UIApplication.shared.connectedScenes
      .compactMap { $0 as? UIWindowScene }
      .first { $0.activationState == .foregroundActive }?
      .windows
      .first { $0.isKeyWindow }
  }

  private static func error(_ code: String) -> FlutterError {
    FlutterError(code: code, message: "Apple authorization did not complete", details: nil)
  }

  private func complete(_ value: Any) {
    let result = activeResult
    activeResult = nil
    activeController = nil
    activeAnchor = nil
    result?(value)
  }
}

extension AppleAuthorizationBridge: ASAuthorizationControllerDelegate {
  func authorizationController(
    controller: ASAuthorizationController,
    didCompleteWithAuthorization authorization: ASAuthorization
  ) {
    guard
      controller === activeController,
      let credential = authorization.credential as? ASAuthorizationAppleIDCredential,
      let tokenData = credential.identityToken,
      tokenData.count <= 32_768,
      let token = String(data: tokenData, encoding: .utf8),
      !token.isEmpty
    else {
      complete(Self.error("apple_authorization_failed"))
      return
    }
    // The provider subject remains inside the signed token. Do not return the
    // Apple user identifier, email, name, authorization code, or profile hints.
    complete(["identity_token": token])
  }

  func authorizationController(
    controller: ASAuthorizationController,
    didCompleteWithError error: Error
  ) {
    guard controller === activeController else { return }
    let code: String
    if let authorizationError = error as? ASAuthorizationError {
      switch authorizationError.code {
      case .canceled:
        code = "apple_authorization_cancelled"
      case .notHandled:
        code = "apple_authorization_unavailable"
      default:
        code = "apple_authorization_failed"
      }
    } else {
      code = "apple_authorization_failed"
    }
    complete(Self.error(code))
  }
}

extension AppleAuthorizationBridge: ASAuthorizationControllerPresentationContextProviding {
  func presentationAnchor(for controller: ASAuthorizationController) -> ASPresentationAnchor {
    activeAnchor ?? ASPresentationAnchor()
  }
}
