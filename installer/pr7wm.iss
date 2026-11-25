; Paragon PR7-WM installer (Inno Setup 6): file and folder compare, the way WinMerge compares.
;   iscc /DAppVersion=0.1.0 installer\pr7wm.iss      (after pyinstaller pr7wm.spec has made dist\PR7-WM)
;
; Per-user (no admin rights) into %LOCALAPPDATA%\Programs\PR7-WM, with a Start menu entry. "Compare in PR7-WM" in
; Explorer's menu (ticked) is registered by PR7-WM itself (--register-menu; --unregister on uninstall), HKCU only, so the
; installer, Tools > Compare in the Explorer Menu and the command line share shell.py.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
; AppId is permanent: it's how a new version finds and upgrades the installed one. Never change it.
AppId={{2E52DD0D-51E7-40B7-B5C4-F0EDC2C9E8B9}
AppName=Paragon PR7-WM
AppVersion={#AppVersion}
AppVerName=Paragon PR7-WM {#AppVersion}
AppPublisher=Paragon
VersionInfoVersion={#AppVersion}
PrivilegesRequired=lowest
DefaultDirName={autopf}\PR7-WM
DefaultGroupName=Paragon PR7-WM
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
UsePreviousTasks=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=PR7-WM-Setup-{#AppVersion}
SetupIconFile=..\pr7wm\icons\app.ico
UninstallDisplayIcon={app}\PR7-WM.exe
UninstallDisplayName=Paragon PR7-WM
WizardStyle=modern
WizardImageFile=wizard-large-1x.bmp,wizard-large-2x.bmp
WizardSmallImageFile=wizard-small-1x.bmp,wizard-small-2x.bmp
Compression=lzma2/max
SolidCompression=yes
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "explorermenu"; Description: "Add ""Compare in PR7-WM"" to Explorer's menu"; GroupDescription: "Explorer:"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\PR7-WM\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\NOTICE.md"; DestDir: "{app}"; Flags: ignoreversion

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\Paragon PR7-WM"; Filename: "{app}\PR7-WM.exe"; Comment: "File and folder compare"
Name: "{autodesktop}\Paragon PR7-WM"; Filename: "{app}\PR7-WM.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PR7-WM.exe"; Parameters: "--register-menu"; Tasks: explorermenu; Flags: runhidden waituntilterminated
Filename: "{app}\PR7-WM.exe"; Description: "{cm:LaunchProgram,Paragon PR7-WM}"; Flags: nowait postinstall skipifsilent
; Updates (Check for updates runs this installer with /SILENT /relaunch=1): start PR7-WM again when done.
Filename: "{app}\PR7-WM.exe"; Flags: nowait runasoriginaluser; Check: Relaunch

[UninstallRun]
Filename: "{app}\PR7-WM.exe"; Parameters: "--unregister"; Flags: runhidden waituntilterminated; RunOnceId: "Unregister"

[Code]
// True only when the updater asked for it (/relaunch=1): normal and CI installs behave as before.
function Relaunch: Boolean;
begin
  Result := ExpandConstant('{param:relaunch|0}') = '1';
end;
