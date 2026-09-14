"""
Musavir Otomasyon Sistemi - WhatsApp Tahakkuk Gonderim Uygulamasi

Bir klasordeki PDF tahakkuk dosyalarini okur, dosya isminden mukellef adi,
vergi turu ve donem bilgisini cikarir, firmalar.json rehberinden telefon
numarasini eslestirir ve WhatsApp Desktop uzerinden otomatik gonderim yapar.

NOT: /gonder rotasindaki otomasyon (PyAutoGUI + PowerShell Set-Clipboard)
yalnizca Windows uzerinde, WhatsApp Desktop uygulamasi kurulu ve acik
oldugunda calisir.
"""
import json
import os
import platform
import re
import subprocess
import time
import webbrowser

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FIRMALAR_DOSYASI = os.path.join(BASE_DIR, "firmalar.json")

DONEM_REGEX = re.compile(r"(\d{8}-\d{8})")


def firmalari_yukle():
    if not os.path.exists(FIRMALAR_DOSYASI):
        return {}
    with open(FIRMALAR_DOSYASI, "r", encoding="utf-8") as f:
        return json.load(f)


def turkce_kucuk(metin):
    """Turkce buyuk/kucuk harf donusumunu (I/i, I/ı) dogru yapan yardimci fonksiyon."""
    return metin.replace("İ", "i").replace("I", "ı").lower()


def vergi_turu_tespit_et(dosya_adi_ham):
    """Dosya adindaki anahtar kelimelere gore vergi turunu belirler."""
    normal = turkce_kucuk(dosya_adi_ham)
    if "kdv1" in normal:
        return "KDV"
    if "muhsgk" in normal:
        return "STOPAJ / SGK"
    if "geçici" in normal or "gecici" in normal:
        return "PEŞİN VERGİ (P.V.)"
    return "BİLİNMEYEN"


def donem_tespit_et(dosya_adi_ham):
    """Dosya adindaki 01072026-31072026 formatindaki donem araligini regex ile bulur."""
    eslesme = DONEM_REGEX.search(dosya_adi_ham)
    return eslesme.group(1) if eslesme else ""


def dosya_adini_parcala(dosya_adi, firmalar):
    """
    Dosya adini '_' ile ayirip mukellef adi, vergi turu, donem ve telefon
    bilgilerini cikarir. Ornek: SAKIR LTD._034252_7981552167_KDV1_45_
    01072026-31072026_THK_28.pdf
    """
    ad, _ext = os.path.splitext(dosya_adi)
    parcalar = ad.split("_")
    firma_kisa = parcalar[0].strip() if parcalar and parcalar[0].strip() else ad

    firma_bilgisi = firmalar.get(firma_kisa)
    if firma_bilgisi:
        firma_tam = firma_bilgisi.get("tam_ad", firma_kisa)
        telefon = firma_bilgisi.get("telefon", "")
        uyari = False
    else:
        firma_tam = firma_kisa
        telefon = ""
        uyari = True

    return {
        "dosya_adi": dosya_adi,
        "firma_kisa": firma_kisa,
        "firma_tam": firma_tam,
        "telefon": telefon,
        "vergi_turu": vergi_turu_tespit_et(ad),
        "donem": donem_tespit_et(ad),
        "uyari": uyari,
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/klasor_tara", methods=["POST"])
def klasor_tara():
    veri = request.get_json(silent=True) or {}
    klasor_yolu = (veri.get("klasor_yolu") or "").strip()

    if not klasor_yolu:
        return jsonify({"success": False, "error": "Klasor yolu bos olamaz."}), 400

    if not os.path.isdir(klasor_yolu):
        return jsonify({"success": False, "error": f"Klasor bulunamadi: {klasor_yolu}"}), 400

    firmalar = firmalari_yukle()

    try:
        dosyalar = sorted(
            f for f in os.listdir(klasor_yolu) if f.lower().endswith(".pdf")
        )
    except OSError as exc:
        return jsonify({"success": False, "error": f"Klasor okunamadi: {exc}"}), 400

    sonuc = []
    for i, dosya_adi in enumerate(dosyalar):
        satir = dosya_adini_parcala(dosya_adi, firmalar)
        satir["id"] = i
        satir["dosya_yolu"] = os.path.join(klasor_yolu, dosya_adi)
        sonuc.append(satir)

    return jsonify({"success": True, "adet": len(sonuc), "dosyalar": sonuc})


@app.route("/gonder", methods=["POST"])
def gonder():
    veri = request.get_json(silent=True) or {}
    dosya_yolu = (veri.get("dosya_yolu") or "").strip()
    telefon = (veri.get("telefon") or "").strip()
    mesaj = (veri.get("mesaj") or "").strip()

    if not dosya_yolu or not os.path.isfile(dosya_yolu):
        return jsonify({"success": False, "error": "PDF dosyasi bulunamadi."}), 400
    if not telefon:
        return jsonify({"success": False, "error": "Telefon numarasi bulunamadi. Once firmalar.json dosyasini guncelleyin."}), 400
    if not mesaj:
        return jsonify({"success": False, "error": "Gonderilecek mesaj bos olamaz."}), 400

    try:
        whatsapp_ile_gonder(telefon, dosya_yolu, mesaj)
    except RuntimeError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:  # pylint: disable=broad-except
        return jsonify({"success": False, "error": f"Gonderim sirasinda hata olustu: {exc}"}), 500

    return jsonify({"success": True})


def whatsapp_ile_gonder(telefon, dosya_yolu, mesaj):
    """
    WhatsApp Desktop uzerinden PDF + mesaj gonderimini otomatiklestirir.
    Sadece Windows'ta calisir; pyautogui/pyperclip Windows disinda
    guvenilir sekilde calismadigi icin burada gecikmeli (lazy) import
    edilir.
    """
    if platform.system() != "Windows":
        raise RuntimeError(
            "Bu otomasyon yalnizca Windows uzerinde, WhatsApp Desktop uygulamasi "
            "acikken calisir. Sunucu Windows disinda calistigi icin gonderim "
            "yapilamadi."
        )

    try:
        import pyautogui
        import pyperclip
    except ImportError as exc:
        raise RuntimeError(
            "pyautogui / pyperclip kutuphaneleri kurulu degil. "
            "'pip install pyautogui pyperclip' komutu ile kurun."
        ) from exc

    webbrowser.open(f"whatsapp://send?phone={telefon}")
    time.sleep(4)

    ps_komutu = f'Set-Clipboard -Path "{dosya_yolu}"'
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_komutu],
        check=True,
    )
    pyautogui.hotkey("ctrl", "v")
    time.sleep(1.5)

    pyperclip.copy(mesaj)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.5)

    pyautogui.press("enter")


if __name__ == "__main__":
    app.run(debug=True)
