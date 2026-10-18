; 心语 Windows 安装脚本（Inno Setup 6）
; 构建：python build.py 后执行 ISCC.exe installer\xinyu.iss /DMyAppVersion=9.3.0
; 安装到用户目录，避免写 Program Files 的权限问题；用户数据在 %APPDATA%\Xinyu。

#ifndef MyAppVersion
#define MyAppVersion "9.3.0"
#endif

#define MyAppName "心语"
#define MyAppPublisher "hedongwei"
#define MyAppExeName "Xinyu.exe"

[Setup]
AppId={{7F2E6B7A-9C1D-4D3E-8B2A-5E6C7D8A9B10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\Xinyu
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist\installer
OutputBaseFilename=Xinyu-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加快捷方式:"; Flags: unchecked

[Files]
Source: "..\dist\Xinyu\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\CHANGELOG.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动{#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
