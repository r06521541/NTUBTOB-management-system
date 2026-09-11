"""Fictional no-key Xcode archive and temporary-Keychain control rehearsal only."""

import json
import os
import platform
import plistlib
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from tools import ios_pkcs12_compatibility as fixtures

DEVELOPER = "/Applications/Xcode_26.3.app/Contents/Developer"
XCODE = DEVELOPER + "/usr/bin/xcodebuild"
SOURCE = (
    Path(__file__).resolve().parent / "native/ios_temporary_keychain_rehearsal.swift"
)
BUNDLE = "invalid.fictional.task196"
MAX_OUTPUT = 262144
REASONS = frozenset(
    {
        "ARGUMENTS_REJECTED",
        "TOOLCHAIN_UNSUPPORTED",
        "PATH_REJECTED",
        "PROCESS_REJECTED",
        "PROCESS_TIMEOUT",
        "OUTPUT_REJECTED",
        "ARCHIVE_REJECTED",
        "CUSTODY_REJECTED",
        "EXPORT_INCONCLUSIVE",
        "CANCELLED",
        "CLEANUP_UNRESOLVED",
        "REHEARSAL_REJECTED",
        "CONTROL_VERIFIED_EXPORT_REJECTED",
    }
)
NATIVE_FIELDS = {
    "reason": frozenset(
        {
            "ARGUMENTS_REJECTED",
            "PLATFORM_UNSUPPORTED",
            "PATH_REJECTED",
            "FRAME_REJECTED",
            "CUSTODY_REJECTED",
            "AUTH_REJECTED",
            "CERTIFICATE_MISMATCH",
            "CUSTODY_VERIFIED",
            "CLEANUP_UNRESOLVED",
        }
    ),
    "phase": frozenset(
        {
            "arguments",
            "platform",
            "cwd_name",
            "root_name",
            "cwd_canonical",
            "temp_binding",
            "directory_stat",
            "directory_owner",
            "directory_mode",
            "directory_type",
            "path_empty",
            "frame",
            "search_snapshot",
            "default_snapshot",
            "disable_interaction",
            "trusted_application",
            "access",
            "create",
            "created_keychain",
            "search_read",
            "default_status",
            "search_shape",
            "search_match",
            "default_match",
            "import",
            "identity_array",
            "identity_count",
            "identity_value",
            "identity_type",
            "certificate",
            "certificate_value",
            "certificate_match",
            "private_key",
            "private_key_value",
            "public_key",
            "key_association",
            "key_value",
            "key_target",
            "algorithm",
            "sign",
            "verify",
        }
    ),
    "error_class": frozenset(
        {
            "NOT_CHECKED",
            "OS_SUCCESS",
            "OS_AUTH_FAILED",
            "OS_DECODE",
            "OS_INTERACTION_NOT_ALLOWED",
            "OS_ITEM_NOT_FOUND",
            "OS_PARAM",
            "OS_OTHER",
            "PREDICATE_REJECTED",
        }
    ),
    "cleanup": frozenset(
        {
            "NOT_CREATED",
            "UNRESOLVED",
            "DELETE_REJECTED",
            "METADATA_CHANGED",
            "RESIDUAL_FILES",
            "VERIFIED",
        }
    ),
    "cleanup_error_class": frozenset(
        {
            "NOT_CHECKED",
            "OS_SUCCESS",
            "OS_AUTH_FAILED",
            "OS_DECODE",
            "OS_INTERACTION_NOT_ALLOWED",
            "OS_ITEM_NOT_FOUND",
            "OS_PARAM",
            "OS_OTHER",
            "PREDICATE_REJECTED",
        }
    ),
    "cleanup_phase": frozenset(
        {
            "not_started",
            "delete",
            "search_read",
            "default_status",
            "search_shape",
            "search_match",
            "default_match",
            "file_absence",
            "directory_empty",
            "completed",
        }
    ),
}


def native_detail(output):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError
            result[key] = value
        return result

    try:
        if type(output) is not bytes or len(output) > 2048:
            raise ValueError
        result = json.loads(output.decode("ascii"), object_pairs_hook=unique)
        if (
            type(result) is not dict
            or set(result) != set(NATIVE_FIELDS)
            or any(
                type(result[key]) is not str or result[key] not in allowed
                for key, allowed in NATIVE_FIELDS.items()
            )
        ):
            raise ValueError
        if result["cleanup"] == "VERIFIED" and (
            result["cleanup_phase"] != "completed"
            or result["cleanup_error_class"] != "OS_SUCCESS"
        ):
            raise ValueError
        if result["cleanup"] == "NOT_CREATED" and (
            result["cleanup_phase"] != "not_started"
            or result["cleanup_error_class"] != "NOT_CHECKED"
        ):
            raise ValueError
        if result["reason"] == "CLEANUP_UNRESOLVED" and result["cleanup"] in {
            "VERIFIED",
            "NOT_CREATED",
        }:
            raise ValueError
        return {key: result[key] for key in NATIVE_FIELDS}
    except Exception:
        raise Rejected("OUTPUT_REJECTED") from None


class Rejected(Exception):
    pass


def safe_path(root, path):
    root, path = Path(root), Path(path)
    if (
        not root.is_absolute()
        or ".." in path.parts
        or not path.is_relative_to(root)
        or root.resolve() != root
        or path.resolve() != path
    ):
        raise Rejected("PATH_REJECTED")
    for item in (path, *path.parents):
        if item.exists() or item.is_symlink():
            if item.is_symlink():
                raise Rejected("PATH_REJECTED")
    return path


def process(args, *, cwd, payload=b"", timeout=30):
    """Bound both pipes and descendants; never return raw output to the CLI."""
    if type(payload) is not bytes or len(payload) > 131081:
        raise Rejected("PROCESS_REJECTED")
    child = None
    output, failures = [], []

    def stop():
        if child is not None:
            try:
                if os.name == "posix":
                    os.killpg(child.pid, signal.SIGKILL)
                elif child.poll() is None:
                    child.kill()
            except ProcessLookupError:
                pass

    def write():
        try:
            child.stdin.write(payload)
            child.stdin.close()
        except Exception:
            failures.append(True)

    def read():
        try:
            output.append(child.stdout.read(MAX_OUTPUT + 1))
            if len(output[0]) > MAX_OUTPUT:
                stop()
        except Exception:
            failures.append(True)

    workers = []
    try:
        child = subprocess.Popen(
            args,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env={
                "PATH": "/usr/bin:/bin",
                "DEVELOPER_DIR": DEVELOPER,
                "TMPDIR": str(cwd),
                "LANG": "en_US.UTF-8",
            },
            start_new_session=True,
        )
        workers = [
            threading.Thread(target=write, daemon=True),
            threading.Thread(target=read, daemon=True),
        ]
        for worker in workers:
            worker.start()
        try:
            child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            raise Rejected("PROCESS_TIMEOUT") from None
        for worker in workers:
            worker.join(2)
        if (
            any(worker.is_alive() for worker in workers)
            or failures
            or len(output) != 1
            or len(output[0]) > MAX_OUTPUT
        ):
            raise Rejected("OUTPUT_REJECTED")
        return child.returncode, output[0]
    finally:
        stop()
        if child is not None:
            child.wait(timeout=5)
            for worker in workers:
                worker.join(2)
            if not any(worker.is_alive() for worker in workers):
                child.stdin.close()
                child.stdout.close()


def checked(run, args, root, *, timeout=30):
    code, output = run(args, cwd=root, timeout=timeout)
    if code != 0 or type(output) is not bytes or len(output) > MAX_OUTPUT:
        raise Rejected("PROCESS_REJECTED")
    return output


def toolchain(run, root):
    if platform.system() != "Darwin" or platform.machine() not in {"arm64", "x86_64"}:
        raise Rejected("TOOLCHAIN_UNSUPPORTED")
    version = checked(run, ["/usr/bin/sw_vers", "-productVersion"], root).strip()
    build = checked(run, ["/usr/bin/sw_vers", "-buildVersion"], root).strip()
    if not re.fullmatch(rb"15\.[0-9]+(?:\.[0-9]+)?", version) or not re.fullmatch(
        rb"[0-9A-Z]{3,16}", build
    ):
        raise Rejected("TOOLCHAIN_UNSUPPORTED")
    if (
        checked(run, [XCODE, "-version"], root).strip()
        != b"Xcode 26.3\nBuild version 17C529"
        or checked(
            run, [XCODE, "-version", "-sdk", "iphoneos", "SDKVersion"], root
        ).strip()
        != b"26.2"
    ):
        raise Rejected("TOOLCHAIN_UNSUPPORTED")
    help_text = checked(run, [XCODE, "-help"], root)
    if not all(
        key in help_text
        for key in (
            b"-exportArchive",
            b"signingStyle",
            b"manual",
            b"destination",
            b"export",
            b"app-store-connect",
            b"provisioningProfiles",
            b"teamID",
            b"signingCertificate",
        )
    ):
        raise Rejected("TOOLCHAIN_UNSUPPORTED")
    return {
        "macos_version": version.decode("ascii"),
        "macos_build": build.decode("ascii"),
        "architecture": platform.machine(),
        "xcode": "26.3",
        "xcode_build": "17C529",
        "sdk": "26.2",
    }


def project(root):
    """Fixed no-package/no-script fictional app, not the product Runner project."""
    directory = safe_path(root, root / "Fictional.xcodeproj")
    directory.mkdir()
    (root / "main.m").write_text(
        "#import <UIKit/UIKit.h>\n@interface App : UIResponder <UIApplicationDelegate>\n@property(strong,nonatomic) UIWindow *window;\n@end\n@implementation App\n-(BOOL)application:(UIApplication*)app didFinishLaunchingWithOptions:(NSDictionary*)options { self.window=[[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds]; self.window.rootViewController=[UIViewController new]; [self.window makeKeyAndVisible]; return YES; }\n@end\nint main(int argc,char **argv) { @autoreleasepool { return UIApplicationMain(argc,argv,nil,NSStringFromClass(App.class)); } }\n"
    )
    (directory / "project.pbxproj").write_text(
        """// !$*UTF8*$!
{ archiveVersion = 1; classes = {}; objectVersion = 56; objects = {
 A00000000000000000000001 = {isa = PBXProject; buildConfigurationList = A00000000000000000000002; compatibilityVersion = "Xcode 14.0"; mainGroup = A00000000000000000000003; targets = (A00000000000000000000004,); };
 A00000000000000000000002 = {isa = XCConfigurationList; buildConfigurations = (A00000000000000000000005,); defaultConfigurationIsVisible = 0; defaultConfigurationName = Release; };
 A00000000000000000000003 = {isa = PBXGroup; children = (A00000000000000000000006,A00000000000000000000007,); sourceTree = "<group>"; };
 A00000000000000000000004 = {isa = PBXNativeTarget; buildConfigurationList = A00000000000000000000002; buildPhases = (A00000000000000000000008,); buildRules = (); dependencies = (); name = Fictional; productName = Fictional; productReference = A00000000000000000000007; productType = "com.apple.product-type.application"; };
 A00000000000000000000005 = {isa = XCBuildConfiguration; name = Release; buildSettings = { PRODUCT_NAME = Fictional; PRODUCT_BUNDLE_IDENTIFIER = invalid.fictional.task196; SDKROOT = iphoneos; IPHONEOS_DEPLOYMENT_TARGET = 18.0; TARGETED_DEVICE_FAMILY = "1,2"; CLANG_ENABLE_OBJC_ARC = YES; CLANG_ENABLE_MODULES = YES; OTHER_LDFLAGS = ("-framework", UIKit,); GENERATE_INFOPLIST_FILE = YES; INFOPLIST_KEY_UIApplicationSceneManifest_Generation = YES; CURRENT_PROJECT_VERSION = 1; MARKETING_VERSION = 1.0; CODE_SIGNING_ALLOWED = NO; CODE_SIGNING_REQUIRED = NO; CODE_SIGN_STYLE = Manual; SKIP_INSTALL = NO; }; };
 A00000000000000000000006 = {isa = PBXFileReference; lastKnownFileType = sourcecode.c.objc; path = main.m; sourceTree = "<group>"; };
 A00000000000000000000007 = {isa = PBXFileReference; explicitFileType = wrapper.application; path = Fictional.app; sourceTree = BUILT_PRODUCTS_DIR; };
 A00000000000000000000008 = {isa = PBXSourcesBuildPhase; buildActionMask = 2147483647; files = (A00000000000000000000009,); runOnlyForDeploymentPostprocessing = 0; };
 A00000000000000000000009 = {isa = PBXBuildFile; fileRef = A00000000000000000000006; };
 }; rootObject = A00000000000000000000001; }
"""
    )


def expected_export_rejection(code, output):
    return (
        code != 0
        and type(output) is bytes
        and len(output) <= MAX_OUTPUT
        and any(
            text in output
            for text in (
                b"requires a provisioning profile",
                b"No profiles for",
                b"No signing certificate",
            )
        )
    )


def cleanup(root, identity):
    info = root.lstat()
    if (
        root.is_symlink()
        or (info.st_dev, info.st_ino) != identity
        or root.parent != Path(tempfile.gettempdir()).resolve()
        or not root.name.startswith("task-196-")
    ):
        raise Rejected("CLEANUP_UNRESOLVED")
    shutil.rmtree(root)
    if root.exists():
        raise Rejected("CLEANUP_UNRESOLVED")


def rehearse(*, _run=process):
    result = {
        "classification": "REHEARSAL_REJECTED",
        "stage": "preflight",
        "archive_created_without_key": False,
        "temporary_keychain_verified": False,
        "manual_export_rejected": False,
        "cleanup_verified": False,
        "positive_export_verified": False,
        "real_assets_verified": False,
        "real_signing_authorized": False,
        "signing_authorized": False,
        "upload_authorized": False,
        "release_authorized": False,
    }
    root = None
    custody_active = False
    try:
        if platform.system() != "Darwin":
            raise Rejected("TOOLCHAIN_UNSUPPORTED")
        root = Path(tempfile.mkdtemp(prefix="task-196-")).resolve()
        os.chmod(root, 0o700)
        identity = (root.stat().st_dev, root.stat().st_ino)
        result["toolchain"] = toolchain(_run, root)
        project(root)
        binary = safe_path(root, root / "native")
        checked(
            _run,
            ["/usr/bin/xcrun", "swiftc", str(SOURCE), "-o", str(binary)],
            root,
            timeout=90,
        )
        result["stage"] = "archive"
        archive = safe_path(root, root / "Fictional.xcarchive")
        checked(
            _run,
            [
                XCODE,
                "-project",
                str(root / "Fictional.xcodeproj"),
                "-scheme",
                "Fictional",
                "-configuration",
                "Release",
                "-sdk",
                "iphoneos26.2",
                "-destination",
                "generic/platform=iOS",
                "-derivedDataPath",
                str(root / "derived"),
                "-archivePath",
                str(archive),
                "CODE_SIGNING_ALLOWED=NO",
                "CODE_SIGNING_REQUIRED=NO",
                "CODE_SIGN_STYLE=Manual",
                "archive",
            ],
            root,
            timeout=600,
        )
        app = safe_path(root, archive / "Products/Applications/Fictional.app")
        info_path = safe_path(root, app / "Info.plist")
        if (
            not info_path.is_file()
            or info_path.stat().st_size > 65536
            or plistlib.loads(info_path.read_bytes()).get("CFBundleIdentifier")
            != BUNDLE
        ):
            raise Rejected("ARCHIVE_REJECTED")
        code, output = _run(
            ["/usr/bin/codesign", "--display", str(app)], cwd=root, timeout=30
        )
        if code == 0 or b"code object is not signed at all" not in output:
            raise Rejected("ARCHIVE_REJECTED")
        result["archive_created_without_key"] = True
        result["stage"] = "custody"
        custody = safe_path(root, root / "custody")
        custody.mkdir(mode=0o700)
        p12, certificate, wrong = fixtures.fictional_material()
        for index, (payload, expected) in enumerate(
            (
                (fixtures.frame(p12, certificate), "CUSTODY_VERIFIED"),
                (fixtures.frame(p12, wrong), "CERTIFICATE_MISMATCH"),
                (fixtures.frame(p12, certificate, True), "AUTH_REJECTED"),
            )
        ):
            result["native_case"] = index
            result.pop("native_detail", None)
            custody_active = True
            code, output = _run([str(binary)], cwd=custody, payload=payload, timeout=30)
            detail = native_detail(output)
            result["native_detail"] = detail
            if (
                code == 0
                and detail["cleanup"] in {"VERIFIED", "NOT_CREATED"}
                and not list(custody.iterdir())
            ):
                custody_active = False
            if (
                code != 0
                or detail["reason"] != expected
                or detail["cleanup"] != "VERIFIED"
                or custody_active
            ):
                raise Rejected("CUSTODY_REJECTED")
        result["temporary_keychain_verified"] = True
        result["stage"] = "export"
        options = safe_path(root, root / "ExportOptions.plist")
        options.write_bytes(
            plistlib.dumps(
                {
                    "method": "app-store-connect",
                    "destination": "export",
                    "signingStyle": "manual",
                    "teamID": "FICTTEAM01",
                    "signingCertificate": "fictional-leaf",
                    "provisioningProfiles": {
                        BUNDLE: "00000000-0000-0000-0000-000000000000"
                    },
                }
            )
        )
        code, output = _run(
            [
                XCODE,
                "-exportArchive",
                "-archivePath",
                str(archive),
                "-exportPath",
                str(root / "export"),
                "-exportOptionsPlist",
                str(options),
            ],
            cwd=root,
            timeout=120,
        )
        if not expected_export_rejection(code, output):
            raise Rejected("EXPORT_INCONCLUSIVE")
        result["manual_export_rejected"] = True
        result["classification"] = "CONTROL_VERIFIED_EXPORT_REJECTED"
    except KeyboardInterrupt:
        result["classification"] = "CANCELLED"
    except Exception as error:
        result["classification"] = (
            error.args[0]
            if isinstance(error, Rejected)
            and len(error.args) == 1
            and error.args[0] in REASONS
            else "REHEARSAL_REJECTED"
        )
    finally:
        if root is not None:
            try:
                cleanup(root, identity)
                result["cleanup_verified"] = not custody_active
                if custody_active:
                    result["classification"] = "CLEANUP_UNRESOLVED"
            except Exception:
                result["classification"] = "CLEANUP_UNRESOLVED"
    return result


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    result = (
        rehearse()
        if args == ["--rehearsal"]
        else {"classification": "ARGUMENTS_REJECTED"}
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["classification"] == "CONTROL_VERIFIED_EXPORT_REJECTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
