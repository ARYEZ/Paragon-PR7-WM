"""Reading and writing the two sides of a compare (no Qt). PR7-W's encodings (Notepad2's names, byte-order marks,
cp1252's undefined bytes kept), plus lines that each keep their own line ending: a side saved unchanged gives back the
very same bytes, and copying one difference across never rewrites the line endings of the rest of the file.
Binary files (a NUL byte near the start, without a UTF-16 byte-order mark) are told apart the way WinMerge does.
"""

from __future__ import annotations

import codecs
import os
from dataclasses import dataclass
from pathlib import Path

# ----------------------------------------------------------------------------- encodings
def ansi_codec() -> str:
    """Windows' 'ANSI' code page (cp1252 on Western systems); cp1252 elsewhere."""
    if os.name == "nt":
        try:
            import ctypes
            return f"cp{ctypes.windll.kernel32.GetACP()}"
        except Exception:
            pass
    return "cp1252"


def _keep_bytes_decode(err: UnicodeDecodeError):
    # A byte the code page has no character for (cp1252: 81 8D 8F 90 9D) becomes U+0080..U+00FF ...
    b = err.object[err.start]
    return chr(b), err.start + 1


def _keep_bytes_encode(err: UnicodeEncodeError):
    # ... and goes back as the same byte on save, so such files survive a round trip.
    ch = err.object[err.start]
    if ord(ch) < 256:
        return bytes([ord(ch)]), err.start + 1
    raise err


def _keep_bytes(err):
    return _keep_bytes_decode(err) if isinstance(err, UnicodeDecodeError) else _keep_bytes_encode(err)


codecs.register_error("pr7wm-keep", _keep_bytes)


@dataclass(frozen=True)
class Encoding:
    key: str          # our name, stored in settings
    label: str        # what the menu and status bar show (Notepad2's names)
    codec: str        # Python codec ('ansi' = the system code page)
    bom: bytes = b""


ENCODINGS = [
    Encoding("ansi", "ANSI", "ansi"),
    Encoding("utf-16le-bom", "Unicode", "utf-16-le", codecs.BOM_UTF16_LE),
    Encoding("utf-16be-bom", "Unicode Big Endian", "utf-16-be", codecs.BOM_UTF16_BE),
    Encoding("utf-8", "UTF-8", "utf-8"),
    Encoding("utf-8-bom", "UTF-8 with Signature", "utf-8", codecs.BOM_UTF8),
]
OTHER_ENCODINGS = [  # File > Encoding > Other (as Notepad2's Recode list, abridged to common ones)
    Encoding("cp1250", "Central European (Windows-1250)", "cp1250"),
    Encoding("cp1251", "Cyrillic (Windows-1251)", "cp1251"),
    Encoding("cp1252", "Western European (Windows-1252)", "cp1252"),
    Encoding("cp1253", "Greek (Windows-1253)", "cp1253"),
    Encoding("cp1254", "Turkish (Windows-1254)", "cp1254"),
    Encoding("cp1255", "Hebrew (Windows-1255)", "cp1255"),
    Encoding("cp1256", "Arabic (Windows-1256)", "cp1256"),
    Encoding("cp1257", "Baltic (Windows-1257)", "cp1257"),
    Encoding("cp1258", "Vietnamese (Windows-1258)", "cp1258"),
    Encoding("iso8859-1", "Western European (ISO 8859-1)", "iso8859-1"),
    Encoding("iso8859-2", "Central European (ISO 8859-2)", "iso8859-2"),
    Encoding("iso8859-15", "Latin 9 (ISO 8859-15)", "iso8859-15"),
    Encoding("koi8-r", "Cyrillic (KOI8-R)", "koi8-r"),
    Encoding("cp437", "OEM United States (437)", "cp437"),
    Encoding("cp850", "OEM Multilingual Latin 1 (850)", "cp850"),
    Encoding("shift_jis", "Japanese (Shift-JIS)", "shift_jis"),
    Encoding("gbk", "Chinese Simplified (GBK)", "gbk"),
    Encoding("big5", "Chinese Traditional (Big5)", "big5"),
    Encoding("euc-kr", "Korean (EUC-KR)", "euc-kr"),
]
BY_KEY = {e.key: e for e in ENCODINGS + OTHER_ENCODINGS}


def codec_of(enc: Encoding) -> str:
    return ansi_codec() if enc.codec == "ansi" else enc.codec


def detect_encoding(data: bytes) -> Encoding:
    if data.startswith(codecs.BOM_UTF8):
        return BY_KEY["utf-8-bom"]
    if data.startswith(codecs.BOM_UTF16_LE):
        return BY_KEY["utf-16le-bom"]
    if data.startswith(codecs.BOM_UTF16_BE):
        return BY_KEY["utf-16be-bom"]
    try:
        data.decode("utf-8")
        return BY_KEY["utf-8"]
    except UnicodeDecodeError:
        return BY_KEY["ansi"]


def decode(data: bytes, enc: Encoding) -> str:
    body = data[len(enc.bom):] if enc.bom and data.startswith(enc.bom) else data
    return body.decode(codec_of(enc), errors="pr7wm-keep" if enc.codec not in ("utf-8", "utf-16-le", "utf-16-be")
                       else "replace")


def encode(text: str, enc: Encoding) -> bytes:
    """Bytes for saving. Raises UnicodeEncodeError for characters the encoding can't hold."""
    errors = "pr7wm-keep" if enc.codec not in ("utf-8", "utf-16-le", "utf-16-be") else "strict"
    return enc.bom + text.encode(codec_of(enc), errors=errors)


def unencodable(text: str, enc: Encoding) -> list[str]:
    """The characters that would be lost saving in `enc` (Notepad2 warns before saving)."""
    if enc.codec in ("utf-8", "utf-16-le", "utf-16-be"):
        return []
    bad = []
    for ch in set(text):
        try:
            ch.encode(codec_of(enc), errors="pr7wm-keep")
        except UnicodeEncodeError:
            bad.append(ch)
    return sorted(bad)


# ----------------------------------------------------------------------------- lines
EOLS = {"crlf": ("CRLF", "\r\n"), "lf": ("LF", "\n"), "cr": ("CR", "\r")}
SNIFF = 8000                  # bytes looked at for a NUL (WinMerge looks at the start of the file)


def split(text: str) -> tuple[list[str], list[str]]:
    """Lines without their endings, and each line's ending ("" for a last line with none). An empty text has none."""
    lines, ends = [], []
    i, n = 0, len(text)
    while i < n:
        j = i
        while j < n and text[j] not in "\r\n":
            j += 1
        lines.append(text[i:j])
        if j < n and text[j] == "\r" and j + 1 < n and text[j + 1] == "\n":
            ends.append("\r\n")
            j += 2
        elif j < n:
            ends.append(text[j])
            j += 1
        else:
            ends.append("")
        i = j
    return lines, ends


def join(lines: list[str], ends: list[str]) -> str:
    return "".join(a + b for a, b in zip(lines, ends))


def main_eol(ends: list[str], default: str = "crlf") -> str:
    """The most common ending (WinMerge's status bar shows it; copied lines take it)."""
    counts = {"crlf": ends.count("\r\n"), "lf": ends.count("\n"), "cr": ends.count("\r")}
    best = max(counts, key=lambda k: counts[k])
    return best if counts[best] else default


def mixed(ends: list[str]) -> bool:
    return len({e for e in ends if e}) > 1


def is_binary(data: bytes) -> bool:
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return False
    return b"\0" in data[:SNIFF]


# ----------------------------------------------------------------------------- files
@dataclass
class Text:
    lines: list[str]
    ends: list[str]
    encoding: Encoding
    eol: str              # the main ending: crlf / lf / cr
    binary: bool = False
    size: int = 0

    @property
    def text(self) -> str:
        return join(self.lines, self.ends)

    def eol_label(self) -> str:
        return "Mixed" if mixed(self.ends) else EOLS[self.eol][0]


def default_eol() -> str:
    return "crlf" if os.name == "nt" else "lf"


def empty() -> Text:
    return Text([], [], BY_KEY["utf-8"], default_eol())


def read(path: str | Path, force: Encoding | None = None) -> Text:
    data = Path(path).read_bytes()
    if force is None and is_binary(data):
        return Text([], [], BY_KEY["utf-8"], default_eol(), True, len(data))
    enc = force or detect_encoding(data)
    lines, ends = split(decode(data, enc))
    return Text(lines, ends, enc, main_eol(ends, default_eol()), False, len(data))


def write(path: str | Path, t: Text) -> int:
    """Write atomically (a temp file, then a rename), so a failed save never leaves half a file."""
    data = encode(t.text, t.encoding)
    p = Path(path)
    if p.is_symlink():
        p = p.resolve()
    tmp = p.with_name(f".{p.name}.pr7wm-save")
    tmp.write_bytes(data)
    try:
        if p.exists():
            import shutil
            shutil.copymode(p, tmp)
        os.replace(tmp, p)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
    return len(data)


def fmt_size(n: int | None) -> str:
    """WinMerge's folder compare sizes: bytes, then KB / MB / GB."""
    if n is None:
        return ""
    if n < 1024:
        return f"{n} B"
    f = float(n)
    for unit in ("KB", "MB", "GB", "TB"):
        f /= 1024
        if f < 1024 or unit == "TB":
            return f"{f:.1f} {unit}" if f < 100 else f"{f:.0f} {unit}"
    return ""
