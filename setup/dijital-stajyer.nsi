; Dijital Stajyer kurulum paketi (NSIS 3). Derleme: setup/derle.py (dosyalar.nsh / silme.nsh'yi o uretir).
Unicode True
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"
!insertmacro GetParent

!ifndef SURUM
  !define SURUM "1.0.0"
!endif
!ifndef YIL
  !define YIL "2026"
!endif
!ifndef PYTHON_SURUM
  !define PYTHON_SURUM "3.12.10"
!endif
!define AD "Dijital Stajyer"
!define KLASOR "DijitalStajyer"
!define YAYINCI "Adem Yılmaz, SMMM"
!define WEB "https://smmmyilmaz.com"
!define KAYIT "Software\Microsoft\Windows\CurrentVersion\Uninstall\${KLASOR}"
!define PYTHON_URL "https://www.python.org/ftp/python/${PYTHON_SURUM}/python-${PYTHON_SURUM}-amd64.exe"

Name "${AD}"
OutFile "${CIKTI_EXE}"
InstallDir "$LOCALAPPDATA\${KLASOR}"
InstallDirRegKey HKCU "${KAYIT}" "InstallLocation"
RequestExecutionLevel user
SetCompressor /SOLID lzma
BrandingText "© ${YIL} ${YAYINCI} — Tüm Hakları Saklıdır"
ShowInstDetails show
ShowUninstDetails show

VIProductVersion "${SURUM}.0"
VIAddVersionKey /LANG=1055 "ProductName" "${AD}"
VIAddVersionKey /LANG=1055 "CompanyName" "${YAYINCI}"
VIAddVersionKey /LANG=1055 "LegalCopyright" "© ${YIL} ${YAYINCI}. Tüm hakları saklıdır."
VIAddVersionKey /LANG=1055 "FileDescription" "${AD} kurulum programı"
VIAddVersionKey /LANG=1055 "FileVersion" "${SURUM}"
VIAddVersionKey /LANG=1055 "ProductVersion" "${SURUM}"

!define MUI_ICON "${SIMGE}"
!define MUI_UNICON "${SIMGE}"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "${AD} ${SURUM} kurulumuna hoş geldiniz"
!define MUI_WELCOMEPAGE_TEXT "Bu sihirbaz ${AD} programını bilgisayarınıza kurar.$\r$\n$\r$\nProgram Luca'dan e-Fatura / e-Arşiv indirir, kâr/zarar tahmini çıkarır ve rapor hazırlar.$\r$\n$\r$\nGerekli bileşenler (Python, paketler, tarayıcı) kurulum sırasında internetten indirilir; bu yüzden internet bağlantınızın açık olması gerekir. Kuruluma yönetici hakkı gerekmez.$\r$\n$\r$\nDevam etmek için İleri'ye tıklayın."
!define MUI_LICENSEPAGE_CHECKBOX
!define MUI_FINISHPAGE_TITLE "Kurulum tamamlandı"
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "${AD} programını şimdi aç"
!define MUI_FINISHPAGE_RUN_FUNCTION ProgramiAc
!define MUI_FINISHPAGE_LINK "smmmyilmaz.com"
!define MUI_FINISHPAGE_LINK_LOCATION "${WEB}"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${LISANS_METNI}"
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Turkish"

Var PY
Var PYW

; --- Python bulma ----------------------------------------------------------------------------

; Yigin: aday komut ('py -3', '"C:\...\python.exe"' ...). Calisiyor, surum >= 3.9 ve tkinter varsa $PY'ye
; python.exe'nin tam yolunu yazar.
Function PythonDene
  Pop $0
  ${If} $PY != ""
    Return
  ${EndIf}
  nsExec::ExecToStack '$0 -c "import sys,tkinter;print(sys.executable);sys.exit(0 if sys.version_info>=(3,9) else 1)"'
  Pop $1
  Pop $2
  ${If} $1 == 0
    ; cikti sonundaki satir sonlarini temizle
    ${Do}
      StrCpy $3 $2 1 -1
      ${If} $3 == "$\r"
      ${OrIf} $3 == "$\n"
      ${OrIf} $3 == " "
        StrCpy $2 $2 -1
      ${Else}
        ${ExitDo}
      ${EndIf}
    ${Loop}
    ${If} $2 != ""
    ${AndIf} ${FileExists} "$2"
      StrCpy $PY $2
    ${EndIf}
  ${EndIf}
FunctionEnd

Function PythonBul
  StrCpy $PY ""
  Push 'py -3'
  Call PythonDene
  ; Python.org yukleyicisinin kullanici klasorune kurdugu surumler (yeniden eskiye degil, alfabetik; sonuncusu kalir)
  ${If} $PY == ""
    FindFirst $4 $5 "$LOCALAPPDATA\Programs\Python\Python3*"
    ${DoWhile} $5 != ""
      Push '"$LOCALAPPDATA\Programs\Python\$5\python.exe"'
      Call PythonDene
      FindNext $4 $5
    ${Loop}
    FindClose $4
  ${EndIf}
  Push 'python'
  Call PythonDene
FunctionEnd

Function PythonuKur
  StrCpy $0 "$TEMP\python-${PYTHON_SURUM}-amd64.exe"
  DetailPrint "Python bulunamadı; python.org'dan indiriliyor (yaklaşık 25 MB)..."
  nsExec::ExecToLog `powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Uri '${PYTHON_URL}' -OutFile '$0'"`
  Pop $1
  ${If} $1 != 0
  ${OrIfNot} ${FileExists} "$0"
    DetailPrint "Python indirilemedi (internet bağlantısını kontrol edin)."
    Return
  ${EndIf}
  ; indirilen dosya Python Software Foundation tarafindan imzali mi
  nsExec::ExecToLog `powershell -NoProfile -ExecutionPolicy Bypass -Command "$$s=Get-AuthenticodeSignature '$0'; if($$s.Status -eq 'Valid' -and $$s.SignerCertificate.Subject -like '*Python Software Foundation*'){exit 0}else{exit 1}"`
  Pop $1
  ${If} $1 != 0
    DetailPrint "İndirilen Python yükleyicisinin imzası doğrulanamadı; kurulmadı."
    Delete "$0"
    Return
  ${EndIf}
  DetailPrint "Python ${PYTHON_SURUM} kuruluyor (1-2 dakika sürebilir)..."
  ExecWait '"$0" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=0 Include_test=0 Include_tcltk=1 Include_pip=1 Shortcuts=0' $1
  Delete "$0"
  DetailPrint "Python yükleyicisi çıkış kodu: $1"
  Push '"$LOCALAPPDATA\Programs\Python\Python312\python.exe"'
  Call PythonDene
FunctionEnd

; --- Bolumler --------------------------------------------------------------------------------

Section "${AD} programı" SecProgram
  SectionIn RO
  SetOutPath "$INSTDIR"
  !include "dosyalar.nsh"
  SetOutPath "$INSTDIR\luca-bot"
  File /oname=lisans.json "${LISANS_DOSYASI}"
  WriteUninstaller "$INSTDIR\Kaldir.exe"
  WriteRegStr HKCU "${KAYIT}" "DisplayName" "${AD}"
  WriteRegStr HKCU "${KAYIT}" "DisplayVersion" "${SURUM}"
  WriteRegStr HKCU "${KAYIT}" "Publisher" "${YAYINCI}"
  WriteRegStr HKCU "${KAYIT}" "URLInfoAbout" "${WEB}"
  WriteRegStr HKCU "${KAYIT}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${KAYIT}" "DisplayIcon" "$INSTDIR\luca-bot\varliklar\logo.ico"
  WriteRegStr HKCU "${KAYIT}" "UninstallString" '"$INSTDIR\Kaldir.exe"'
  WriteRegDWORD HKCU "${KAYIT}" "NoModify" 1
  WriteRegDWORD HKCU "${KAYIT}" "NoRepair" 1
SectionEnd

Section "Gerekli bileşenler (Python, paketler, Chromium tarayıcısı)" SecBilesen
  Call PythonBul
  ${If} $PY == ""
    Call PythonuKur
  ${EndIf}
  ${If} $PY == ""
    DetailPrint "UYARI: Python kurulamadı. Program dosyaları yerinde; Python'u elle kurup programı açtığınızda"
    DetailPrint "Kurulum Sihirbazı eksik bileşenleri tamamlar (OKU-BENI-ONCE.txt)."
    MessageBox MB_ICONEXCLAMATION|MB_OK "Python kurulamadı (internet bağlantısı gerekir).$\r$\n$\r$\nProgram dosyaları kuruldu. Python'u python.org'dan kurup (kurarken 'Add python.exe to PATH' ve 'tcl/tk' seçili olsun) programı açtığınızda Kurulum Sihirbazı kalan bileşenleri tamamlar.$\r$\n$\r$\nAyrıntı: $INSTDIR\luca-bot\OKU-BENI-ONCE.txt" /SD IDOK
  ${Else}
    DetailPrint "Python: $PY"
    DetailPrint "Python paketleri kuruluyor (pip)..."
    nsExec::ExecToLog '"$PY" -m pip install --disable-pip-version-check -r "$INSTDIR\luca-bot\requirements.txt"'
    Pop $1
    ${If} $1 != 0
      DetailPrint "UYARI: pip çıkış kodu $1; programı açınca Kurulum Sihirbazı yeniden dener."
    ${EndIf}
    DetailPrint "Chromium tarayıcısı indiriliyor (yaklaşık 150 MB; birkaç dakika sürebilir)..."
    nsExec::ExecToLog '"$PY" -m playwright install chromium'
    Pop $1
    ${If} $1 != 0
      DetailPrint "UYARI: Chromium kurulamadı (çıkış kodu $1); Kurulum Sihirbazı yeniden dener."
    ${EndIf}
    FileOpen $0 "$INSTDIR\luca-bot\python-yolu.txt" w
    FileWrite $0 "$PY"
    FileClose $0
  ${EndIf}
SectionEnd

Section "Masaüstü ve Başlat menüsü kısayolları" SecKisayol
  ; Python yolu: bilesen bolumu calistiysa $PY dolu; degilse (atlandi) daha once yazilmis dosyadan ya da bat'tan
  ${If} $PY == ""
    ${If} ${FileExists} "$INSTDIR\luca-bot\python-yolu.txt"
      FileOpen $0 "$INSTDIR\luca-bot\python-yolu.txt" r
      FileRead $0 $PY
      FileClose $0
    ${EndIf}
  ${EndIf}
  SetOutPath "$INSTDIR\luca-bot"
  CreateDirectory "$SMPROGRAMS\${AD}"
  ${If} $PY != ""
    ${GetParent} "$PY" $0
    StrCpy $PYW "$0\pythonw.exe"
  ${EndIf}
  ${If} $PYW != ""
  ${AndIf} ${FileExists} "$PYW"
    CreateShortcut "$DESKTOP\${AD}.lnk" "$PYW" '"$INSTDIR\luca-bot\luca_arayuz.py"' "$INSTDIR\luca-bot\varliklar\logo.ico" 0
    CreateShortcut "$SMPROGRAMS\${AD}\${AD}.lnk" "$PYW" '"$INSTDIR\luca-bot\luca_arayuz.py"' "$INSTDIR\luca-bot\varliklar\logo.ico" 0
  ${Else}
    ; Python bulunamadi: bat dosyasi Python'u kendisi arar / yol gosterir
    CreateShortcut "$DESKTOP\${AD}.lnk" "$INSTDIR\luca-bot\luca-arayuz.bat" "" "$INSTDIR\luca-bot\varliklar\logo.ico" 0
    CreateShortcut "$SMPROGRAMS\${AD}\${AD}.lnk" "$INSTDIR\luca-bot\luca-arayuz.bat" "" "$INSTDIR\luca-bot\varliklar\logo.ico" 0
  ${EndIf}
  CreateShortcut "$SMPROGRAMS\${AD}\Program klasörünü aç.lnk" "$INSTDIR\luca-bot"
  CreateShortcut "$SMPROGRAMS\${AD}\Başlarken.lnk" "$INSTDIR\luca-bot\BASLARKEN.txt"
  CreateShortcut "$SMPROGRAMS\${AD}\Kaldır.lnk" "$INSTDIR\Kaldir.exe"
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecProgram} "Program dosyaları, lisans ve kullanım notları."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecBilesen} "Python 3 (yoksa python.org'dan kurulur), gerekli Python paketleri ve Chromium tarayıcısı. İnternet gerekir."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecKisayol} "Masaüstüne ve Başlat menüsüne simge koyar."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Function ProgramiAc
  ${If} ${FileExists} "$DESKTOP\${AD}.lnk"
    ExecShell "open" "$DESKTOP\${AD}.lnk"
  ${Else}
    ExecShell "open" "$INSTDIR\luca-bot\luca-arayuz.bat"
  ${EndIf}
FunctionEnd

; --- Kaldirma --------------------------------------------------------------------------------

Section "Uninstall"
  !include "silme.nsh"
  Delete "$INSTDIR\luca-bot\lisans.json"
  Delete "$INSTDIR\luca-bot\lisans-durum.json"
  Delete "$INSTDIR\luca-bot\python-yolu.txt"
  Delete "$DESKTOP\${AD}.lnk"
  RMDir /r "$SMPROGRAMS\${AD}"
  Delete "$INSTDIR\Kaldir.exe"
  RMDir "$INSTDIR\luca-bot"
  RMDir "$INSTDIR\kar-zarar"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "${KAYIT}"
  ${If} ${FileExists} "$INSTDIR"
    MessageBox MB_ICONINFORMATION|MB_OK "Program kaldırıldı. Ayarlarınız (ayarlar.json), indirilen faturalar ve raporlar silinmedi; klasör:$\r$\n$INSTDIR$\r$\n$\r$\nİstemezseniz bu klasörü elle silebilirsiniz." /SD IDOK
  ${EndIf}
SectionEnd
