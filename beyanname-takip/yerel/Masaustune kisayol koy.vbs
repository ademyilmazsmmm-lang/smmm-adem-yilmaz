' Masaustune kisayollar koyar (bir kez calistirmaniz yeter):
'   "Beyanname Takip"        : programi acar
'   "Luca - Ofis" vb.        : ayarlar.env'deki her Luca hesabi icin, Luca'ya otomatik giris yapip acik birakir
Option Explicit
Dim sh, fso, yerel, masa, k, h, hesaplar, adlar

Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
yerel = fso.GetParentFolderName(WScript.ScriptFullName)
masa = sh.SpecialFolders("Desktop")

Function HesapListesi()
    Dim metin, re, m
    HesapListesi = Array("ofis", "isletme")
    If Not fso.FileExists(yerel & "\ayarlar.env") Then Exit Function
    metin = fso.OpenTextFile(yerel & "\ayarlar.env", 1).ReadAll
    Set re = New RegExp
    re.Pattern = "^\s*LUCA_HESAPLAR\s*=\s*(.+?)\s*$"
    re.MultiLine = True
    Set m = re.Execute(metin)
    If m.Count > 0 Then HesapListesi = Split(Replace(Trim(m(0).SubMatches(0)), " ", ""), ",")
End Function

Function Gorunen(ad)
    ad = LCase(Trim(ad))
    If ad = "ofis" Then
        Gorunen = "Ofis"
    ElseIf ad = "isletme" Then
        Gorunen = ChrW(304) & ChrW(351) & "letme"
    Else
        Gorunen = UCase(Left(ad, 1)) & Mid(ad, 2)
    End If
End Function

Set k = sh.CreateShortcut(masa & "\Beyanname Takip.lnk")
k.TargetPath = yerel & "\Beyanname Takip.vbs"
k.WorkingDirectory = yerel
k.Description = "Beyanname Takip"
k.Save
adlar = "Beyanname Takip"

hesaplar = HesapListesi()
For Each h In hesaplar
    If Len(Trim(h)) > 0 Then
        Set k = sh.CreateShortcut(masa & "\Luca - " & Gorunen(h) & ".lnk")
        k.TargetPath = "wscript.exe"
        k.Arguments = """" & yerel & "\Luca Giris.vbs"" " & LCase(Trim(h))
        k.WorkingDirectory = yerel
        k.Description = "Luca'ya otomatik giris (" & Gorunen(h) & ")"
        k.Save
        adlar = adlar & ", Luca - " & Gorunen(h)
    End If
Next
MsgBox "Masaustune kisayollar konuldu: " & adlar & ". Artik onlara cift tiklamaniz yeter.", 64, "Beyanname Takip"
