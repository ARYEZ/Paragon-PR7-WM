# Paragon PR7-WM: notes for Claude

**Paragon PR7-WM** is the owner's personal file and folder compare: Python (**PySide6**) that **works the way WinMerge
works**, in the Paragon family look (PR7-Z ... PR7-FS, PR7-AR `ARYEZ/Paragon-PR7-AR`). Windows 10/11 x64 is the target;
it runs on Linux for tests. The owner writes Python; explain the why.

## How it's built

- `pr7wm/textio.py` (no Qt): PR7-W's encodings (Notepad2's names, BOMs, cp1252's undefined bytes kept via the
  `pr7wm-keep` error handler) plus `split` / `join`: lines without endings and **each line's own ending**, so a side
  saved unchanged is byte-exact and a merge touches only the copied lines. `is_binary` = a NUL in the first 8000 bytes
  without a UTF-16 BOM. `write` is atomic.
- `pr7wm/diff.py` (no Qt): `key` per line from `Options` (whitespace compare / changes (GNU -b) / all, case, eol =
  ignore carriage return differences, on by default as in WinMerge), difflib (autojunk only for very long files) ->
  `Result(rows, blocks)`: rows with fillers (`Row.l` / `r` None), blocks = differences; "ignore blank lines" marks a
  blank-only block `ignored` (shown, not counted, Next skips it). `inline` = word (default) / char spans.
- `pr7wm/compare.py` (no Qt): `Side` (path, `textio.Text`, description = /dl /dr, read_only, modified, stamp for
  changes made elsewhere) and `FileCompare`: `copy(block, to)` / `copy_all` (copied lines take the destination's main
  ending; the end of file keeps its "no final newline" state; an empty unnamed side takes the source's form),
  `set_lines` (an edit: unchanged lines keep their endings), whole-snapshot undo / redo, `save`, `reload`, `patch`.
- `pr7wm/folders.py` (no Qt): WinMerge's mask `Filter` (`*.*` = every file, `!mask`, `!dir\`), `compare` (tree order,
  folders first; one-sided folders are one item; methods full / quick / date / date_size / size; 2 s time tolerance;
  text files counted by the same diff options), `result_text` (WinMerge's wording), `copy`, `delete` (`trash.send`).
  **PR7WM_TRASH** points the Recycle Bin at a folder: tests always set it.
- `pr7wm/panes.py`: `TextPane` is a QPlainTextEdit with one block per row; fillers carry user state FILLER, so
  `real_lines` reads an edited side back (a filler that got text is a line). Tints painted under the text in
  `paintEvent`, word marks by a QSyntaxHighlighter, line numbers in a gutter. Undo is the compare's own (the pane
  passes Ctrl+Z / Ctrl+Y on). `FilePage`: both panes scroll together, `rebuild` keeps the cursor on its line, edits
  are compared again after EDIT_DELAY_MS (inline when `sync`), `Location`, the Diff pane (`detail`), `SideHeader`.
- `pr7wm/folder_page.py`: `FolderModel` (plain list model, never QStandardItemModel: PR7-Z's crash), `Band` delegate
  (one family gradient across the selected row), compare on a thread (inline when `sync`), show choices in the
  `show` setting.
- `pr7wm/main_window.py`: tabs of pages, WinMerge's menus and keys (`_act(..., key=)` into `acts`), `_sync` sets keys
  and status; every question through `_ask(kind)` (tests: `answers`); `collect` / `flush_collected` merge the Explorer
  menu's launches (two items -> compare; one -> `pending_left`, compared with the next one); `run_args` for the
  command line. `dialogs.py`: OpenDialog (Select Files or Folders), OptionsDialog (radios in a QButtonGroup).
- `pr7wm/shell.py`: "Compare in PR7-WM" = HKCU `Software\Classes\{*,Directory}\shell\PR7WM.Compare`, MultiSelectModel
  Player, `--collect "%1"`; `base` lets Windows CI use a throwaway key.
- `pr7wm/app.py`: WinMerge's command line (`parse`: /r /e /wl /wr /dl /dr /f; a path starting with / isn't a switch
  unless it's one of them); one window per user (QLocalSocket, PR7-R's Windows fix) plus a QLockFile so Explorer's
  simultaneous launches hand over to the first; command-line modes never let an error escape (PR7-IS's lesson);
  `--selftest OUT.json` (CI runs it on the installed exe), `--register-menu`, `--unregister`.
- Open in PR7-HX: binary files (File menu on a binary file compare, the folder menu on binary results) go to PR7-HX
  via `family.launch` when `hex_editor()` finds it (tests: `answers["find"]`, `answers["launch_hx"]`).
- Installer `installer/pr7wm.iss` (per user, AppId {2E52DD0D-51E7-40B7-B5C4-F0EDC2C9E8B9} permanent; tasks explorermenu
  (ticked, runs `--register-menu`; `--unregister` on uninstall), desktopicon); CI installs it,
  `tools/verify_install.py installed|uninstalled`. Spec: file details, no UPX, PyInstaller's bootloader built in CI,
  Defender scan.
- Updates: `pr7wm/updates.py` / `update_ui.py` (the family's files, keep them in step; with PR7-U installed,
  update_ui offers it); `family.py`: the family's AppIds (PR7-WM included).
- `pr7wm/finish.py` (no Qt): the family's finish (OBSIDIAN / AURORA), one choice for every app:
  HKCU\Software\Paragon\Family "Finish" (a file elsewhere; PARAGON_FAMILY_FILE in tests, conftest). `finish.start`
  at start-up, `set_finish` saves it, app.py's 2 s timer `finish.follow`s another app's switch. The same file in every
  family app: keep them in step.

## The look (family rules)

- Theme is PR7-AR's (OBSIDIAN + AURORA, tabs and sliders). Colours: the family's only; the diff colours are
  `panes.colours()` (pink changed, orange one-sided, onyx / pearl fillers; WinMerge's yellow / grey are these here).
  Inter for the UI; the texts are monospaced (the one exception); labels UPPER CASE; file names keep their case.
- The PR7-WM mark: PR7 `Logo.cpp` geometry plus W and M (`widgets.W_OUTER` / `M_OUTER`); icon "7WM" by
  `tools/make_icon.py`, wizard art by `tools/make_installer_art.py`. Mock-up: `tools/mockup.py`. Check visuals with
  `QT_SCALE_FACTOR=2 python tools/screenshots.py OUT` (the real window on generated files).

## Rules

- Behaviour questions: do what WinMerge does (menus, keys, options, folder results, command line).
- Tests: `python -m pytest` (offscreen) on real files; merges and saves are checked byte for byte. Never the real
  settings, data folder or Recycle Bin (conftest), or, outside CI, the registry.
- Releases: bump `__version__` in `pr7wm/__init__.py` and add a `## x.y.z` section to CHANGELOG.md, then push: CI
  publishes that version by itself once every check has passed. Run workflow / `v*` tags still work.
