; Ghost Hunter Pro - NSIS Installer
; Build with: makensis /DAPP_VERSION=2.3 installer.nsi

!define APP_NAME      "Ghost Hunter Pro"
!define APP_EXE       "GhostHunterPro.exe"
!define PUBLISHER     "GhostHunterPro"
!define REGKEY        "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"
!define INSTDIR_REG   "Software\${PUBLISHER}\${APP_NAME}"

!ifndef APP_VERSION
  !define APP_VERSION "2.3"
!endif

OutFile "GhostHunterPro-Setup-${APP_VERSION}.exe"
InstallDir "$PROGRAMFILES64\${APP_NAME}"
InstallDirRegKey HKLM "${INSTDIR_REG}" "InstallDir"
RequestExecutionLevel admin

!include "MUI2.nsh"

!define MUI_ABORTWARNING
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "Launch ${APP_NAME}"
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Name "${APP_NAME}"
BrandingText "${APP_NAME} ${APP_VERSION}"

Section "Install" SecInstall
  SectionIn RO
  ; Stop a running copy so updates can replace the EXE cleanly
  ExecWait 'taskkill /F /IM "${APP_EXE}"' $0
  Sleep 1500

  SetOutPath "$INSTDIR"

  File '/oname=${APP_EXE}' "dist\GhostHunterPro.exe"

  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
  CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"

  WriteRegStr HKLM "${INSTDIR_REG}" "InstallDir" "$INSTDIR"
  WriteRegStr HKLM "${REGKEY}" "DisplayName" "${APP_NAME}"
  WriteRegStr HKLM "${REGKEY}" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKLM "${REGKEY}" "Publisher" "${PUBLISHER}"
  WriteRegStr HKLM "${REGKEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "${REGKEY}" "UninstallString" "$INSTDIR\Uninstall.exe"
  WriteRegStr HKLM "${REGKEY}" "DisplayIcon" "$INSTDIR\${APP_EXE}"
  WriteRegDWORD HKLM "${REGKEY}" "NoModify" 1
  WriteRegDWORD HKLM "${REGKEY}" "NoRepair" 1

  WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Uninstall"
  ExecWait 'taskkill /F /IM "${APP_EXE}"' $0
  Delete "$INSTDIR\${APP_EXE}"
  Delete "$INSTDIR\Uninstall.exe"
  Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
  RMDir "$SMPROGRAMS\${APP_NAME}"
  Delete "$DESKTOP\${APP_NAME}.lnk"
  RMDir "$INSTDIR"
  DeleteRegKey HKLM "${REGKEY}"
  DeleteRegKey HKLM "${INSTDIR_REG}"
SectionEnd
