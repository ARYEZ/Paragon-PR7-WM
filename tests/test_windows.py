"""Windows only (CI): the real registry, under a throwaway key, never the real Explorer menu."""
import sys
import uuid

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


def test_explorer_menu_keys():
    import winreg

    from pr7wm import shell
    base = rf"Software\Paragon\PR7-WM-test-{uuid.uuid4().hex[:8]}\Classes"
    try:
        shell.register('"C:\\Apps\\PR7-WM.exe"', base)
        assert shell.menu_registered(base)
        for target in shell.TARGETS:
            assert shell.command_of(target, base) == '"C:\\Apps\\PR7-WM.exe" --collect "%1"'
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"{base}\*\shell\{shell.VERB}") as k:
            assert winreg.QueryValueEx(k, None)[0] == "Compare in PR7-WM"
            assert winreg.QueryValueEx(k, "MultiSelectModel")[0] == "Player"
        shell.unregister(base)
        assert not shell.menu_registered(base) and shell.command_of("Directory", base) is None
    finally:
        shell.unregister(base)
        root = base.rsplit("\\", 1)[0]
        for sub in (base + r"\Directory\shell", base + r"\Directory", base + r"\*\shell", base + r"\*", base, root):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
            except OSError:
                pass


def test_a_real_file_compare_saves_crlf(tmp_path):
    from pr7wm import compare
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_bytes(b"x\r\ny\r\n")
    b.write_bytes(b"x\r\nz\r\n")
    fc = compare.FileCompare.open(str(a), str(b))
    fc.copy(fc.blocks[0], "right")
    fc.save("right")
    assert b.read_bytes() == b"x\r\ny\r\n"
