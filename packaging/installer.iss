; Inno Setup script for LocalProof (Windows).
; Build after PyInstaller:  iscc /DAppVersion=0.1.0 packaging\installer.iss
;
; - Installs per user by default (%LOCALAPPDATA%\Programs\LocalProof); an
;   all-users install can be chosen in the privileges dialog.
; - Adds a Windows Firewall rule that blocks ALL outbound traffic for
;   LocalProof.exe. Elevated installs add it directly; per-user installs ask
;   for one UAC approval (task "firewall", on by default). If that is declined,
;   the app's Trust Panel reports "firewall rule missing" with instructions.
; - Uninstall removes the rule and leaves the user data folder in place.

#ifndef AppVersion
  #define AppVersion "0.0.0-dev"
#endif
#define AppName "LocalProof"
#define AppExe "LocalProof.exe"
#define RuleName "LocalProof - block outbound"

[Setup]
AppId={{CDED289F-6354-4900-8C01-CDC890B619D9}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=LocalProof contributors
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
OutputDir=..\dist\installer
OutputBaseFilename=LocalProof-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#AppExe}
SetupLogging=yes

[Tasks]
Name: "firewall"; Description: "Block all outbound network traffic for LocalProof in Windows Firewall (recommended; asks for administrator approval)"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\LocalProof\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Messages]
FinishedLabel=Setup has finished installing [name].%n%nYour files are stored in %LOCALAPPDATA%\LocalProof and never leave this computer. Open the Trust Panel in the app to check the firewall rule and verify this yourself.
UninstalledAll=%1 was removed from your computer.%n%nYour data folder (%LOCALAPPDATA%\LocalProof) was left in place. Delete it yourself, or use Trust Panel > Delete all my data before uninstalling.

[Code]
function NetshParams(const Action: String): String;
begin
  if Action = 'add' then
    Result := 'advfirewall firewall add rule name="{#RuleName}" dir=out action=block ' +
              'program="' + ExpandConstant('{app}\{#AppExe}') + '" enable=yes profile=any'
  else
    Result := 'advfirewall firewall delete rule name="{#RuleName}"';
end;

{ Runs netsh directly when this installer is elevated, otherwise via one UAC prompt. }
function RunNetsh(const Params: String): Integer;
var
  Code: Integer;
  Started: Boolean;
begin
  Code := -1;
  if IsAdmin then
    Started := Exec(ExpandConstant('{sys}\netsh.exe'), Params, '', SW_HIDE, ewWaitUntilTerminated, Code)
  else
    Started := ShellExec('runas', ExpandConstant('{sys}\netsh.exe'), Params, '', SW_HIDE, ewWaitUntilTerminated, Code);
  if not Started then
    Code := -1;
  Log('netsh ' + Params + ' -> exit code ' + IntToStr(Code));
  Result := Code;
end;

{ Querying needs no elevation, so per-user uninstalls only prompt when there is a rule to remove. }
function RuleExists: Boolean;
var
  Code: Integer;
begin
  Result := Exec(ExpandConstant('{sys}\netsh.exe'), 'advfirewall firewall show rule name="{#RuleName}"',
                 '', SW_HIDE, ewWaitUntilTerminated, Code) and (Code = 0);
end;

procedure AddFirewallRule;
begin
  { Elevated: drop any stale rule first so the program path is always current.
    Per-user: skip the delete to keep it to a single UAC prompt. }
  if IsAdmin then
    RunNetsh(NetshParams('delete'));
  if RunNetsh(NetshParams('add')) <> 0 then
    Log('Firewall rule NOT added; the Trust Panel will report it missing.');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and (IsAdmin or WizardIsTaskSelected('firewall')) then
    AddFirewallRule;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usUninstall) and RuleExists then
    RunNetsh(NetshParams('delete'));
end;
