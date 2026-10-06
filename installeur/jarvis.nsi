; Installeur Windows de Jarvis (NSIS 3).
; Construit avec : bash installeur/construire.sh  -> Installer-Jarvis.exe
; L'installation se fait dans %LOCALAPPDATA%\Jarvis, sans droits administrateur.
; Python et les bibliothèques sont téléchargés pendant l'installation grâce à uv.

Unicode true
!include "MUI2.nsh"
!include "LogicLib.nsh"

!define APP "Jarvis"
; VERSION est passé par construire.sh (contenu du fichier VERSION).
!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\Jarvis"

Name "${APP}"
OutFile "${OUTFILE}"
InstallDir "$LOCALAPPDATA\Jarvis"
RequestExecutionLevel user
SetCompressor /SOLID lzma
BrandingText "Jarvis ${VERSION}"
ShowInstDetails show

VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "Jarvis"
VIAddVersionKey "FileDescription" "Installeur de Jarvis, assistant personnel vocal"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "LegalCopyright" "Michel"

!define MUI_ICON "${STAGE}\jarvis.ico"
!define MUI_UNICON "${STAGE}\jarvis.ico"
!define MUI_ABORTWARNING

!define MUI_WELCOMEPAGE_TITLE "Installation de Jarvis"
!define MUI_WELCOMEPAGE_TEXT "Jarvis est ton assistant personnel vocal.$\r$\n$\r$\nL'installation télécharge les composants nécessaires (environ 400 Mo) : garde Internet branché, cela prend quelques minutes.$\r$\n$\r$\nUne icône Jarvis sera ajoutée sur ton bureau."
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_TITLE "Jarvis est installé"
!define MUI_FINISHPAGE_TEXT "Double-clique sur l'icône Jarvis de ton bureau pour le lancer.$\r$\n$\r$\nAu premier lancement, il te demandera de connecter ton abonnement Claude."
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "Lancer Jarvis maintenant"
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchJarvis
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "French"

; Définit une variable d'environnement pour les programmes lancés par l'installeur.
!macro SetEnv NAME VALUE
  System::Call 'Kernel32::SetEnvironmentVariable(t, t) i ("${NAME}", "${VALUE}")'
!macroend

Section "Jarvis" SecMain
  SetOutPath "$INSTDIR"
  ; Ne pas écraser les réglages (.env) ni la mémoire (data\) lors d'une réinstallation.
  RMDir /r "$INSTDIR\jarvis"
  File /r "${STAGE}\*.*"

  !insertmacro SetEnv "UV_PYTHON_INSTALL_DIR" "$INSTDIR\python"
  !insertmacro SetEnv "UV_CACHE_DIR" "$INSTDIR\cache"
  !insertmacro SetEnv "UV_PYTHON_PREFERENCE" "only-managed"
  !insertmacro SetEnv "UV_LINK_MODE" "copy"
  !insertmacro SetEnv "UV_NO_PROGRESS" "1"
  !insertmacro SetEnv "NO_COLOR" "1"

  DetailPrint "Téléchargement de Python..."
  nsExec::ExecToLog '"$INSTDIR\uv.exe" venv --python 3.12 --allow-existing "$INSTDIR\.venv"'
  Pop $0
  ${If} $0 != 0
    MessageBox MB_ICONSTOP "Impossible de télécharger Python (code $0).$\r$\nVérifie ta connexion Internet puis relance l'installeur."
    Abort
  ${EndIf}

  DetailPrint "Installation des composants de Jarvis (quelques minutes)..."
  nsExec::ExecToLog '"$INSTDIR\uv.exe" pip install --python "$INSTDIR\.venv\Scripts\python.exe" -r "$INSTDIR\requirements-windows.txt"'
  Pop $0
  ${If} $0 != 0
    MessageBox MB_ICONSTOP "L'installation des composants a échoué (code $0).$\r$\nVérifie ta connexion Internet puis relance l'installeur."
    Abort
  ${EndIf}
  RMDir /r "$INSTDIR\cache"

  ; Claude Code permet à Jarvis de réfléchir avec l'abonnement Claude (Pro ou Max) de l'utilisateur.
  ${IfNot} ${FileExists} "$PROFILE\.local\bin\claude.exe"
    DetailPrint "Installation de Claude Code (pour utiliser ton abonnement Claude)..."
    nsExec::ExecToLog 'powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://claude.ai/install.ps1 | iex"'
    Pop $0
  ${EndIf}

  ; FFmpeg sert au montage vidéo. Facultatif : on continue même si winget n'est pas disponible.
  DetailPrint "Installation de FFmpeg pour le montage vidéo (facultatif)..."
  nsExec::ExecToLog 'winget install -e --id Gyan.FFmpeg --silent --accept-source-agreements --accept-package-agreements'
  Pop $0

  ; Raccourcis : bureau et menu Démarrer.
  SetOutPath "$INSTDIR"
  CreateShortcut "$DESKTOP\Jarvis.lnk" "$INSTDIR\.venv\Scripts\pythonw.exe" '"$INSTDIR\Jarvis.pyw"' "$INSTDIR\jarvis.ico" 0
  CreateDirectory "$SMPROGRAMS\Jarvis"
  CreateShortcut "$SMPROGRAMS\Jarvis\Jarvis.lnk" "$INSTDIR\.venv\Scripts\pythonw.exe" '"$INSTDIR\Jarvis.pyw"' "$INSTDIR\jarvis.ico" 0
  CreateShortcut "$SMPROGRAMS\Jarvis\Désinstaller Jarvis.lnk" "$INSTDIR\Desinstaller.exe"

  WriteUninstaller "$INSTDIR\Desinstaller.exe"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayName" "Jarvis"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINST_KEY}" "Publisher" "Jarvis"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayIcon" "$INSTDIR\jarvis.ico"
  WriteRegStr HKCU "${UNINST_KEY}" "UninstallString" '"$INSTDIR\Desinstaller.exe"'
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoRepair" 1
SectionEnd

Function LaunchJarvis
  SetOutPath "$INSTDIR"
  Exec '"$INSTDIR\.venv\Scripts\pythonw.exe" "$INSTDIR\Jarvis.pyw"'
FunctionEnd

Section "Uninstall"
  Delete "$DESKTOP\Jarvis.lnk"
  Delete "$APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\Jarvis.lnk"
  RMDir /r "$SMPROGRAMS\Jarvis"
  RMDir /r "$INSTDIR"
  DeleteRegKey HKCU "${UNINST_KEY}"
SectionEnd
