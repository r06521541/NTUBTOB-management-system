// Compiled public anchor and build marker are prepended by the repository build.
// Internal stdin transport only; Python MUST validate canonical CMS first.
import Foundation
import Security

func emit(_ reason: String, _ fields: [String: Any] = [:]) -> Never {
    var result = fields
    result["reason"] = reason
    result["marker"] = buildMarker
    guard let output = try? JSONSerialization.data(withJSONObject: result, options: [.sortedKeys]),
          output.count <= 700000 else { exit(1) }
    FileHandle.standardOutput.write(output)
    exit(0)
}

guard CommandLine.arguments.count == 1 else { emit("CMS_BINDING_REJECTED") }
guard #available(macOS 15.0, *) else { emit("CMS_TRUST_REJECTED") }
let maximum = 1048576
var frame = Data()
while frame.count <= maximum + 12 {
    let chunk = FileHandle.standardInput.readData(ofLength: min(4096, maximum + 13 - frame.count))
    if chunk.isEmpty { break }
    frame.append(chunk)
}
guard frame.count > 12, frame.count <= maximum + 12 else { emit("CMS_BINDING_REJECTED") }
let dateBits = frame[0..<8].reduce(UInt64(0)) { ($0 << 8) | UInt64($1) }
let timestamp = Double(bitPattern: dateBits)
let length = frame[8..<12].reduce(0) { ($0 << 8) | Int($1) }
guard timestamp.isFinite, timestamp >= 978307200, timestamp < 253370764800,
      length == frame.count - 12 else { emit("CMS_BINDING_REJECTED") }
let cms = frame.subdata(in: 12..<frame.count)
guard let anchorData = Data(base64Encoded: compiledAnchor),
      let anchor = SecCertificateCreateWithData(nil, anchorData as CFData) else { emit("CMS_TRUST_REJECTED") }
var decoder: CMSDecoder?
guard CMSDecoderCreate(&decoder) == errSecSuccess, let decoder = decoder else { emit("CMS_SIGNATURE_REJECTED") }
let update = cms.withUnsafeBytes { bytes in
    CMSDecoderUpdateMessage(decoder, bytes.baseAddress!, bytes.count)
}
guard update == errSecSuccess, CMSDecoderFinalizeMessage(decoder) == errSecSuccess else { emit("CMS_SIGNATURE_REJECTED") }
var count = 0
var encrypted: DarwinBoolean = false
guard CMSDecoderGetNumSigners(decoder, &count) == errSecSuccess, count == 1,
      CMSDecoderIsContentEncrypted(decoder, &encrypted) == errSecSuccess, !encrypted.boolValue else { emit("CMS_SIGNATURE_REJECTED") }
let policy = SecPolicyCreateBasicX509()
var status = CMSSignerStatus.unsigned
var trust: SecTrust?
// certVerifyResultCode is undefined when evaluation is deferred: pass nil.
guard CMSDecoderCopySignerStatus(decoder, 0, policy, false, &status, &trust, nil) == errSecSuccess,
      status == .valid, let trust = trust else { emit("CMS_SIGNATURE_REJECTED") }
guard SecTrustSetPolicies(trust, policy) == errSecSuccess,
      SecTrustSetAnchorCertificates(trust, [anchor] as CFArray) == errSecSuccess,
      SecTrustSetAnchorCertificatesOnly(trust, true) == errSecSuccess,
      SecTrustSetNetworkFetchAllowed(trust, false) == errSecSuccess,
      SecTrustSetVerifyDate(trust, Date(timeIntervalSince1970: timestamp) as CFDate) == errSecSuccess else { emit("CMS_TRUST_REJECTED") }
guard SecTrustEvaluateWithError(trust, nil) else { emit("CMS_TRUST_REJECTED") }
guard let chain = SecTrustCopyCertificateChain(trust) as? [SecCertificate], chain.count == 3 else { emit("CMS_BINDING_REJECTED") }
var signer: SecCertificate?
var payload: CFData?
guard CMSDecoderCopySignerCert(decoder, 0, &signer) == errSecSuccess,
      let signer = signer,
      CMSDecoderCopyContent(decoder, &payload) == errSecSuccess,
      let payload = payload else { emit("CMS_BINDING_REJECTED") }
let signerData = SecCertificateCopyData(signer) as Data
let encodedChain = chain.map { SecCertificateCopyData($0) as Data }
guard signerData == encodedChain[0], encodedChain[2] == anchorData,
      (payload as Data).count <= 262144, encodedChain.allSatisfy({ $0.count <= 65536 }) else { emit("CMS_BINDING_REJECTED") }
emit("VERIFIED", ["payload": (payload as Data).base64EncodedString(),
                  "signer": signerData.base64EncodedString(),
                  "chain": encodedChain.map { $0.base64EncodedString() }])
