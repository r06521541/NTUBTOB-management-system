// Fictional fixed-cwd fixture only. Never installs an identity into login/default.
import Foundation
import Security
import Darwin
import CryptoKit

var phase = "arguments"
var errorClass = "NOT_CHECKED"
var cleanupState = "NOT_CREATED"
var cleanupError = "NOT_CHECKED"
var cleanupPhase = "not_started"
var codesignExit = "NOT_RUN"
var codesignOutput = "NOT_READ"
var certificateQuery = "NOT_CHECKED", identityQuery = "NOT_CHECKED"
var certificateType = false, certificateDER = false, identityType = false, identityDER = false
var selection: [String: Any]?
var codesignMarkers: [String: Bool] = ["marker_internal_component": false, "marker_interaction": false, "marker_authentication": false, "marker_identity": false, "marker_chain": false, "marker_format": false, "marker_permission": false, "marker_resource_fork": false]
func finish(_ value: String) -> Never {
    var result: [String: Any] = ["reason": value, "phase": phase, "error_class": errorClass,
                  "cleanup": cleanupState, "cleanup_error_class": cleanupError, "cleanup_phase": cleanupPhase]
    result["codesign_exit"] = codesignExit; result["codesign_output"] = codesignOutput
    result["certificate_query"] = certificateQuery; result["identity_query"] = identityQuery
    result["certificate_type"] = certificateType; result["certificate_der"] = certificateDER
    result["identity_type"] = identityType; result["identity_der"] = identityDER
    for (key, value) in codesignMarkers { result[key] = value }
    if let selection = selection { result["selection"] = selection }
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
let diagnoseIdentity = Array(CommandLine.arguments.dropFirst()) == ["--diagnose-identity"]
let diagnoseSelection = Array(CommandLine.arguments.dropFirst()) == ["--diagnose-selection"]
let selectionChild = Array(CommandLine.arguments.dropFirst()) == ["--selection-child"]
guard predicate("arguments", CommandLine.arguments.count == 1 || diagnoseIdentity || diagnoseSelection || selectionChild) else { finish("ARGUMENTS_REJECTED") }
phase = "platform"
guard #available(macOS 15.0, *) else { errorClass = "PREDICATE_REJECTED"; finish("PLATFORM_UNSUPPORTED") }
let fm = FileManager.default
let cwd = URL(fileURLWithPath: fm.currentDirectoryPath).standardizedFileURL
let parent = cwd.deletingLastPathComponent()
// OS authority, never child TMPDIR: the private task root is an immediate child.
var tempBuffer = [CChar](repeating: 0, count: 4096)
let tempLength = confstr(_CS_DARWIN_USER_TEMP_DIR, &tempBuffer, 4096)
guard predicate("temp_lookup", tempLength > 1 && tempLength <= tempBuffer.count) else { finish("PATH_REJECTED") }
let tempPath = String(cString: tempBuffer)
guard predicate("temp_absolute", tempPath.hasPrefix("/")) else { finish("PATH_REJECTED") }
let temporary = URL(fileURLWithPath: tempPath).standardizedFileURL.resolvingSymlinksInPath()
guard predicate("cwd_name", cwd.lastPathComponent == "custody") else { finish("PATH_REJECTED") }
guard predicate("root_name", parent.lastPathComponent.hasPrefix("task-197-")) else { finish("PATH_REJECTED") }
guard predicate("cwd_canonical", cwd.resolvingSymlinksInPath().pathComponents == cwd.pathComponents) else { finish("PATH_REJECTED") }
guard predicate("temp_binding", parent.deletingLastPathComponent().pathComponents == temporary.pathComponents) else { finish("PATH_REJECTED") }
var rootInfo = stat()
guard predicate("root_stat", lstat(parent.path, &rootInfo) == 0) else { finish("PATH_REJECTED") }
guard predicate("root_owner", rootInfo.st_uid == getuid()) else { finish("PATH_REJECTED") }
guard predicate("root_mode", rootInfo.st_mode & 0o777 == 0o700) else { finish("PATH_REJECTED") }
guard predicate("root_type", rootInfo.st_mode & S_IFMT == S_IFDIR) else { finish("PATH_REJECTED") }
var directoryInfo = stat()
guard predicate("directory_stat", lstat(cwd.path, &directoryInfo) == 0) else { finish("PATH_REJECTED") }
guard predicate("directory_owner", directoryInfo.st_uid == getuid()) else { finish("PATH_REJECTED") }
guard predicate("directory_mode", directoryInfo.st_mode & 0o777 == 0o700) else { finish("PATH_REJECTED") }
guard predicate("directory_type", directoryInfo.st_mode & S_IFMT == S_IFDIR) else { finish("PATH_REJECTED") }
let path = cwd.appendingPathComponent("fictional-task197.keychain-db").path
if !selectionChild {
    guard predicate("path_empty", (try? fm.contentsOfDirectory(atPath: cwd.path)) == []) else { finish("PATH_REJECTED") }
}
var input = Data()
let inputLimit = selectionChild ? 4096 : 131081
while input.count <= inputLimit {
    let part = FileHandle.standardInput.readData(ofLength: min(4096, inputLimit + 1 - input.count))
    if part.isEmpty { break }
    input.append(part)
}
let p12: Data
let expected: Data
if selectionChild {
    guard predicate("frame", !input.isEmpty && input.count <= 4096) else { finish("FRAME_REJECTED") }
    p12 = Data(); expected = input
} else {
    guard predicate("frame", input.count >= 9 && input.count <= 131081) else { finish("FRAME_REJECTED") }
    func length(_ offset: Int) -> Int { input[offset..<(offset + 4)].reduce(0) { ($0 << 8) | Int($1) } }
    let p12Length = length(1), certLength = length(5)
    guard predicate("frame", input[0] <= 1 && p12Length > 0 && p12Length <= 65536 && certLength > 0 && certLength <= 65536 && input.count == 9 + p12Length + certLength) else { finish("FRAME_REJECTED") }
    p12 = input.subdata(in: 9..<(9 + p12Length))
    expected = input.subdata(in: (9 + p12Length)..<input.count)
}
if selectionChild {
    guard predicate("frame", !input.isEmpty && input.count <= 4096) else { finish("FRAME_REJECTED") }
    var info = stat()
    guard predicate("child_path", lstat(path, &info) == 0 && info.st_mode & S_IFMT == S_IFREG && info.st_nlink == 1 && info.st_uid == getuid()) else { finish("PATH_REJECTED") }
    var opened: SecKeychain?
    guard status("disable_interaction", SecKeychainSetUserInteractionAllowed(false)), status("child_open", SecKeychainOpen(path, &opened)), let opened = opened else { finish("CUSTODY_REJECTED") }
    let observed = selectionScope(opened, expectedDER: input)
    let data = try! JSONSerialization.data(withJSONObject: observed, options: [.sortedKeys])
    FileHandle.standardOutput.write(data)
    exit(0)
}
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

@discardableResult
func observeIdentity(_ target: SecKeychain, expectedDER: Data? = nil) -> SecIdentity? {
    let wanted = expectedDER ?? expected
    var found: SecIdentity?
    func query(_ kind: CFString) -> (String, CFTypeRef?) {
        let attributes: [String: Any] = [kSecClass as String: kind,
            kSecMatchSearchList as String: [target] as CFArray,
            kSecMatchLimit as String: kSecMatchLimitOne,
            kSecReturnRef as String: true]
        var item: CFTypeRef?
        let result = SecItemCopyMatching(attributes as CFDictionary, &item)
        return (result == errSecSuccess ? "FOUND" : result == errSecItemNotFound ? "NOT_FOUND" : "ERROR", item)
    }
    var item: CFTypeRef?
    (certificateQuery, item) = query(kSecClassCertificate)
    if certificateQuery == "FOUND", let item = item, CFGetTypeID(item) == SecCertificateGetTypeID() {
        certificateType = true
        let certificate = item as! SecCertificate
        certificateDER = SecCertificateCopyData(certificate) as Data == wanted
    }
    (identityQuery, item) = query(kSecClassIdentity)
    if identityQuery == "FOUND", let item = item, CFGetTypeID(item) == SecIdentityGetTypeID() {
        identityType = true
        let identity = item as! SecIdentity
        found = identity
        var certificate: SecCertificate?
        if SecIdentityCopyCertificate(identity, &certificate) == errSecSuccess, let certificate = certificate {
            identityDER = SecCertificateCopyData(certificate) as Data == wanted
        }
    }
    phase = "identity_observation"; errorClass = "OS_SUCCESS"
    return found
}

func selectionScope(_ target: SecKeychain, expectedDER: Data) -> [String: Any] {
    let found = observeIdentity(target, expectedDER: expectedDER)
    var result: [String: Any] = ["certificate_query": certificateQuery, "certificate_type": certificateType, "certificate_der": certificateDER,
        "identity_query": identityQuery, "identity_type": identityType, "identity_der": identityDER,
        "key_status": "NOT_CHECKED", "key_can_sign_typed": false, "key_can_sign": false, "key_target": false]
    if let found = found {
        result["key_status"] = "ERROR"
        var key: SecKey?
        if SecIdentityCopyPrivateKey(found, &key) == errSecSuccess, let key = key {
            var owner: SecKeychain?
            let item = unsafeBitCast(key, to: SecKeychainItem.self)
            let associated = SecKeychainItemCopyKeychain(item, &owner) == errSecSuccess && owner != nil && CFEqual(owner!, target)
            result["key_target"] = associated
            if let attributes = SecKeyCopyAttributes(key) as? [String: Any], let canSign = attributes[kSecAttrCanSign as String], CFGetTypeID(canSign as CFTypeRef) == CFBooleanGetTypeID() {
                result["key_can_sign_typed"] = true
                result["key_can_sign"] = CFEqual(canSign as CFTypeRef, kCFBooleanTrue)
                result["key_status"] = associated ? "FOUND" : "ERROR"
            }
        }
    }
    return result
}

func selectionChildObservation() -> (String, [String: Any]) {
    let executable = parent.appendingPathComponent("native")
    var info = stat()
    guard executable.resolvingSymlinksInPath().pathComponents == executable.pathComponents,
          URL(fileURLWithPath: CommandLine.arguments[0]).standardizedFileURL.resolvingSymlinksInPath().pathComponents == executable.pathComponents,
          lstat(executable.path, &info) == 0, info.st_mode & S_IFMT == S_IFREG, info.st_uid == getuid(), info.st_mode & 0o777 == 0o700,
          !expected.isEmpty && expected.count <= 4096 else { return ("FAILED", [:]) }
    let child = Process(), inputPipe = Pipe(), outputPipe = Pipe()
    child.executableURL = executable; child.arguments = ["--selection-child"]
    child.currentDirectoryURL = cwd; child.environment = ["PATH": "/usr/bin:/bin", "LANG": "en_US.UTF-8"]
    child.standardInput = inputPipe; child.standardOutput = outputPipe; child.standardError = FileHandle.nullDevice
    defer { try? inputPipe.fileHandleForWriting.close(); try? inputPipe.fileHandleForReading.close(); try? outputPipe.fileHandleForReading.close(); try? outputPipe.fileHandleForWriting.close() }
    let writer = inputPipe.fileHandleForWriting.fileDescriptor, reader = outputPipe.fileHandleForReading.fileDescriptor
    guard fcntl(writer, F_SETFL, O_NONBLOCK) == 0, fcntl(reader, F_SETFL, O_NONBLOCK) == 0 else { return ("FAILED", [:]) }
    signal(SIGPIPE, SIG_IGN)
    let ended = DispatchSemaphore(value: 0)
    child.terminationHandler = { _ in ended.signal() }
    do { try child.run() } catch { return ("FAILED", [:]) }
    try? inputPipe.fileHandleForReading.close(); try? outputPipe.fileHandleForWriting.close()
    var sent = 0, output = Data(), eof = false, stopped = false, failed = false
    let deadline = ProcessInfo.processInfo.systemUptime + 20
    while ProcessInfo.processInfo.systemUptime < deadline {
        if sent < expected.count {
            let count = expected.withUnsafeBytes { bytes in write(writer, bytes.baseAddress!.advanced(by: sent), expected.count - sent) }
            if count > 0 { sent += count; if sent == expected.count { try? inputPipe.fileHandleForWriting.close() } }
            else if count < 0 && errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR { failed = true; break }
        }
        var buffer = [UInt8](repeating: 0, count: 1024)
        let count = read(reader, &buffer, min(1024, 4097 - output.count))
        if count > 0 { output.append(contentsOf: buffer.prefix(count)); if output.count > 4096 { failed = true; break } }
        else if count == 0 { eof = true }
        else if errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR { failed = true; break }
        if !stopped { stopped = ended.wait(timeout: .now() + 0.01) == .success }
        else if !eof { usleep(10000) }
        if stopped && eof { break }
    }
    if !stopped {
        if child.isRunning { kill(child.processIdentifier, SIGKILL) }
        if ended.wait(timeout: .now() + 2) == .timedOut { return ("UNREAPED", [:]) }
        return (failed ? "FAILED" : "TIMEOUT", [:])
    }
    guard !failed && eof && sent == expected.count && child.terminationReason == .exit && child.terminationStatus == 0,
          let object = try? JSONSerialization.jsonObject(with: output), let value = object as? [String: Any] else { return ("FAILED", [:]) }
    let statuses = ["certificate_query", "identity_query", "key_status"]
    let booleans = ["certificate_type", "certificate_der", "identity_type", "identity_der", "key_can_sign_typed", "key_can_sign", "key_target"]
    guard Set(value.keys) == Set(statuses + booleans), statuses.allSatisfy({ key in (value[key] as? String).map { ["NOT_CHECKED", "FOUND", "NOT_FOUND", "ERROR"].contains($0) } ?? false }), booleans.allSatisfy({ key in value[key].map { CFGetTypeID($0 as CFTypeRef) == CFBooleanGetTypeID() } ?? false }) else { return ("FAILED", [:]) }
    return ("COMPLETE", value)
}

func crossProcessSign() -> Bool {
    guard !diagnoseIdentity && !diagnoseSelection && !selectionChild else { return false }
    let fixture = parent.appendingPathComponent("fictional-mach-o")
    var info = stat()
    guard predicate("fixture_canonical", fixture.resolvingSymlinksInPath().pathComponents == fixture.pathComponents),
          predicate("fixture_stat", lstat(fixture.path, &info) == 0),
          predicate("fixture_owner", info.st_uid == getuid()),
          predicate("fixture_mode", info.st_mode & 0o777 == 0o700),
          predicate("fixture_regular", info.st_mode & S_IFMT == S_IFREG && info.st_nlink == 1),
          predicate("fixture_size", info.st_size > 0 && info.st_size <= 1048576) else { return false }
    let fingerprint = Insecure.SHA1.hash(data: expected).map { String(format: "%02x", $0) }.joined()
    let child = Process()
    child.executableURL = URL(fileURLWithPath: "/usr/bin/codesign")
    child.arguments = ["--force", "--sign", fingerprint, "--keychain", path,
                       "--timestamp=none", "--identifier", "invalid.fictional.task197", fixture.path]
    child.currentDirectoryURL = parent
    child.environment = ["PATH": "/usr/bin:/bin", "LANG": "en_US.UTF-8"]
    child.standardInput = FileHandle.nullDevice
    child.standardOutput = FileHandle.nullDevice
    let stderrPipe = Pipe()
    child.standardError = stderrPipe
    defer { try? stderrPipe.fileHandleForReading.close(); try? stderrPipe.fileHandleForWriting.close() }
    let descriptor = stderrPipe.fileHandleForReading.fileDescriptor
    guard predicate("codesign_pipe", fcntl(descriptor, F_SETFL, O_NONBLOCK) == 0) else { return false }
    var captured = Data()
    var eof = false
    func drain() -> Bool {
        var buffer = [UInt8](repeating: 0, count: 1024)
        while true {
            let count = read(descriptor, &buffer, min(1024, 8193 - captured.count))
            if count > 0 {
                captured.append(contentsOf: buffer.prefix(count))
                if captured.count > 8192 { codesignOutput = "OVERFLOW"; return false }
            } else if count == 0 { eof = true; return true }
            else if errno == EAGAIN || errno == EWOULDBLOCK { return true }
            else if errno == EINTR { return true }
            else { codesignOutput = "READ_FAILED"; return false }
        }
    }
    let ended = DispatchSemaphore(value: 0)
    child.terminationHandler = { _ in ended.signal() }
    phase = "codesign_launch"; errorClass = "PREDICATE_REJECTED"
    do { try child.run() } catch { return false }
    try? stderrPipe.fileHandleForWriting.close()
    let deadline = ProcessInfo.processInfo.systemUptime + 20
    var endedNormally = false
    var readable = true
    while ProcessInfo.processInfo.systemUptime < deadline {
        readable = drain()
        if !readable { break }
        if ended.wait(timeout: .now() + 0.01) == .success { endedNormally = true; break }
    }
    if !endedNormally {
        codesignExit = readable ? "TIMEOUT" : "OUTPUT_STOP"
        if child.isRunning { kill(child.processIdentifier, SIGKILL) }
        if ended.wait(timeout: .now() + 2) == .timedOut {
            cleanupState = "UNRESOLVED"; cleanupPhase = "not_started"
            finish("CLEANUP_UNRESOLVED")
        }
        phase = readable ? "codesign_timeout" : "codesign_output"; errorClass = "PREDICATE_REJECTED"
        return false
    }
    codesignExit = child.terminationReason == .exit ? (child.terminationStatus == 0 ? "ZERO" : "NONZERO") : "SIGNAL"
    let drainDeadline = ProcessInfo.processInfo.systemUptime + 2
    while !eof && ProcessInfo.processInfo.systemUptime < drainDeadline {
        if !drain() { break }
        if !eof { usleep(10000) }
    }
    guard predicate("codesign_output", eof && codesignOutput == "NOT_READ") else {
        if codesignOutput == "NOT_READ" { codesignOutput = "READ_FAILED" }
        return false
    }
    codesignOutput = "BOUNDED"
    let text = String(decoding: captured, as: UTF8.self).lowercased()
    let markers = ["marker_internal_component": ["errsecinternalcomponent"], "marker_interaction": ["interaction is not allowed", "errsecinteractionnotallowed"], "marker_authentication": ["authentication failed", "errsecauthfailed"], "marker_identity": ["specified item could not be found", "no identity found", "identity not found"], "marker_chain": ["unable to build chain", "not trusted"], "marker_format": ["unrecognized, invalid, or unsuitable", "invalid format"], "marker_permission": ["permission denied", "operation not permitted"], "marker_resource_fork": ["resource fork", "finder information"]]
    for (key, needles) in markers { codesignMarkers[key] = needles.contains { text.contains($0) } }
    guard predicate("codesign_exit", child.terminationReason == .exit && child.terminationStatus == 0) else { return false }
    var requirement: SecRequirement?
    let expression = "certificate leaf = H\"" + fingerprint + "\""
    guard status("requirement", SecRequirementCreateWithString(expression as CFString, [], &requirement)),
          let requirement = requirement else { return false }
    func verify() -> OSStatus {
        var code: SecStaticCode?
        let created = SecStaticCodeCreateWithPath(fixture as CFURL, [], &code)
        guard created == errSecSuccess, let code = code else { return created == errSecSuccess ? errSecParam : created }
        // CSCommon.h/SecStaticCode.h: kSecCSNoNetworkAccess (1<<29),
        // kSecCSStrictValidate (1<<4), kSecCSCheckAllArchitectures (1).
        return SecStaticCodeCheckValidity(code, SecCSFlags(rawValue: 0x20000011), requirement)
    }
    guard status("signature_binding", verify()) else { return false }
    var signedCode: SecStaticCode?
    var signingInfo: CFDictionary?
    guard status("signed_code", SecStaticCodeCreateWithPath(fixture as CFURL, [], &signedCode)), let signedCode = signedCode,
          status("signing_info", SecCodeCopySigningInformation(signedCode, SecCSFlags(rawValue: kSecCSSigningInformation), &signingInfo)),
          let values = signingInfo as? [String: Any], let certificates = values[kSecCodeInfoCertificates as String] as? [SecCertificate],
          predicate("signed_certificate_count", certificates.count == 1),
          predicate("signed_certificate_der", SecCertificateCopyData(certificates[0]) as Data == expected) else { return false }
    phase = "tamper_write"; errorClass = "PREDICATE_REJECTED"
    do {
        let handle = try FileHandle(forUpdating: fixture)
        defer { try? handle.close() }
        let data = try handle.read(upToCount: 1048577) ?? Data()
        guard predicate("signed_size", data.count <= 1048576) else { return false }
        let marker = Data("fictional-task197-tamper-marker".utf8)
        guard let range = data.range(of: marker),
              predicate("tamper_marker", data.range(of: marker, in: range.upperBound..<data.endIndex) == nil) else { return false }
        try handle.seek(toOffset: UInt64(range.lowerBound))
        try handle.write(contentsOf: Data([data[range.lowerBound] ^ 1]))
        try handle.synchronize()
    } catch { return false }
    let tampered = verify()
    return predicate("tamper_rejected", tampered == errSecCSSignatureFailed)
}

var keychain: SecKeychain?
var trustedApplication: SecTrustedApplication?
var access: SecAccess?
var signingApplication: SecTrustedApplication?
guard status("trusted_application", SecTrustedApplicationCreateFromPath(nil, &trustedApplication)),
      let trustedApplication = trustedApplication else { finish("CUSTODY_REJECTED") }
guard status("signing_application", SecTrustedApplicationCreateFromPath("/usr/bin/codesign", &signingApplication)),
      let signingApplication = signingApplication else { finish("CUSTODY_REJECTED") }
guard status("access", SecAccessCreate("fictional-task197-helper-and-codesign-only" as CFString, [trustedApplication, signingApplication] as CFArray, &access)),
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
        } else if importOK && diagnoseSelection {
            let observed = selectionScope(target, expectedDER: expected)
            let (childStatus, childObserved) = selectionChildObservation()
            selection = ["native_policy_qualification": "NOT_EVALUATED", "parent": observed, "child_status": childStatus, "child": childObserved]
            if childStatus == "UNREAPED" { cleanupState = "UNRESOLVED"; finish("CLEANUP_UNRESOLVED") }
            phase = "selection_observation"; errorClass = "OS_SUCCESS"
            reason = "SELECTION_OBSERVED"
        } else if importOK && diagnoseIdentity {
            observeIdentity(target)
            reason = "IDENTITY_OBSERVED"
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
                                    if crossProcessSign() { reason = "SIGNING_VERIFIED" }
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
