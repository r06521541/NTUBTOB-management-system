"""Windows-only, local CSR preparation; no Apple or signing operation.

Private values stay in process memory. Python cannot guarantee memory zeroization.
Only a separately approved Owner run may create genuine material.
"""

from __future__ import annotations

import argparse
import base64
import ctypes
import getpass
import os
import re
import stat
import subprocess
import sys
import uuid
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = "NTUBTOB-AppleDistribution-CSR"
KEY_FILE = "distribution-private-key.pem"
CSR_FILE = "distribution.csr"
VERSION = "50.0.0"


class Rejected(Exception):
    """Details must never be rendered to the console."""


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise Rejected()


def dependencies():
    import cryptography
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    if cryptography.__version__ != VERSION:
        raise Rejected()
    return x509, hashes, serialization, rsa


def local_app_data() -> Path:
    # SHGetKnownFolderPath ignores caller-provided LOCALAPPDATA variables.
    folder_id = ctypes.create_string_buffer(
        uuid.UUID("f1b32785-6fba-4fcf-9d55-7b8e7f157091").bytes_le
    )
    pointer = ctypes.c_void_p()
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    shell.SHGetKnownFolderPath.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    shell.SHGetKnownFolderPath.restype = ctypes.c_long
    result = shell.SHGetKnownFolderPath(folder_id, 0, None, ctypes.byref(pointer))
    try:
        if result != 0 or not pointer.value:
            raise Rejected()
        return Path(ctypes.wstring_at(pointer))
    finally:
        ctypes.windll.ole32.CoTaskMemFree(ctypes.c_void_p(pointer.value))


def fixed_drive(path: Path) -> bool:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetDriveTypeW.argtypes = [ctypes.c_wchar_p]
    kernel.GetDriveTypeW.restype = ctypes.c_uint
    return kernel.GetDriveTypeW(path.anchor) == 3


def safe_directory(path: Path, *, fresh: bool) -> None:
    if (
        not path.is_absolute()
        or str(path).startswith(("\\\\", "//"))
        or not fixed_drive(path)
        or path.is_relative_to(ROOT)
        or any(
            part.lower() in {"onedrive", "dropbox", "google drive", "iclouddrive"}
            or part.lower().startswith("onedrive -")
            for part in path.parts
        )
    ):
        raise Rejected()
    for item in (path, *path.parents):
        try:
            info = item.lstat()
        except FileNotFoundError:
            if item != path or not fresh:
                raise Rejected() from None
            continue
        if (
            not stat.S_ISDIR(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & 0x400
        ):
            raise Rejected()
        if fresh and item == path:
            raise Rejected()


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=15,
        encoding="ascii",
        errors="strict",
    )
    if result.returncode:
        raise Rejected()
    return result.stdout.strip()


def preflight(expected_commit: str) -> Path:
    if sys.platform != "win32" or not re.fullmatch("[0-9a-f]{40}", expected_commit):
        raise Rejected()
    dependencies()
    acl_environment(powershell_home())
    if git("rev-parse", "HEAD") != expected_commit or git(
        "status", "--porcelain", "--untracked-files=all"
    ):
        raise Rejected()
    target = local_app_data() / DIRECTORY
    safe_directory(target, fresh=True)
    return target


# Fixed code only: the path travels as data, never PowerShell source. Modules
# resolve from the Windows PowerShell installation, not inherited PS7 paths.
ACL_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$PSModuleAutoLoadingPreference = 'None'
try {
  Import-Module ($PSHOME + '\Modules\Microsoft.PowerShell.Utility\Microsoft.PowerShell.Utility.psd1') -ErrorAction Stop
  Import-Module ($PSHOME + '\Modules\Microsoft.PowerShell.Security\Microsoft.PowerShell.Security.psd1') -ErrorAction Stop
  $p = $env:NTUBTOB_CSR_ACL_TARGET
  $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User
  if ($env:NTUBTOB_CSR_ACL_SET -eq '1') {
    $acl = New-Object Security.AccessControl.DirectorySecurity
    $acl.SetOwner($sid)
    $acl.SetAccessRuleProtection($true, $false)
    $rule = New-Object Security.AccessControl.FileSystemAccessRule($sid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
    $acl.AddAccessRule($rule)
    Set-Acl -LiteralPath $p -AclObject $acl
  }
  $acl = Get-Acl -LiteralPath $p
  $rules = @($acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier]))
  if (!$acl.AreAccessRulesProtected -or $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -ne $sid.Value -or $rules.Count -ne 1) { exit 2 }
  $r = $rules[0]
  if ($r.IdentityReference.Value -ne $sid.Value -or $r.AccessControlType -ne 'Allow' -or $r.IsInherited -or $r.FileSystemRights -ne 'FullControl' -or $r.InheritanceFlags -ne 'ContainerInherit,ObjectInherit' -or $r.PropagationFlags -ne 'None') { exit 2 }
  exit 0
} catch { exit 2 }
"""


def powershell_home() -> Path:
    buffer = ctypes.create_unicode_buffer(32768)
    if not ctypes.windll.kernel32.GetSystemDirectoryW(buffer, len(buffer)):
        raise Rejected()
    home = Path(buffer.value) / "WindowsPowerShell" / "v1.0"
    if not (home / "powershell.exe").is_file() or not (home / "Modules").is_dir():
        raise Rejected()
    for name in ("Microsoft.PowerShell.Utility", "Microsoft.PowerShell.Security"):
        if not (home / "Modules" / name / (name + ".psd1")).is_file():
            raise Rejected()
    return home


def acl_environment(home: Path) -> dict[str, str]:
    # .NET/Windows PowerShell require a usable per-user temporary/cache root.
    # Derive only these OS paths from KnownFolder; never inherit caller values.
    local = local_app_data()
    temporary = local / "Temp"
    safe_directory(temporary, fresh=False)
    system_root = str(home.parents[2])
    return {
        "SYSTEMROOT": system_root,
        "WINDIR": system_root,
        "PSMODULEPATH": str(home / "Modules"),
        "LOCALAPPDATA": str(local),
        "TEMP": str(temporary),
        "TMP": str(temporary),
    }


def secure_acl(path: Path, *, establish: bool) -> None:
    home = powershell_home()
    environment = acl_environment(home)
    environment["NTUBTOB_CSR_ACL_TARGET"] = str(path)
    environment["NTUBTOB_CSR_ACL_SET"] = "1" if establish else "0"
    result = subprocess.run(
        [
            str(home / "powershell.exe"),
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-EncodedCommand",
            base64.b64encode(ACL_SCRIPT.encode("utf-16-le")).decode("ascii"),
        ],
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=30,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode:
        raise Rejected()


def hidden(prompt: str) -> str:
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise Rejected()
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        value = getpass.getpass(prompt)
    if not value or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise Rejected()
    print("input_accepted length=" + str(len(value)))
    return value


def private_input() -> tuple[str, str, bytes]:
    name = hidden("Common name (hidden): ")
    email = hidden("Email (hidden): ")
    password = hidden("Encryption passphrase (hidden): ")
    repeat = hidden("Repeat passphrase (hidden): ")
    if (
        len(name.encode("utf-8")) > 64
        or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+", email)
        or len(email) > 254
        or password != repeat
        or not 16 <= len(password.encode("utf-8")) <= 1024
    ):
        raise Rejected()
    return name, email, password.encode("utf-8")


def material(name: str, email: str, password: bytes) -> tuple[bytes, bytes]:
    x509, hashes, serialization, rsa = dependencies()
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(
            x509.Name(
                [
                    x509.NameAttribute(x509.NameOID.COMMON_NAME, name),
                    x509.NameAttribute(x509.NameOID.EMAIL_ADDRESS, email),
                ]
            )
        )
        .sign(key, hashes.SHA256())
    )
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(password),
    ), csr.public_bytes(serialization.Encoding.PEM)


def execute(expected_commit: str) -> str:
    started = False
    private = None
    try:
        target = preflight(expected_commit)
        print(
            "PREFLIGHT_OK action=create_csr count=1 target=local_app_data/" + DIRECTORY
        )
        print(
            "files=" + KEY_FILE + "," + CSR_FILE + " rollback=manual_protected_recovery"
        )
        print("commit=" + expected_commit)
        private = private_input()
        if (
            hidden(
                "Type CREATE CSR followed by a space and the exact commit (hidden): "
            )
            != "CREATE CSR " + expected_commit
        ):
            raise Rejected()
        if preflight(expected_commit) != target:
            raise Rejected()
        # Once mkdir is attempted, interruption is conservatively uncertain.
        started = True
        target.mkdir()
        secure_acl(target, establish=True)
        safe_directory(target, fresh=False)
        secure_acl(target, establish=False)
        key, csr = material(*private)
        for filename, data in ((KEY_FILE, key), (CSR_FILE, csr)):
            safe_directory(target, fresh=False)
            secure_acl(target, establish=False)
            with (target / filename).open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        return "confirmed_success"
    except (Exception, KeyboardInterrupt):
        return "uncertain" if started else "pre_execution_rejected"
    finally:
        private = None


def main(argv=None) -> int:
    # No parser error includes caller input.
    parser = SafeParser(add_help=False, exit_on_error=False)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--execute", action="store_true")
    try:
        args, unknown = parser.parse_known_args(argv)
        if unknown:
            raise Rejected()
        if args.execute:
            result = execute(args.expected_commit)
        else:
            preflight(args.expected_commit)
            result = "preflight_passed"
    except (Exception, KeyboardInterrupt, SystemExit):
        result = "pre_execution_rejected"
    print("IOS_CSR_RESULT target=local_apple_distribution classification=" + result)
    return 0 if result in {"confirmed_success", "preflight_passed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
