# -*- coding: utf-8 -*-
"""Luca arama/filtre pencerelerindeki alanlari bulma ve doldurma.

Pencerelerin etiket/kutu yapisi (BEYANNAME ARAMA, Hesap Arama ...) ayni:
satirdaki ilk metin etiket, ayni satirdaki select/input kutulari alanlardir.
Alanlar yalnizca baslikli pencerenin icinde aranir (ayni etiket liste
basliklarinda da gecebiliyor).
"""

from .luca_ekran import cerceveler
from .ortak import sadelestir

# arguman: {baslik, etiketler}. Bulunan kutular data-lucabot-alan="<etiket>#<sira>" ile isaretlenir
ALANLAR_JS = r"""arg => {
  document.querySelectorAll('[data-lucabot-alan]').forEach(e => e.removeAttribute('data-lucabot-alan'));
  const gorunur = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  const duz = e => (e.textContent || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const bulunan = {};
  const baslik = [...document.querySelectorAll('td, th, div, span, b')]
    .find(e => gorunur(e) && !e.children.length && duz(e) === arg.baslik.toLowerCase());
  if (!baslik) return bulunan;
  let kap = baslik.parentElement;
  while (kap && !kap.querySelector('select, input[type=text], input:not([type])') && kap.parentElement)
    kap = kap.parentElement;
  for (const etiket of arg.etiketler) {
    const aranan = etiket.toLowerCase();
    const el = [...kap.querySelectorAll('td, th, label, span, div, b')]
      .find(e => gorunur(e) && !e.children.length && duz(e) === aranan);
    if (!el) continue;
    let satir = el.closest('tr') || el.parentElement;
    const kutular = s => [...s.querySelectorAll('select, input[type=text], input:not([type])')].filter(gorunur);
    let k = kutular(satir);
    if (!k.length && satir.parentElement) { satir = satir.parentElement; k = kutular(satir); }
    k.forEach((x, i) => x.setAttribute('data-lucabot-alan', etiket + '#' + i));
    bulunan[etiket] = k.length;
  }
  return bulunan;
}"""


def alanlari_isaretle(page, baslik, etiketler, zorunlu):
    """Penceredeki alanlari isaretler; zorunlu etiketin bulundugu cerceve dondurulur, yoksa LookupError."""
    for fr in cerceveler(page):
        try:
            bulunan = fr.evaluate(ALANLAR_JS, {"baslik": baslik, "etiketler": list(etiketler)})
        except Exception:
            continue
        if bulunan.get(zorunlu):
            return fr
    raise LookupError(f"'{baslik}' penceresindeki alanlar bulunamadi")


def alan(cerceve, etiket, sira=0):
    return cerceve.locator(f'[data-lucabot-alan="{etiket}#{sira}"]')


def secenek_sec(secici, metin):
    """Select'te sadelestirilmis metni tutan secenegi secer; bulunamazsa False."""
    hedef = sadelestir(metin)
    for i, s in enumerate(secici.locator("option").all_inner_texts()):
        if sadelestir(s) == hedef:
            secici.select_option(index=i, timeout=8000)
            return True
    return False


def metin_yaz(kutu, metin):
    """Kutuyu bosaltip yazar, Tab ile onaylar; yazilan deger beklenenle ayniysa True."""
    kutu.fill(metin, timeout=5000)
    kutu.press("Tab")
    return sadelestir(kutu.input_value()) == sadelestir(metin)
