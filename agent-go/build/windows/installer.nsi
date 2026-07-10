; ═══════════════════════════════════════════════════════════════════
; Kaydan Edge Gateway — Installateur NSIS Windows
; ═══════════════════════════════════════════════════════════════════
;
; Génère KaydanEdgeGatewaySetup.exe qui :
;   1. Copie le binaire kshield-agent.exe dans C:\Program Files\KaydanEdge\
;   2. Copie NSSM pour gérer le service Windows
;   3. Crée le service Windows "KaydanEdgeGateway" (auto-start)
;   4. Enregistre l'uninstaller
;
; Prérequis pour construire :
;   - NSIS (Nullsoft Scriptable Install System) — nsis.sourceforge.io
;   - Le binaire kshield-agent-windows-amd64.exe présent dans ce dossier
;
; Build : makensis installer.nsi
; ═══════════════════════════════════════════════════════════════════

!define APP_NAME     "Kaydan Edge Gateway"
!define APP_VERSION  "1.0.0"
!define PUBLISHER    "Kaydan Groupe"
!define SERVICE_NAME "KaydanEdgeGateway"
!define BINARY_NAME  "kshield-agent.exe"
!define WEB_URL      "https://kaydanshield.com"

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"

; ─── Metadata ─────────────────────────────────────────────────────
Name         "${APP_NAME}"
OutFile      "KaydanEdgeGatewaySetup.exe"
InstallDir   "$PROGRAMFILES64\KaydanEdge"
RequestExecutionLevel admin
BrandingText "${APP_NAME} v${APP_VERSION} - ${PUBLISHER}"

VIProductVersion "${APP_VERSION}.0"
VIAddVersionKey "ProductName"     "${APP_NAME}"
VIAddVersionKey "CompanyName"     "${PUBLISHER}"
VIAddVersionKey "FileDescription" "${APP_NAME} Installer"
VIAddVersionKey "FileVersion"     "${APP_VERSION}"
VIAddVersionKey "LegalCopyright"  "© 2026 ${PUBLISHER}"

; ─── UI Pages ─────────────────────────────────────────────────────
!define MUI_ABORTWARNING
!define MUI_ICON   "kaydan.ico"
!define MUI_UNICON "kaydan.ico"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "LICENSE.txt"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "French"

; ─── Sections ─────────────────────────────────────────────────────
Section "Core" SEC_CORE
    SectionIn RO

    SetOutPath "$INSTDIR"

    ; Binaire principal
    File /oname=${BINARY_NAME} "kshield-agent-windows-amd64.exe"

    ; NSSM (service manager)
    File "nssm.exe"

    ; Docs
    File "README.txt"

    ; Dossier de config par défaut (vide, l'admin y copie sa config)
    CreateDirectory "$COMMONAPPDATA\KaydanEdge"
    CreateDirectory "$COMMONAPPDATA\KaydanEdge\logs"

    ; Ajoute au PATH pour permettre `kshield-agent` en ligne de commande
    EnVar::SetHKLM
    EnVar::AddValue "PATH" "$INSTDIR"
    Pop $0

    ; Enregistre l'uninstaller
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    ; Registre — Add/Remove Programs
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
        "DisplayName"     "${APP_NAME}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
        "DisplayVersion"  "${APP_VERSION}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
        "Publisher"       "${PUBLISHER}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
        "URLInfoAbout"    "${WEB_URL}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
        "InstallLocation" "$INSTDIR"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
        "UninstallString" "$\"$INSTDIR\Uninstall.exe$\""
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
        "NoModify" 1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
        "NoRepair" 1
SectionEnd

Section "Service Windows" SEC_SERVICE
    ; Supprime un ancien service s'il existe (mise à jour)
    ExecWait '"$INSTDIR\nssm.exe" stop ${SERVICE_NAME} confirm' $0
    ExecWait '"$INSTDIR\nssm.exe" remove ${SERVICE_NAME} confirm' $0

    ; Crée le service via NSSM
    ExecWait '"$INSTDIR\nssm.exe" install ${SERVICE_NAME} "$INSTDIR\${BINARY_NAME}" run' $0
    ExecWait '"$INSTDIR\nssm.exe" set ${SERVICE_NAME} AppDirectory "$INSTDIR"' $0
    ExecWait '"$INSTDIR\nssm.exe" set ${SERVICE_NAME} AppEnvironmentExtra "KSHIELD_CONFIG_FILE=$COMMONAPPDATA\KaydanEdge\kshield-agent.toml"' $0
    ExecWait '"$INSTDIR\nssm.exe" set ${SERVICE_NAME} DisplayName "${APP_NAME}"' $0
    ExecWait '"$INSTDIR\nssm.exe" set ${SERVICE_NAME} Description "Passerelle temps réel Kaydan Shield"' $0
    ExecWait '"$INSTDIR\nssm.exe" set ${SERVICE_NAME} Start SERVICE_AUTO_START' $0
    ExecWait '"$INSTDIR\nssm.exe" set ${SERVICE_NAME} AppStdout "$COMMONAPPDATA\KaydanEdge\logs\service-stdout.log"' $0
    ExecWait '"$INSTDIR\nssm.exe" set ${SERVICE_NAME} AppStderr "$COMMONAPPDATA\KaydanEdge\logs\service-stderr.log"' $0
    ExecWait '"$INSTDIR\nssm.exe" set ${SERVICE_NAME} AppRotateFiles 1' $0
    ExecWait '"$INSTDIR\nssm.exe" set ${SERVICE_NAME} AppRotateBytes 10485760' $0
    ExecWait '"$INSTDIR\nssm.exe" set ${SERVICE_NAME} AppExit Default Restart' $0
    ExecWait '"$INSTDIR\nssm.exe" set ${SERVICE_NAME} AppRestartDelay 5000' $0

    ; Ne pas démarrer le service ici — l'admin doit d'abord copier
    ; la config kshield-agent.toml dans C:\ProgramData\KaydanEdge\.
SectionEnd

; ─── Uninstaller ──────────────────────────────────────────────────
Section "Uninstall"
    ; Stop + remove service
    ExecWait '"$INSTDIR\nssm.exe" stop ${SERVICE_NAME} confirm' $0
    ExecWait '"$INSTDIR\nssm.exe" remove ${SERVICE_NAME} confirm' $0

    ; Retire du PATH
    EnVar::SetHKLM
    EnVar::DeleteValue "PATH" "$INSTDIR"
    Pop $0

    ; Supprime fichiers
    Delete "$INSTDIR\${BINARY_NAME}"
    Delete "$INSTDIR\nssm.exe"
    Delete "$INSTDIR\README.txt"
    Delete "$INSTDIR\Uninstall.exe"
    RMDir "$INSTDIR"

    ; Note : on ne supprime PAS $COMMONAPPDATA\KaydanEdge\ pour préserver
    ; la config et les logs (uninstall doit être "réversible").

    ; Registre
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"

    MessageBox MB_OK|MB_ICONINFORMATION \
        "Kaydan Edge Gateway a été désinstallé.$\n$\nLa config et les logs restent dans $COMMONAPPDATA\KaydanEdge\ — supprimez-les manuellement si nécessaire."
SectionEnd

; ─── Post-install message ────────────────────────────────────────
Function .onInstSuccess
    MessageBox MB_OK|MB_ICONINFORMATION \
"Installation terminée.$\n$\nProchaines étapes :$\n$\n\
1. Télécharger la config depuis Kaydan Shield → Edge Gateway$\n\
2. Copier config\kshield-agent.toml dans C:\ProgramData\KaydanEdge\$\n\
3. Ouvrir PowerShell en admin, exécuter :$\n\
     kshield-agent activate$\n\
4. Démarrer le service :$\n\
     Start-Service ${SERVICE_NAME}$\n$\n\
Vérifier sur : ${WEB_URL}/edge-gateway"
FunctionEnd
