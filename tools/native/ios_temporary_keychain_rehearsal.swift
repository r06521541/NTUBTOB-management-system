// Fictional fixed-cwd fixture only. Never installs an identity into login/default.
import Foundation
import Security
import Darwin

var phase = "arguments"
var errorClass = "NOT_CHECKED"
var cleanupState = "NOT_CREATED"
var cleanupError = "NOT_CHECKED"
var cleanupPhase = "not_started"
func finish(_ value: String) -> Never {
    let result = ["reason": value, "phase": phase, "error_class": errorClass,
                  "cleanup": cleanupState, "cleanup_error_class": cleanupError, "cleanup_phase": cleanupPhase]
    let data = try! JSONSerialization.data(withJSONObject: result, options: [.sortedKeys])
    print(String(data: data, encoding: .utf8)!)
    exit(0)
}
func category(_ value: OSStatus) -> String {
    switch value {
    case errSecSuccess: return "OS_SUCCESS"
    case errSecAuthFailed: return "OS_AUTH_FAILED"
    case errSecDecode: return "OS_DECODE"
    case errSecInteractionNotAllowed: return "OS_INTERACTION_NOT_ALLOWED"
    case errSecItemNotFound: return "OS_ITEM_NOT_FOUND"
    case errSecParam: return "OS_PARAM"
    default: return "OS_OTHER"
    }
}
func status(_ name: String, _ value: OSStatus) -> Bool {
    phase = name; errorClass = category(value)
    return value == errSecSuccess
}
func predicate(_ name: String, _ value: Bool) -> Bool {
    phase = name; errorClass = value ? "OS_SUCCESS" : "PREDICATE_REJECTED"
    return value
}
guard predicate("arguments", CommandLine.arguments.count == 1) else { finish("ARGUMENTS_REJECTED") }
phase = "platform"
guard #available(macOS 15.0, *) else { errorClass = "PREDICATE_REJECTED"; finish("PLATFORM_UNSUPPORTED") }
let fm = FileManager.default
let cwd = URL(fileURLWithPath: fm.currentDirectoryPath).standardizedFileURL
let parent = cwd.deletingLastPathComponent()
let temporary = URL(fileURLWithPath: NSTemporaryDirectory()).resolvingSymlinksInPath()
guard predicate("cwd_name", cwd.lastPathComponent == "custody") else { finish("PATH_REJECTED") }
guard predicate("root_name", parent.lastPathComponent.hasPrefix("task-196-")) else { finish("PATH_REJECTED") }
guard predicate("cwd_canonical", cwd.resolvingSymlinksInPath().path == cwd.path) else { finish("PATH_REJECTED") }
guard predicate("temp_binding", temporary.path == cwd.path) else { finish("PATH_REJECTED") }
var directoryInfo = stat()
guard predicate("directory_stat", lstat(cwd.path, &directoryInfo) == 0) else { finish("PATH_REJECTED") }
guard predicate("directory_owner", directoryInfo.st_uid == getuid()) else { finish("PATH_REJECTED") }
guard predicate("directory_mode", directoryInfo.st_mode & 0o777 == 0o700) else { finish("PATH_REJECTED") }
guard predicate("directory_type", directoryInfo.st_mode & S_IFMT == S_IFDIR) else { finish("PATH_REJECTED") }
let path = cwd.appendingPathComponent("fictional-task196.keychain-db").path
guard predicate("path_empty", (try? fm.contentsOfDirectory(atPath: cwd.path)) == []) else { finish("PATH_REJECTED") }
var input = Data()
while input.count <= 131081 {
    let part = FileHandle.standardInput.readData(ofLength: min(4096, 131082 - input.count))
    if part.isEmpty { break }
    input.append(part)
}
guard predicate("frame", input.count >= 9 && input.count <= 131081) else { finish("FRAME_REJECTED") }
func length(_ offset: Int) -> Int { input[offset..<(offset + 4)].reduce(0) { ($0 << 8) | Int($1) } }
let p12Length = length(1), certLength = length(5)
guard predicate("frame", input[0] <= 1 && p12Length > 0 && p12Length <= 65536 && certLength > 0 && certLength <= 65536 && input.count == 9 + p12Length + certLength) else { finish("FRAME_REJECTED") }
let p12 = input.subdata(in: 9..<(9 + p12Length))
let expected = input.subdata(in: (9 + p12Length)..<input.count)
var beforeList: CFArray?
var beforeDefault: SecKeychain?
guard status("search_snapshot", SecKeychainCopySearchList(&beforeList)) else { finish("CUSTODY_REJECTED") }
let beforeDefaultStatus = SecKeychainCopyDefault(&beforeDefault)
phase = "default_snapshot"; errorClass = category(beforeDefaultStatus)
guard beforeDefaultStatus == errSecSuccess || beforeDefaultStatus == errSecNoDefaultKeychain else { finish("CUSTODY_REJECTED") }
guard status("disable_interaction", SecKeychainSetUserInteractionAllowed(false)) else { finish("CUSTODY_REJECTED") }
var metadataPhase = "search_read"
var metadataError = "NOT_CHECKED"
func unchanged() -> Bool {
    var list: CFArray?
    var keychain: SecKeychain?
    let value = SecKeychainCopyDefault(&keychain)
    let searchStatus = SecKeychainCopySearchList(&list)
    metadataPhase = "search_read"; metadataError = category(searchStatus)
    guard searchStatus == errSecSuccess else { return false }
    metadataPhase = "default_status"; metadataError = "PREDICATE_REJECTED"
    guard value == beforeDefaultStatus else { return false }
    metadataPhase = "search_shape"
    guard let list = list, let before = beforeList else { return false }
    metadataPhase = "search_match"
    guard CFEqual(list, before) else { return false }
    metadataPhase = "default_match"
    if let old = beforeDefault, let current = keychain { return CFEqual(old, current) }
    return beforeDefault == nil && keychain == nil
}
func identityFromItems(_ imported: CFArray?) -> SecIdentity? {
    phase = "identity_array"; errorClass = "PREDICATE_REJECTED"
    guard let items = imported as? [[String: Any]] else { return nil }
    guard predicate("identity_count", items.count == 1) else { return nil }
    phase = "identity_value"; errorClass = "PREDICATE_REJECTED"
    guard let value = items[0][kSecImportItemIdentity as String] else { return nil }
    guard predicate("identity_type", CFGetTypeID(value as CFTypeRef) == SecIdentityGetTypeID()) else { return nil }
    return value as! SecIdentity
}
var keychain: SecKeychain?
var trustedApplication: SecTrustedApplication?
var access: SecAccess?
guard status("trusted_application", SecTrustedApplicationCreateFromPath(nil, &trustedApplication)),
      let trustedApplication = trustedApplication else { finish("CUSTODY_REJECTED") }
guard status("access", SecAccessCreate("fictional-task196-current-process-only" as CFString, [trustedApplication] as CFArray, &access)),
      let access = access else { finish("CUSTODY_REJECTED") }
let password = Array("fictional-temporary-keychain-password".utf8)
var reason = "CUSTODY_REJECTED"
cleanupState = "UNRESOLVED"
let created = password.withUnsafeBytes { bytes in
    SecKeychainCreate(path, UInt32(password.count), bytes.baseAddress, false, nil, &keychain)
}
if status("create", created), predicate("created_keychain", keychain != nil), let target = keychain {
    if unchanged() {
        let options: [String: Any] = [
            kSecImportExportPassphrase as String: input[0] == 0 ? "fictional-new-password" : "fictional-wrong-password",
            kSecImportExportKeychain as String: target,
            kSecImportExportAccess as String: access
        ]
        var imported: CFArray?
        let importedStatus = SecPKCS12Import(p12 as CFData, options as CFDictionary, &imported)
        let importOK = status("import", importedStatus)
        if importedStatus == errSecAuthFailed {
            reason = "AUTH_REJECTED"
        } else if importOK {
            if let identity = identityFromItems(imported) {
                var certificate: SecCertificate?
                var privateKey: SecKey?
                if status("certificate", SecIdentityCopyCertificate(identity, &certificate)), predicate("certificate_value", certificate != nil), let certificate = certificate {
                    if !predicate("certificate_match", SecCertificateCopyData(certificate) as Data == expected) {
                        reason = "CERTIFICATE_MISMATCH"
                    } else if status("private_key", SecIdentityCopyPrivateKey(identity, &privateKey)), predicate("private_key_value", privateKey != nil), let privateKey = privateKey {
                        phase = "public_key"; errorClass = "PREDICATE_REJECTED"
                        if let publicKey = SecCertificateCopyKey(certificate) {
                            var actualKeychain: SecKeychain?
                            let item = unsafeBitCast(privateKey, to: SecKeychainItem.self)
                            let algorithm = SecKeyAlgorithm.rsaSignatureMessagePKCS1v15SHA256
                            let challenge = Data("fictional-custody-challenge-not-app-signing".utf8)
                            if status("key_association", SecKeychainItemCopyKeychain(item, &actualKeychain)),
                               predicate("key_value", actualKeychain != nil), let actual = actualKeychain, predicate("key_target", CFEqual(actual, target)),
                               predicate("algorithm", SecKeyIsAlgorithmSupported(privateKey, .sign, algorithm)) {
                                phase = "sign"; errorClass = "PREDICATE_REJECTED"
                                if let signature = SecKeyCreateSignature(privateKey, algorithm, challenge as CFData, nil),
                                   predicate("verify", SecKeyVerifySignature(publicKey, algorithm, challenge as CFData, signature, nil)) {
                                    reason = "CUSTODY_VERIFIED"
                                }
                            }
                        }
                    }
                }
            }
        }
    } else { phase = metadataPhase; errorClass = metadataError }
    // Preserve operation failure evidence while independently checking cleanup.
    let deleted = SecKeychainDelete(target)
    cleanupPhase = "delete"
    cleanupError = category(deleted)
    if deleted != errSecSuccess { cleanupState = "DELETE_REJECTED"; finish("CLEANUP_UNRESOLVED") }
} else if fm.fileExists(atPath: path) {
    cleanupState = "RESIDUAL_FILES"; cleanupError = "PREDICATE_REJECTED"; cleanupPhase = "file_absence"
    finish("CLEANUP_UNRESOLVED")
}
guard unchanged() else { cleanupState = "METADATA_CHANGED"; cleanupError = metadataError; cleanupPhase = metadataPhase; finish("CLEANUP_UNRESOLVED") }
guard !fm.fileExists(atPath: path) else {
    cleanupState = "RESIDUAL_FILES"; cleanupError = "PREDICATE_REJECTED"; cleanupPhase = "file_absence"; finish("CLEANUP_UNRESOLVED")
}
guard (try? fm.contentsOfDirectory(atPath: cwd.path)) == [] else {
    cleanupState = "RESIDUAL_FILES"; cleanupError = "PREDICATE_REJECTED"; cleanupPhase = "directory_empty"; finish("CLEANUP_UNRESOLVED")
}
cleanupState = "VERIFIED"; cleanupError = "OS_SUCCESS"; cleanupPhase = "completed"
finish(reason)
