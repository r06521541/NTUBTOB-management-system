// Fictional stdin-only test harness. Never use default persistent PKCS12 import.
import Foundation
import Security

func finish(_ reason: String) -> Never {
    print(reason)
    exit(0)
}

guard CommandLine.arguments.count == 1 else { finish("ARGUMENTS_REJECTED") }
guard #available(macOS 15.0, *) else { finish("PLATFORM_UNSUPPORTED") }

// Three fields: selector byte, big-endian P12 length and certificate length,
// followed by their bytes. Read at most the bounded envelope plus one byte.
let limit = 65536
var input = Data()
while input.count <= 2 * limit + 9 {
    let chunk = FileHandle.standardInput.readData(ofLength: min(4096, 2 * limit + 10 - input.count))
    if chunk.isEmpty { break }
    input.append(chunk)
}
guard input.count >= 9, input.count <= 2 * limit + 9 else { finish("FRAME_REJECTED") }
func length(_ offset: Int) -> Int {
    input[offset..<(offset + 4)].reduce(0) { ($0 << 8) | Int($1) }
}
let p12Length = length(1)
let certLength = length(5)
guard input[0] <= 1, p12Length > 0, p12Length <= limit,
      certLength > 0, certLength <= limit,
      input.count == 9 + p12Length + certLength else { finish("FRAME_REJECTED") }
let password = input[0] == 0 ? "fictional-new-password" : "fictional-wrong-password"
let p12 = input.subdata(in: 9..<(9 + p12Length))
let expected = input.subdata(in: (9 + p12Length)..<input.count)
let options: [String: Any] = [
    kSecImportExportPassphrase as String: password,
    kSecImportToMemoryOnly as String: true
]
var imported: CFArray?
let status = SecPKCS12Import(p12 as CFData, options as CFDictionary, &imported)
if status == errSecAuthFailed { finish("AUTH_REJECTED") }
if status == errSecDecode { finish("DECODE_REJECTED") }
guard status == errSecSuccess else { finish("IMPORT_REJECTED") }
guard let items = imported as? [[String: Any]], items.count == 1,
      let value = items[0][kSecImportItemIdentity as String],
      CFGetTypeID(value as CFTypeRef) == SecIdentityGetTypeID() else { finish("IDENTITY_REJECTED") }
let identity = value as! SecIdentity
var certificate: SecCertificate?
guard SecIdentityCopyCertificate(identity, &certificate) == errSecSuccess,
      let certificate = certificate,
      SecCertificateCopyData(certificate) as Data == expected else { finish("CERTIFICATE_MISMATCH") }
var privateKey: SecKey?
guard SecIdentityCopyPrivateKey(identity, &privateKey) == errSecSuccess,
      let privateKey = privateKey,
      let publicKey = SecCertificateCopyKey(certificate) else { finish("KEY_REJECTED") }
let algorithm = SecKeyAlgorithm.rsaSignatureMessagePKCS1v15SHA256
let challenge = Data("fictional-memory-challenge-not-app-signing".utf8)
guard SecKeyIsAlgorithmSupported(privateKey, .sign, algorithm),
      let signature = SecKeyCreateSignature(privateKey, algorithm, challenge as CFData, nil),
      SecKeyVerifySignature(publicKey, algorithm, challenge as CFData, signature, nil) else {
    finish("KEY_REJECTED")
}
finish("MEMORY_IMPORT_VERIFIED")
