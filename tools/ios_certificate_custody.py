"""Windows handle-bound custody. Never repairs ACLs or removes partial output.

Directory handles prevent rename; input handles deny write/delete sharing.
ACLs are checked on the handles used for I/O. This cannot protect against a
malicious process running as the same user or an administrator.
"""

import ctypes as c
import os
import sys
from ctypes import wintypes as w
from pathlib import Path

from tools import ios_certificate_preparation as preparation

INPUTS = ("distribution.cer", "distribution.csr", "distribution-private-key.pem")
OUTPUT = "distribution.p12"
LIMIT = 65536
REASONS = frozenset(
    {
        "UNSUPPORTED_HOST",
        "IDENTITY_REJECTED",
        "HANDLE_REJECTED",
        "METADATA_REJECTED",
        "ACL_REJECTED",
        "OUTPUT_EXISTS",
        "INPUT_CHANGED",
        "OUTPUT_REJECTED",
        "READ_REJECTED",
        "WRITE_REJECTED",
        "READBACK_REJECTED",
    }
)


class CustodyError(Exception):
    pass


class FileInfo(c.Structure):
    _fields_ = [
        ("attributes", w.DWORD),
        ("created", w.FILETIME),
        ("accessed", w.FILETIME),
        ("written", w.FILETIME),
        ("volume", w.DWORD),
        ("size_high", w.DWORD),
        ("size_low", w.DWORD),
        ("links", w.DWORD),
        ("index_high", w.DWORD),
        ("index_low", w.DWORD),
    ]


class ACLHeader(c.Structure):
    _fields_ = [
        ("revision", c.c_ubyte),
        ("reserved", c.c_ubyte),
        ("size", w.WORD),
        ("count", w.WORD),
        ("reserved2", w.WORD),
    ]


class SecurityDescriptor(c.Structure):
    _fields_ = [
        ("revision", c.c_ubyte),
        ("reserved", c.c_ubyte),
        ("control", w.WORD),
        ("owner", c.c_void_p),
        ("group", c.c_void_p),
        ("sacl", c.c_void_p),
        ("dacl", c.c_void_p),
    ]


class SecurityAttributes(c.Structure):
    _fields_ = [
        ("length", w.DWORD),
        ("descriptor", c.c_void_p),
        ("inherit_handle", w.BOOL),
    ]


class Native:
    def __init__(self):
        if sys.platform != "win32":
            raise CustodyError("UNSUPPORTED_HOST")
        self.kernel = c.WinDLL("kernel32", use_last_error=True)
        self.security = c.WinDLL("advapi32", use_last_error=True)
        ptr = c.c_void_p
        self.open = self.bind(
            self.kernel,
            "CreateFileW",
            w.HANDLE,
            [w.LPCWSTR, w.DWORD, w.DWORD, ptr, w.DWORD, w.DWORD, w.HANDLE],
        )
        self.close = self.bind(self.kernel, "CloseHandle", w.BOOL, [w.HANDLE])
        self.info = self.bind(
            self.kernel,
            "GetFileInformationByHandle",
            w.BOOL,
            [w.HANDLE, c.POINTER(FileInfo)],
        )
        self.final = self.bind(
            self.kernel,
            "GetFinalPathNameByHandleW",
            w.DWORD,
            [w.HANDLE, w.LPWSTR, w.DWORD, w.DWORD],
        )
        self.kind = self.bind(self.kernel, "GetFileType", w.DWORD, [w.HANDLE])
        self.read = self.bind(
            self.kernel,
            "ReadFile",
            w.BOOL,
            [w.HANDLE, ptr, w.DWORD, c.POINTER(w.DWORD), ptr],
        )
        self.write = self.bind(
            self.kernel,
            "WriteFile",
            w.BOOL,
            [w.HANDLE, ptr, w.DWORD, c.POINTER(w.DWORD), ptr],
        )
        self.seek = self.bind(
            self.kernel,
            "SetFilePointerEx",
            w.BOOL,
            [w.HANDLE, c.c_longlong, ptr, w.DWORD],
        )
        self.flush = self.bind(self.kernel, "FlushFileBuffers", w.BOOL, [w.HANDLE])
        self.free = self.bind(self.kernel, "LocalFree", ptr, [ptr])
        self.get_security = self.bind(
            self.security,
            "GetSecurityInfo",
            w.DWORD,
            [
                w.HANDLE,
                c.c_int,
                w.DWORD,
                c.POINTER(ptr),
                ptr,
                c.POINTER(ptr),
                ptr,
                c.POINTER(ptr),
            ],
        )
        self.get_control = self.bind(
            self.security,
            "GetSecurityDescriptorControl",
            w.BOOL,
            [ptr, c.POINTER(w.WORD), c.POINTER(w.DWORD)],
        )
        self.get_ace = self.bind(
            self.security, "GetAce", w.BOOL, [ptr, w.DWORD, c.POINTER(ptr)]
        )
        self.equal_sid = self.bind(self.security, "EqualSid", w.BOOL, [ptr, ptr])
        token = w.HANDLE()
        process = self.bind(self.kernel, "GetCurrentProcess", w.HANDLE, [])
        open_token = self.bind(
            self.security,
            "OpenProcessToken",
            w.BOOL,
            [w.HANDLE, w.DWORD, c.POINTER(w.HANDLE)],
        )
        token_info = self.bind(
            self.security,
            "GetTokenInformation",
            w.BOOL,
            [w.HANDLE, c.c_int, ptr, w.DWORD, c.POINTER(w.DWORD)],
        )
        sid_length = self.bind(self.security, "GetLengthSid", w.DWORD, [ptr])
        if not open_token(process(), 8, c.byref(token)):
            raise CustodyError("IDENTITY_REJECTED")
        try:
            size = w.DWORD()
            token_info(token, 1, None, 0, c.byref(size))
            if not 0 < size.value <= 65536:
                raise CustodyError("IDENTITY_REJECTED")
            buffer = c.create_string_buffer(size.value)
            if not token_info(token, 1, buffer, size, c.byref(size)):
                raise CustodyError("IDENTITY_REJECTED")
            sid = c.cast(buffer, c.POINTER(ptr)).contents.value
            length = sid_length(sid)
            if not 8 <= length <= 68:
                raise CustodyError("IDENTITY_REJECTED")
            self.sid = c.create_string_buffer(c.string_at(sid, length))
            self.sid_size = length
        finally:
            self.close(token)

    @staticmethod
    def bind(library, name, result, arguments):
        function = getattr(library, name)
        function.restype = result
        function.argtypes = arguments
        return function

    def open_handle(self, path, *, directory=False, ancestor=False, create=False):
        access = 0x20080 if directory else 0x80020000
        if create:
            access |= 0x40000000
        share = 3 if ancestor else 0 if create else 1
        # Keep absolute descriptor, ACL and SID buffers alive through CreateFile.
        # Existing inputs retain their original descriptor and open semantics.
        security = self.creation_security() if create else None
        handle = self.open(
            str(path),
            access,
            share,
            c.byref(security[0]) if security else None,
            1 if create else 3,
            0x00200000 | (0x02000000 if directory else 0x80),
            None,
        )
        if handle == c.c_void_p(-1).value:
            raise CustodyError("HANDLE_REJECTED")
        return handle

    def creation_security(self):
        ptr = c.c_void_p
        initialize_sd = self.bind(
            self.security, "InitializeSecurityDescriptor", w.BOOL, [ptr, w.DWORD]
        )
        set_owner = self.bind(
            self.security, "SetSecurityDescriptorOwner", w.BOOL, [ptr, ptr, w.BOOL]
        )
        initialize_acl = self.bind(
            self.security, "InitializeAcl", w.BOOL, [ptr, w.DWORD, w.DWORD]
        )
        add_ace = self.bind(
            self.security,
            "AddAccessAllowedAceEx",
            w.BOOL,
            [ptr, w.DWORD, w.DWORD, w.DWORD, ptr],
        )
        set_dacl = self.bind(
            self.security,
            "SetSecurityDescriptorDacl",
            w.BOOL,
            [ptr, w.BOOL, ptr, w.BOOL],
        )
        set_control = self.bind(
            self.security, "SetSecurityDescriptorControl", w.BOOL, [ptr, w.WORD, w.WORD]
        )
        descriptor = SecurityDescriptor()
        acl = c.create_string_buffer(c.sizeof(ACLHeader) + 8 + self.sid_size)
        if (
            not initialize_sd(c.byref(descriptor), 1)
            or not set_owner(c.byref(descriptor), self.sid, False)
            or not initialize_acl(acl, len(acl), 2)
            or not add_ace(acl, 2, 0, 0x1F01FF, self.sid)
            or not set_dacl(c.byref(descriptor), True, acl, False)
            or not set_control(c.byref(descriptor), 0x1000, 0x1000)
        ):
            raise CustodyError("ACL_REJECTED")
        attributes = SecurityAttributes(
            c.sizeof(SecurityAttributes), c.addressof(descriptor), False
        )
        return attributes, descriptor, acl

    def metadata(self, handle, path, *, directory=False, allow_empty=False):
        info = FileInfo()
        final = c.create_unicode_buffer(32768)
        length = self.final(handle, final, len(final), 0)
        if not length or length >= len(final) or not self.info(handle, c.byref(info)):
            raise CustodyError("METADATA_REJECTED")
        actual = final.value
        if actual.startswith("\\\\?\\"):
            actual = actual[4:]
        if (
            os.path.normcase(actual.rstrip("\\"))
            != os.path.normcase(str(path).rstrip("\\"))
            or self.kind(handle) != 1
            or info.attributes & 0x400
            or bool(info.attributes & 0x10) != directory
        ):
            raise CustodyError("METADATA_REJECTED")
        size = (info.size_high << 32) | info.size_low
        if not directory and (
            info.links != 1 or not (0 if allow_empty else 1) <= size <= LIMIT
        ):
            raise CustodyError("METADATA_REJECTED")
        return (
            info.volume,
            info.index_high,
            info.index_low,
            size,
            info.written.dwHighDateTime,
            info.written.dwLowDateTime,
        )

    def acl(self, handle, *, directory=False):
        owner, dacl, descriptor = c.c_void_p(), c.c_void_p(), c.c_void_p()
        if self.get_security(
            handle, 1, 5, c.byref(owner), None, c.byref(dacl), None, c.byref(descriptor)
        ):
            raise CustodyError("ACL_REJECTED")
        try:
            if not owner or not dacl or not self.equal_sid(owner, self.sid):
                raise CustodyError("ACL_REJECTED")
            header = c.cast(dacl, c.POINTER(ACLHeader)).contents
            control, revision = w.WORD(), w.DWORD()
            if (
                header.count != 1
                or not self.get_control(descriptor, c.byref(control), c.byref(revision))
                or (directory and not control.value & 0x1000)
            ):
                raise CustodyError("ACL_REJECTED")
            ace = c.c_void_p()
            if not self.get_ace(dacl, 0, c.byref(ace)):
                raise CustodyError("ACL_REJECTED")
            prefix = c.string_at(ace, 8)
            if (
                prefix[0] != 0
                or prefix[1] & 8
                or (directory and prefix[1] != 3)
                or (not directory and prefix[1] not in (0, 16))
                or int.from_bytes(prefix[4:8], "little") != 0x1F01FF
                or not self.equal_sid(ace.value + 8, self.sid)
            ):
                raise CustodyError("ACL_REJECTED")
        finally:
            self.free(descriptor)


class Custody:
    """Keep metadata-checked handles open across confirmation and one output."""

    def __init__(self, directory: Path):
        self.directory = directory
        self.native = Native()
        self.handles = []
        self.inputs = {}
        self.output_attempted = False

    def __enter__(self):
        try:
            try:
                preparation.safe_directory(self.directory, fresh=False)
            except preparation.Rejected:
                raise CustodyError("METADATA_REJECTED") from None
            for path in (*reversed(self.directory.parents), self.directory):
                handle = self.native.open_handle(
                    path, directory=True, ancestor=path != self.directory
                )
                self.handles.append(handle)
                self.native.metadata(handle, path, directory=True)
                if path == self.directory:
                    self.directory_handle = handle
                    self.native.acl(handle, directory=True)
            for name in INPUTS:
                path = self.directory / name
                handle = self.native.open_handle(path)
                self.handles.append(handle)
                metadata = self.native.metadata(handle, path)
                self.native.acl(handle)
                self.inputs[name] = (handle, metadata)
            if (self.directory / OUTPUT).exists():
                raise CustodyError("OUTPUT_EXISTS")
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        for handle in reversed(self.handles):
            self.native.close(handle)
        self.handles.clear()

    def read_input(self, name):
        handle, expected = self.inputs[name]
        if self.native.metadata(handle, self.directory / name) != expected:
            raise CustodyError("INPUT_CHANGED")
        self.native.acl(handle)
        return self._read(handle, expected[3])

    def _read(self, handle, size):
        buffer, count = c.create_string_buffer(size), w.DWORD()
        if (
            not self.native.seek(handle, 0, None, 0)
            or not self.native.read(handle, buffer, size, c.byref(count), None)
            or count.value != size
        ):
            raise CustodyError("READ_REJECTED")
        return buffer.raw[:size]

    def write_output(self, data):
        if (
            self.output_attempted
            or type(data) is not bytes
            or not 0 < len(data) <= LIMIT
        ):
            raise CustodyError("OUTPUT_REJECTED")
        self.native.acl(self.directory_handle, directory=True)
        self.output_attempted = True
        path = self.directory / OUTPUT
        handle = self.native.open_handle(path, create=True)
        self.handles.append(handle)
        self.native.metadata(handle, path, allow_empty=True)
        self.native.acl(handle)
        count = w.DWORD()
        buffer = c.create_string_buffer(data)
        if (
            not self.native.write(handle, buffer, len(data), c.byref(count), None)
            or count.value != len(data)
            or not self.native.flush(handle)
        ):
            raise CustodyError("WRITE_REJECTED")
        self.native.metadata(handle, path)
        self.native.acl(handle)
        if self._read(handle, len(data)) != data:
            raise CustodyError("READBACK_REJECTED")
