' Luca'ya hizli giris: secilen hesapla (ofis / isletme) Luca'ya girer, dogrulama kodunu kendisi yazar, Luca acik kalir.
' Siyah pencere acmaz. Hesap adi arguman olarak gelir (masaustundeki "Luca - Ofis" / "Luca - Isletme" kisayollari verir).
Option Explicit
Dim sh, fso, yerel, hesap, pythonw
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
yerel = fso.GetParentFolderName(WScript.ScriptFullName)
hesap = ""
If WScript.Arguments.Count > 0 Then hesap = WScript.Arguments(0)

If Not fso.FileExists(yerel & "\ayarlar.env") Then
    MsgBox "ayarlar.env dosyasi yok. Once Beyanname Takip kurulumunu yapin.", 48, "Luca Giris"
    WScript.Quit
End If

pythonw = yerel & "\.venv\Scripts\pythonw.exe"
sh.CurrentDirectory = yerel
If Not fso.FileExists(pythonw) Then
    MsgBox "Ilk kurulum yapilacak (3-5 dakika surer). Siyah bir pencere acilacak; kurulum bitene kadar kapatmayin. Devam icin Tamam'a basin.", 64, "Luca Giris"
    sh.Run """" & yerel & "\kur.bat""", 1, True
    If Not fso.FileExists(pythonw) Then
        MsgBox "Kurulum tamamlanamadi. Siyah penceredeki hata yazisini gonderin.", 16, "Luca Giris"
        WScript.Quit
    End If
End If

sh.Run """" & pythonw & """ """ & yerel & "\luca_giris.py"" """ & hesap & """", 0, False
