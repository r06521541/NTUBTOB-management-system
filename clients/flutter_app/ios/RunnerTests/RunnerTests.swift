import Flutter
import UIKit
import XCTest
@testable import Runner

class RunnerTests: XCTestCase {

  func testAppleNonceHashUsesLowercaseSHA256() {
    XCTAssertEqual(
      AppleAuthorizationBridge.sha256Hex("obvious-fictional-raw-nonce"),
      "6f8b9b108e9119312af29a9d41cc3bd38e00f2f600af77b1f874803634d5cf6a"
    )
  }

}
