Unicode true
Name "Xinyu Tauri Spike"
OutFile "..\dist\installer\Xinyu-Tauri-Spike-Setup-9.3.0.exe"
InstallDir "$LOCALAPPDATA\Programs\XinyuTauriSpike"
RequestExecutionLevel user
SetCompressor /SOLID lzma

Page directory
Page instfiles
UninstPage uninstConfirm
UninstPage instfiles

Section "Install"
  SetOutPath "$INSTDIR"
  File "..\dist\tauri-spike\xinyu-tauri-spike.exe"

  SetOutPath "$INSTDIR\sidecar\embedded"
  File /r "..\dist\XinyuSidecarEmbedded\*.*"

  CreateDirectory "$SMPROGRAMS\Xinyu Tauri Spike"
  CreateShortCut "$SMPROGRAMS\Xinyu Tauri Spike\Xinyu Tauri Spike.lnk" "$INSTDIR\xinyu-tauri-spike.exe"
  CreateShortCut "$DESKTOP\Xinyu Tauri Spike.lnk" "$INSTDIR\xinyu-tauri-spike.exe"

  WriteUninstaller "$INSTDIR\uninstall.exe"
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\Xinyu Tauri Spike.lnk"
  Delete "$SMPROGRAMS\Xinyu Tauri Spike\Xinyu Tauri Spike.lnk"
  RMDir "$SMPROGRAMS\Xinyu Tauri Spike"
  RMDir /r "$INSTDIR\sidecar"
  Delete "$INSTDIR\xinyu-tauri-spike.exe"
  Delete "$INSTDIR\uninstall.exe"
  RMDir "$INSTDIR"
SectionEnd
