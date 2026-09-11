// TASK198 callable manual Runner signing. No CLI credentials, upload or trust override.
import Foundation
import Security
import Darwin
import CryptoKit

let fm = FileManager.default
var stage = "input", operation = "REJECTED", cleanup = "NOT_STARTED"
func finish() -> Never {
    let value = ["stage": stage, "operation": operation, "cleanup": cleanup]
    let data = try! JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
    FileHandle.standardOutput.write(data); exit(0)
}
func matches(_ value: String, _ pattern: String) -> Bool {
    value.range(of: pattern, options: .regularExpression) != nil
}
func directory(_ url: URL, privateMode: Bool = false) -> Bool {
    var info = stat()
    return url.pathComponents == url.resolvingSymlinksInPath().pathComponents && lstat(url.path, &info) == 0 && info.st_mode & S_IFMT == S_IFDIR && (!privateMode || (info.st_uid == getuid() && info.st_mode & 0o777 == 0o700))
}
guard CommandLine.arguments.count == 2, #available(macOS 15.0, *) else { finish() }
let root = URL(fileURLWithPath: fm.currentDirectoryPath).standardizedFileURL
let repo = URL(fileURLWithPath: CommandLine.arguments[1]).standardizedFileURL
var temp = [CChar](repeating: 0, count: 4096)
let size = confstr(_CS_DARWIN_USER_TEMP_DIR, &temp, temp.count)
guard size > 1 && size <= temp.count else { finish() }
let osTemp = URL(fileURLWithPath: String(cString: temp)).standardizedFileURL.resolvingSymlinksInPath()
guard directory(root, privateMode: true), directory(repo), root.lastPathComponent.hasPrefix("task-198-"), root.deletingLastPathComponent().pathComponents == osTemp.pathComponents else { finish() }
umask(0o077)
var input = Data()
while input.count <= 524288 {
    let part = FileHandle.standardInput.readData(ofLength: min(4096, 524289-input.count))
    if part.isEmpty { break }; input.append(part)
}
guard input.count <= 524288,
      let fields = try? JSONSerialization.jsonObject(with: input) as? [String: Any],
      Set(fields.keys) == Set(["p12","password","profile","certificate","team","uuid","version","build","defines"]),
      let p12s=fields["p12"] as? String, let p12=Data(base64Encoded:p12s), p12.count > 0, p12.count <= 65536,
      let password=fields["password"] as? String, !password.isEmpty, password.utf8.count <= 1024, !password.contains("\0"),
      let profiles=fields["profile"] as? String, let profile=Data(base64Encoded:profiles), profile.count > 0, profile.count <= 262144,
      let certs=fields["certificate"] as? String, let expected=Data(base64Encoded:certs), expected.count > 0, expected.count <= 65536,
      let team=fields["team"] as? String, matches(team,"^[A-Z0-9]{10}$"),
      let uuid=fields["uuid"] as? String, matches(uuid,"^[A-Fa-f0-9]{8}(-[A-Fa-f0-9]{4}){3}-[A-Fa-f0-9]{12}$"),
      let version=fields["version"] as? String, matches(version,"^[0-9]{1,4}\\.[0-9]{1,4}\\.[0-9]{1,4}$"),
      let build=fields["build"] as? NSNumber, CFGetTypeID(build) != CFBooleanGetTypeID(), build.int64Value > 0, build.int64Value <= 2147483647, build.doubleValue == Double(build.int64Value),
      let definitions=fields["defines"] as? [String:String], Set(definitions.keys)==Set(["API_BASE_URL","LINE_CHANNEL_ID","GOOGLE_CLIENT_ID","GOOGLE_SERVER_CLIENT_ID"]),
      definitions.values.allSatisfy({ !$0.isEmpty && $0.utf8.count<=2048 && matches($0,"^[A-Za-z0-9:/._-]+$") }) else { finish() }
let app=repo.appendingPathComponent("clients/flutter_app")
let ios=app.appendingPathComponent("ios")
stage="paths"
guard directory(ios.appendingPathComponent("Flutter")), directory(ios.appendingPathComponent("Runner")),
      definitions["API_BASE_URL"]!.hasPrefix("https://"), matches(definitions["LINE_CHANNEL_ID"]!,"^[0-9]+$"),
      ["GOOGLE_CLIENT_ID","GOOGLE_SERVER_CLIENT_ID"].allSatisfy({ matches(definitions[$0]!,"^[A-Za-z0-9-]+\\.apps\\.googleusercontent\\.com$") }) else { finish() }
// System CMS content extraction only. No signer/trust/policy call or custom algorithm gate.
stage="profile"
var decoder: CMSDecoder?
guard CMSDecoderCreate(&decoder)==errSecSuccess, let decoder=decoder else { finish() }
let updated=profile.withUnsafeBytes { CMSDecoderUpdateMessage(decoder,$0.baseAddress!,profile.count) }
var content: CFData?
guard updated==errSecSuccess, CMSDecoderFinalizeMessage(decoder)==errSecSuccess,
      CMSDecoderCopyContent(decoder,&content)==errSecSuccess, let content=content, CFDataGetLength(content)<=262144,
      let plist=try? PropertyListSerialization.propertyList(from:content as Data,options:[],format:nil) as? [String:Any],
      plist["UUID"] as? String == uuid, plist["TeamIdentifier"] as? [String] == [team],
      plist["ApplicationIdentifierPrefix"] as? [String] == [team], plist["Platform"] as? [String] == ["iOS"],
      plist["DeveloperCertificates"] as? [Data] == [expected], plist["ProvisionedDevices"] == nil,
      let expires=plist["ExpirationDate"] as? Date, let created=plist["CreationDate"] as? Date, created<=Date(), Date()<expires,
      let ent=plist["Entitlements"] as? [String:Any],
      ent["application-identifier"] as? String == team+".tw.org.ntubtob.portal",
      ent["com.apple.developer.team-identifier"] as? String == team,
      ent["com.apple.developer.applesignin"] as? [String] == ["Default"] else { finish() }
func boolean(_ value: Any?, _ expected: Bool) -> Bool {
    guard let number=value as? NSNumber, CFGetTypeID(number)==CFBooleanGetTypeID() else { return false }
    return number.boolValue==expected
}
guard boolean(ent["get-task-allow"],false), boolean(ent["beta-reports-active"],true), plist["ProvisionsAllDevices"] == nil || boolean(plist["ProvisionsAllDevices"],false) else { finish() }
// Resolve user home through account database; do not repurpose HOME or trust caller env.
guard let user=getpwuid(getuid()), let homePointer=user.pointee.pw_dir else { finish() }
let userHome=URL(fileURLWithPath:String(cString:homePointer)).standardizedFileURL
let profileDirectory=userHome.appendingPathComponent("Library/Developer/Xcode/UserData/Provisioning Profiles")
// Missing Xcode directories are normal on a fresh ephemeral user.
let installedProfile=profileDirectory.appendingPathComponent(uuid+".mobileprovision")
let authConfig=ios.appendingPathComponent("Flutter/AuthConfig.xcconfig")
let storeConfig=ios.appendingPathComponent("Flutter/StoreReleaseConfig.xcconfig")
let entitlement=ios.appendingPathComponent("Runner/Runner.entitlements")
let exportOptions=root.appendingPathComponent("ExportOptions.plist")
let archive=root.appendingPathComponent("Runner.xcarchive")
let exported=root.appendingPathComponent("export")
let keyPath=root.appendingPathComponent("signing.keychain-db").path
guard [installedProfile,authConfig,storeConfig,entitlement,exportOptions,archive,exported].allSatisfy({ !fm.fileExists(atPath:$0.path) }), !fm.fileExists(atPath:keyPath) else { finish() }
var owned: [(URL,dev_t,ino_t)] = []
var ownedDirectories: [(URL,dev_t,ino_t)] = []
var unidentifiedOutput=false
func profileDirectories() -> Bool {
    guard directory(userHome) else { return false }
    var cursor=userHome
    for part in ["Library","Developer","Xcode","UserData","Provisioning Profiles"] {
        cursor=cursor.appendingPathComponent(part)
        var info=stat()
        if lstat(cursor.path,&info) != 0 {
            guard errno==ENOENT, mkdir(cursor.path,0o700)==0 else { return false }
            guard lstat(cursor.path,&info)==0 else { unidentifiedOutput=true; return false }
            ownedDirectories.append((cursor,info.st_dev,info.st_ino))
        }
        guard directory(cursor), info.st_uid==getuid(), info.st_mode & 0o022 == 0 else { return false }
    }
    return true
}
func exclusive(_ path:URL,_ data:Data) -> Bool {
    let fd=open(path.path,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,0o600)
    guard fd>=0 else { return false }
    var info=stat()
    guard fstat(fd,&info)==0 else { unidentifiedOutput=true; close(fd); return false }
    owned.append((path,info.st_dev,info.st_ino))
    let okay=data.withUnsafeBytes { raw -> Bool in
        var offset=0
        while offset<data.count {
            let count=write(fd,raw.baseAddress!.advanced(by:offset),data.count-offset)
            if count<=0 { return false }; offset+=count
        }
        return fsync(fd)==0
    }
    close(fd); return okay
}
var beforeList: CFArray?, beforeDefault: SecKeychain?
stage="snapshot"
guard SecKeychainCopySearchList(&beforeList)==errSecSuccess, let savedList=beforeList else { finish() }
let defaultStatus=SecKeychainCopyDefault(&beforeDefault)
guard defaultStatus==errSecSuccess || defaultStatus==errSecNoDefaultKeychain else { finish() }
func unchangedDefault() -> Bool {
    var current: SecKeychain?
    guard SecKeychainCopyDefault(&current)==defaultStatus else { return false }
    if let before=beforeDefault, let current=current { return CFEqual(before,current) }
    return beforeDefault==nil && current==nil
}
var keychain: SecKeychain?, keyAttempted=false, childUnresolved=false
func clean() -> Bool {
    if childUnresolved { return false }
    var okay = !unidentifiedOutput
    if keyAttempted && SecKeychainSetSearchList(savedList) != errSecSuccess { okay=false }
    var after: CFArray?
    if SecKeychainCopySearchList(&after) != errSecSuccess || after == nil || !CFEqual(savedList,after!) || !unchangedDefault() { okay=false }
    if let target=keychain, SecKeychainDelete(target) != errSecSuccess { okay=false }
    if fm.fileExists(atPath:keyPath) { okay=false }
    for (path,device,inode) in owned.reversed() {
        var info=stat()
        if lstat(path.path,&info) != 0 || info.st_dev != device || info.st_ino != inode || unlink(path.path) != 0 { okay=false }
    }
    for (path,device,inode) in ownedDirectories.reversed() {
        var info=stat()
        if lstat(path.path,&info) != 0 || info.st_dev != device || info.st_ino != inode || rmdir(path.path) != 0 { okay=false }
    }
    var finalList:CFArray?
    if SecKeychainCopySearchList(&finalList) != errSecSuccess || finalList == nil || !CFEqual(savedList,finalList!) || !unchangedDefault() || fm.fileExists(atPath:keyPath) { okay=false }
    return okay
}
// Each Xcode child has its own process group; no shell, inherited private env or output.
func run(_ arguments:[String],timeout:Double) -> Bool {
    var actions=posix_spawn_file_actions_t(), attributes=posix_spawnattr_t()
    guard posix_spawn_file_actions_init(&actions)==0, posix_spawnattr_init(&attributes)==0 else { return false }
    defer { posix_spawn_file_actions_destroy(&actions); posix_spawnattr_destroy(&attributes) }
    guard posix_spawn_file_actions_addopen(&actions,STDIN_FILENO,"/dev/null",O_RDONLY,0)==0,
          posix_spawn_file_actions_addopen(&actions,STDOUT_FILENO,"/dev/null",O_WRONLY,0)==0,
          posix_spawn_file_actions_addopen(&actions,STDERR_FILENO,"/dev/null",O_WRONLY,0)==0,
          posix_spawnattr_setflags(&attributes,Int16(POSIX_SPAWN_SETPGROUP))==0,
          posix_spawnattr_setpgroup(&attributes,0)==0 else { return false }
    let environment=["PATH=/usr/bin:/bin","DEVELOPER_DIR=/Applications/Xcode_26.3.app/Contents/Developer","LANG=en_US.UTF-8"]
    let argv=arguments.map{strdup($0)}+[nil], env=environment.map{strdup($0)}+[nil]
    defer { argv.forEach{free($0)}; env.forEach{free($0)} }
    var pid:pid_t=0
    let launched=argv.withUnsafeBufferPointer { a in env.withUnsafeBufferPointer { e in posix_spawn(&pid,arguments[0],&actions,&attributes,a.baseAddress!,e.baseAddress!) } }
    guard launched==0 else { return false }
    let deadline=ProcessInfo.processInfo.systemUptime+timeout
    var state:Int32=0, ended=false
    while ProcessInfo.processInfo.systemUptime<deadline {
        let status=waitpid(pid,&state,WNOHANG)
        if status==pid { ended=true; break }
        if status<0 && errno != EINTR { break }
        usleep(100000)
    }
    // Also terminate lingering group members after leader success.
    kill(-pid,SIGKILL)
    let stopDeadline=ProcessInfo.processInfo.systemUptime+5
    while !ended && ProcessInfo.processInfo.systemUptime<stopDeadline {
        if waitpid(pid,&state,WNOHANG)==pid { ended=true; break }; usleep(100000)
    }
    while ProcessInfo.processInfo.systemUptime<stopDeadline && kill(-pid,0)==0 { usleep(100000) }
    if !ended || kill(-pid,0)==0 || errno != ESRCH { childUnresolved=true; return false }
    if ProcessInfo.processInfo.systemUptime>=deadline { operation="TIMEOUT" }
    return ended && state==0 && operation != "TIMEOUT"
}
func execute() -> Bool {
    guard profileDirectories() else { return false }
    guard SecKeychainSetUserInteractionAllowed(false)==errSecSuccess else { return false }
    var helper:SecTrustedApplication?, codesign:SecTrustedApplication?, access:SecAccess?
    guard SecTrustedApplicationCreateFromPath(nil,&helper)==errSecSuccess, let helper=helper,
          SecTrustedApplicationCreateFromPath("/usr/bin/codesign",&codesign)==errSecSuccess, let codesign=codesign,
          SecAccessCreate("task198-helper-and-codesign" as CFString,[helper,codesign] as CFArray,&access)==errSecSuccess, let access=access else { return false }
    var secret=[UInt8](repeating:0,count:32)
    guard SecRandomCopyBytes(kSecRandomDefault,secret.count,&secret)==errSecSuccess else { return false }
    let keyPassword=Data(secret).base64EncodedString()
    stage="create"; cleanup="UNRESOLVED"; keyAttempted=true
    let created=keyPassword.utf8CString.withUnsafeBytes { SecKeychainCreate(keyPath,UInt32(keyPassword.utf8.count),$0.baseAddress,false,nil,&keychain) }
    guard created==errSecSuccess, let target=keychain else { return false }
    // Finite idle locking, not a hard lifetime or substitute for deletion.
    var settings=SecKeychainSettings(version: UInt32(SEC_KEYCHAIN_SETTINGS_VERS1), lockOnSleep: true, useLockInterval: true, lockInterval: 2400)
    var observedSettings=SecKeychainSettings(version: UInt32(SEC_KEYCHAIN_SETTINGS_VERS1), lockOnSleep: false, useLockInterval: false, lockInterval: 0)
    guard SecKeychainSetSettings(target, &settings)==errSecSuccess,
          SecKeychainCopySettings(target, &observedSettings)==errSecSuccess,
          observedSettings.version == UInt32(SEC_KEYCHAIN_SETTINGS_VERS1),
          observedSettings.lockOnSleep.boolValue, observedSettings.useLockInterval.boolValue,
          observedSettings.lockInterval == 2400 else { return false }
    stage="import"
    var items:CFArray?
    let options:[String:Any]=[kSecImportExportPassphrase as String:password,kSecImportExportKeychain as String:target,kSecImportExportAccess as String:access]
    guard SecPKCS12Import(p12 as CFData,options as CFDictionary,&items)==errSecSuccess,
          let array=items as? [[String:Any]], array.count==1,
          let raw=array[0][kSecImportItemIdentity as String], CFGetTypeID(raw as CFTypeRef)==SecIdentityGetTypeID() else { return false }
    let identity=unsafeBitCast(raw as CFTypeRef,to:SecIdentity.self)
    var certificate:SecCertificate?, key:SecKey?, association:SecKeychain?
    guard SecIdentityCopyCertificate(identity,&certificate)==errSecSuccess, let certificate=certificate, SecCertificateCopyData(certificate) as Data==expected,
          SecIdentityCopyPrivateKey(identity,&key)==errSecSuccess, let key=key,
          SecKeychainItemCopyKeychain(unsafeBitCast(key,to:SecKeychainItem.self),&association)==errSecSuccess,
          let association=association, CFEqual(association,target), unchangedDefault() else { return false }
    stage="search"
    guard let old=savedList as? [SecKeychain] else { return false }
    let intended=([target]+old) as CFArray
    var installed:CFArray?
    guard SecKeychainSetSearchList(intended)==errSecSuccess, SecKeychainCopySearchList(&installed)==errSecSuccess, let installed=installed, CFEqual(intended,installed), unchangedDefault() else { return false }
    stage="config"
    var defs=definitions
    defs["APP_FLAVOR"]="staging"; defs["CLIENT_MODE"]="real"; defs["RELEASE_SCOPE"]="basic"
    let encoded=defs.keys.sorted().map{Data(($0+"="+defs[$0]!).utf8).base64EncodedString()}.joined(separator:",")
    let reversed=definitions["GOOGLE_CLIENT_ID"]!.split(separator:".").reversed().joined(separator:".")
    // SHA1 is an exact Xcode identity selector here, not a trust/signature algorithm.
    let selector=Insecure.SHA1.hash(data:expected).map{String(format:"%02X",$0)}.joined()
    let config="IOS_DISTRIBUTION_CHANNEL=testflight\nIOS_EXTERNAL_SIGNING_READY=YES\nCODE_SIGN_STYLE=Manual\nCODE_SIGN_IDENTITY=\(selector)\nCODE_SIGN_IDENTITY[sdk=iphoneos*]=\(selector)\nDEVELOPMENT_TEAM=\(team)\nPROVISIONING_PROFILE_SPECIFIER=\(uuid)\nCODE_SIGN_ENTITLEMENTS=Runner/Runner.entitlements\nFLUTTER_BUILD_NAME=\(version)\nFLUTTER_BUILD_NUMBER=\(build.int64Value)\nDART_DEFINES=\(encoded)\n"
    let optionsPlist:[String:Any]=["method":"app-store-connect","signingStyle":"manual","signingCertificate":selector,"teamID":team,"provisioningProfiles":["tw.org.ntubtob.portal":uuid],"manageAppVersionAndBuildNumber":false,"uploadSymbols":false,"destination":"export"]
    guard let entitlementData=try? PropertyListSerialization.data(fromPropertyList:["com.apple.developer.applesignin":["Default"]],format:.xml,options:0),
          let optionsData=try? PropertyListSerialization.data(fromPropertyList:optionsPlist,format:.xml,options:0),
          exclusive(installedProfile,profile), exclusive(authConfig,Data("GOOGLE_REVERSED_CLIENT_ID=\(reversed)\n".utf8)), exclusive(storeConfig,Data(config.utf8)), exclusive(entitlement,entitlementData), exclusive(exportOptions,optionsData) else { return false }
    let xcode="/Applications/Xcode_26.3.app/Contents/Developer/usr/bin/xcodebuild"
    stage="archive"
    guard run([xcode,"-workspace",ios.appendingPathComponent("Runner.xcworkspace").path,"-scheme","Runner","-configuration","Release","-sdk","iphoneos","-destination","generic/platform=iOS","-disableAutomaticPackageResolution","-onlyUsePackageVersionsFromResolvedFile","-derivedDataPath",root.appendingPathComponent("DerivedData").path,"-archivePath",archive.path,"archive"],timeout:1500) else { return false }
    stage="export"
    guard run([xcode,"-exportArchive","-archivePath",archive.path,"-exportPath",exported.path,"-exportOptionsPlist",exportOptions.path,"-disableAutomaticPackageResolution"],timeout:600) else { return false }
    return true
}
let succeeded=execute()
let cleaned=clean()
cleanup=cleaned ? "VERIFIED" : "UNRESOLVED"
if succeeded { operation="EXPORTED"; stage="complete" }
finish()
