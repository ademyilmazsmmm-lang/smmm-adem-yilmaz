' Beyanname Takip: programi siyah pencere acmadan arka planda calistirir ve tarayicida acar.
' Zaten aciksa yalnizca tarayicida acar. Ilk seferde (Python ortami yoksa) kurulumu gorunur bir pencerede yapar.
Option Explicit
Dim sh, fso, yerel, adres, pythonw, i
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
yerel = fso.GetParentFolderName(WScript.ScriptFullName)
adres = "http://127.0.0.1:8000"

Function CalisiyorMu()
    Dim x
    CalisiyorMu = False
    On Error Resume Next
    Set x = CreateObject("MSXML2.ServerXMLHTTP.6.0")
    x.setTimeouts 1000, 1000, 1500, 1500
    x.setProxy 1
    x.open "GET", adres & "/saglik", False
    x.send
    If Err.Number = 0 Then
        If x.status = 200 Then CalisiyorMu = True
    End If
    On Error GoTo 0
End Function

If CalisiyorMu() Then
    sh.Run adres, 1, False
    WScript.Quit
End If

If Not fso.FileExists(yerel & "\ayarlar.env") Then
    MsgBox "ayarlar.env dosyasi yok. 'yerel' klasorunde ayarlar-ornek.env dosyasini kopyalayip adini ayarlar.env yapin ve doldurun.", 48, "Beyanname Takip"
    WScript.Quit
End If

pythonw = yerel & "\.venv\Scripts\pythonw.exe"
sh.CurrentDirectory = yerel
If Not fso.FileExists(pythonw) Then
    MsgBox "Ilk kurulum yapilacak (3-5 dakika surer). Siyah bir pencere acilacak; kurulum bitene kadar kapatmayin. Devam icin Tamam'a basin.", 64, "Beyanname Takip"
    sh.Run """" & yerel & "\kur.bat""", 1, True
    If Not fso.FileExists(pythonw) Then
        MsgBox "Kurulum tamamlanamadi. Siyah penceredeki hata yazisini gonderin.", 16, "Beyanname Takip"
        WScript.Quit
    End If
End If

sh.Run """" & pythonw & """ """ & yerel & "\baslat.py""", 0, False

' Acilmasini bekle (en cok 45 sn). Tarayiciyi program kendisi acar; ayar hatasi varsa program kendi mesaj kutusunu gosterir.
For i = 1 To 45
    WScript.Sleep 1000
    If CalisiyorMu() Then WScript.Quit
Next
MsgBox "Program 45 saniye icinde acilmadi. 'yerel' klasorundeki program.log dosyasina bakin.", 48, "Beyanname Takip"
