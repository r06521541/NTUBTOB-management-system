// Fictional fixed-cwd fixture only. Never installs an identity into login/default.
import Foundation
import Security
import Darwin

func finish(_ value: String) -> Never { print(value); exit(0) }
guard CommandLine.arguments.count == 1 else { finish("ARGUMENTS_REJECTED") }
guard #available(macOS 15.0, *) else { finish("PLATFORM_UNSUPPORTED") }
let fm = FileManager.default
let cwd = URL(fileURLWithPath: fm.currentDirectoryPath).standardizedFileURL
let parent = cwd.deletingLastPathComponent()
let temporary = URL(fileURLWithPath: NSTemporaryDirectory()).resolvingSymlinksInPath()
// Python's child TMPDIR is custody itself; verify fixed parent structure as well
// as canonical components and private current-user ownership before creation.
guard cwd.lastPathComponent == "custody", parent.lastPathComponent.hasPrefix("task-196-"),
      cwd.resolvingSymlinksInPath().path == cwd.path,
      temporary.path == cwd.path else { finish("PATH_REJECTED") }
var directoryInfo = stat()
guard lstat(cwd.path, &directoryInfo) == 0,
      directoryInfo.st_uid == getuid(),
      directoryInfo.st_mode & 0o777 == 0o700,
      directoryInfo.st_mode & S_IFMT == S_IFDIR else { finish("PATH_REJECTED") }
let path = cwd.appendingPathComponent("fictional-task196.keychain-db").path
guard (try? fm.contentsOfDirectory(atPath: cwd.path)) == [] else { finish("PATH_REJECTED") }

var input = Data()
while input.count <= 131081 {
    let part = FileHandle.standardInput.readData(ofLength: min(4096, 131082 - input.count))
    if part.isEmpty { break }
    input.append(part)
}
guard input.count >= 9, input.count <= 131081 else { finish("FRAME_REJECTED") }
func length(_ offset: Int) -> Int { input[offset..<(offset + 4)].reduce(0) { ($0 << 8) | Int($1) } }
let p12Length = length(1), certLength = length(5)
guard input[0] <= 1, p12Length > 0, p12Length <= 65536, certLength > 0, certLength <= 65536,
      input.count == 9 + p12Length + certLength else { finish("FRAME_REJECTED") }
let p12 = input.subdata(in: 9..<(9 + p12Length))
let expected = input.subdata(in: (9 + p12Length)..<input.count)
var beforeList: CFArray?
var beforeDefault: SecKeychain?
guard SecKeychainCopySearchList(&beforeList) == errSecSuccess else { finish("CUSTODY_REJECTED") }
let beforeDefaultStatus = SecKeychainCopyDefault(&beforeDefault)
guard beforeDefaultStatus == errSecSuccess || beforeDefaultStatus == errSecNoDefaultKeychain,
      SecKeychainSetUserInteractionAllowed(false) == errSecSuccess else { finish("CUSTODY_REJECTED") }

func unchanged() -> Bool {
    var list: CFArray?
    var keychain: SecKeychain?
    let status = SecKeychainCopyDefault(&keychain)
    guard SecKeychainCopySearchList(&list) == errSecSuccess, status == beforeDefaultStatus,
          let list = list, let before = beforeList, CFEqual(list, before) else { return false }
    if let old = beforeDefault, let current = keychain { return CFEqual(old, current) }
    return beforeDefault == nil && keychain == nil
}

var keychain: SecKeychain?
var trustedApplication: SecTrustedApplication?
var access: SecAccess?
guard SecTrustedApplicationCreateFromPath(nil, &trustedApplication) == errSecSuccess,
      let trustedApplication = trustedApplication,
      SecAccessCreate("fictional-task196-current-process-only" as CFString, [trustedApplication] as CFArray, &access) == errSecSuccess,
      let access = access else { finish("CUSTODY_REJECTED") }
let password = Array("fictional-temporary-keychain-password".utf8)
var reason = "CUSTODY_REJECTED"
let created = password.withUnsafeBytes { bytes in
    SecKeychainCreate(path, UInt32(password.count), bytes.baseAddress, false, nil, &keychain)
}
if created == errSecSuccess, let target = keychain {
    if unchanged() {
        let options: [String: Any] = [
            kSecImportExportPassphrase as String: input[0] == 0 ? "fictional-new-password" : "fictional-wrong-password",
            kSecImportExportKeychain as String: target,
            kSecImportExportAccess as String: access
        ]
        var imported: CFArray?
        let status = SecPKCS12Import(p12 as CFData, options as CFDictionary, &imported)
        if status == errSecAuthFailed {
            reason = "AUTH_REJECTED"
        } else if status == errSecSuccess,
                  let items = imported as? [[String: Any]], items.count == 1,
                  let value = items[0][kSecImportItemIdentity as String],
                  CFGetTypeID(value as CFTypeRef) == SecIdentityGetTypeID() {
            let identity = value as! SecIdentity
            var certificate: SecCertificate?
            var privateKey: SecKey?
            if SecIdentityCopyCertificate(identity, &certificate) == errSecSuccess, let certificate = certificate {
                if SecCertificateCopyData(certificate) as Data != expected {
                    reason = "CERTIFICATE_MISMATCH"
                } else if SecIdentityCopyPrivateKey(identity, &privateKey) == errSecSuccess,
                          let privateKey = privateKey, let publicKey = SecCertificateCopyKey(certificate) {
                    var actualKeychain: SecKeychain?
                    let item = unsafeBitCast(privateKey, to: SecKeychainItem.self)
                    let algorithm = SecKeyAlgorithm.rsaSignatureMessagePKCS1v15SHA256
                    let challenge = Data("fictional-custody-challenge-not-app-signing".utf8)
                    if SecKeychainItemCopyKeychain(item, &actualKeychain) == errSecSuccess,
                       let actual = actualKeychain, CFEqual(actual, target),
                       SecKeyIsAlgorithmSupported(privateKey, .sign, algorithm),
                       let signature = SecKeyCreateSignature(privateKey, algorithm, challenge as CFData, nil),
                       SecKeyVerifySignature(publicKey, algorithm, challenge as CFData, signature, nil) {
                        reason = "CUSTODY_VERIFIED"
                    }
                }
            }
        }
    }
    // Always delete this exact keychain, including partial/mismatched imports.
    if SecKeychainDelete(target) != errSecSuccess { finish("CLEANUP_UNRESOLVED") }
} else if fm.fileExists(atPath: path) {
    // Never claim a failed create had no residual state or repair another target.
    finish("CLEANUP_UNRESOLVED")
}
guard unchanged(), !fm.fileExists(atPath: path),
      (try? fm.contentsOfDirectory(atPath: cwd.path)) == [] else { finish("CLEANUP_UNRESOLVED") }
finish(reason)
