"""Windows directory enumeration with a filesystem change time per entry."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path
import struct


# FILE_ID_BOTH_DIR_INFO uses fixed offsets for the fields preceding FileName.
_FIRST = 11  # FileIdBothDirectoryRestartInfo
_NEXT = 10   # FileIdBothDirectoryInfo
_NAME_OFFSET = 104


def directory_changes(path: Path) -> dict[str, str]:
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    open_directory = api.CreateFileW
    open_directory.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                               wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    open_directory.restype = wintypes.HANDLE
    query = api.GetFileInformationByHandleEx
    query.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
    query.restype = wintypes.BOOL
    close = api.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL

    # FILE_LIST_DIRECTORY, sharing for readers/writers/deleters, OPEN_EXISTING, BACKUP_SEMANTICS.
    handle = open_directory(str(path), 1, 7, None, 3, 0x02000000, None)
    if handle == ctypes.c_void_p(-1).value:
        return {}
    entries: dict[str, str] = {}
    buffer = ctypes.create_string_buffer(64 * 1024)
    operation = _FIRST
    try:
        while query(handle, operation, buffer, len(buffer)):
            offset = 0
            while offset + _NAME_OFFSET <= len(buffer):
                skip = struct.unpack_from("<I", buffer, offset)[0]
                length = struct.unpack_from("<I", buffer, offset + 60)[0]
                start = offset + _NAME_OFFSET
                if length <= 0 or length % 2 or start + length > len(buffer):
                    return {}
                name = buffer[start:start + length].decode("utf-16-le", errors="surrogatepass")
                stamp = struct.unpack_from("<Q", buffer, offset + 32)[0]
                identifier = struct.unpack_from("<Q", buffer, offset + 96)[0]
                if stamp and identifier:
                    entries[name] = f"nt:{identifier}:{stamp}"
                if not skip:
                    break
                if skip < _NAME_OFFSET + length:
                    return {}
                offset += skip
            operation = _NEXT
        if ctypes.get_last_error() != 18:  # ERROR_NO_MORE_FILES
            return {}
    finally:
        close(handle)
    return entries
