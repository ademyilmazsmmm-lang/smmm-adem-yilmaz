"""
Ana sayfadaki (index.html) İletişim bölümünü tek "doğruluk kaynağı" olarak
kullanıp, aynı iletişim bilgilerini (telefon, e-posta, adres, LinkedIn,
harita) sitedeki diğer tüm sayfalardaki "site-contact-section" bloğuna
ve WhatsApp balonuna otomatik olarak yayar.

Kullanım: python sync_contact.py
index.html içindeki #iletisim bölümünü değiştirip bu scripti çalıştırdığınızda
(veya main'e push ettiğinizde - bkz. .github/workflows/sync-contact.yml)
tüm site otomatik güncellenir.
"""
import glob
import re

SOURCE_FILE = "index.html"


def extract_contact_data(html):
    def find(pattern, label):
        m = re.search(pattern, html, re.S)
        if not m:
            print(f"UYARI: {label} bulunamadı, mevcut değer korunacak.")
            return None
        return m.group(1).strip()

    phone_href = find(r'href="tel:(\d+)"', "telefon (tel:)")
    phone_display = find(r'href="tel:\d+">\s*([^<]+?)\s*</a>', "telefon (görünen)")
    email = find(r'href="mailto:([^"]+)"', "e-posta")
    address = find(r'<strong>Adres:</strong>\s*<span>([^<]+)</span>', "adres")
    linkedin = find(r'class="linkedin-row"\s+href="([^"]+)"', "linkedin")
    map_src = find(r'<iframe src="([^"]+)"[^>]*>\s*</iframe>', "harita iframe")
    map_go = find(r'class="map-go-btn"\s+href="([^"]+)"', "konuma git linki")

    return {
        "phone_href": phone_href or "905536194134",
        "phone_display": phone_display or "0553 619 41 34",
        "email": email or "adem@smmmyilmaz.com",
        "address": address or "Ümraniye / İstanbul",
        "linkedin": linkedin or "https://www.linkedin.com/in/ademyilmazz",
        "map_src": map_src or "https://maps.google.com/maps?q=41.023735,29.093180&z=16&output=embed",
        "map_go": map_go or "https://maps.app.goo.gl/7JbYMK2JuFgPtxPL8",
    }


def build_block(d):
    tel_link = d["phone_href"] if d["phone_href"].isdigit() else d["phone_href"]
    return f'''<section class="site-contact-section" id="site-iletisim">
  <div class="container">
    <div class="section-head">
      <h2>İletişim</h2>
      <p class="subtitle">Randevu ve danışmanlık için bize ulaşın.</p>
      <div class="gold-rule"></div>
    </div>
    <div class="site-contact-grid">
      <div class="site-contact-card">
        <h3>İletişim Bilgileri</h3>
        <div class="site-contact-row">
          <div class="ico">📞</div>
          <div class="site-contact-text">
            <strong>Telefon:</strong>
            <a href="tel:{tel_link}">{d["phone_display"]}</a>
          </div>
        </div>
        <div class="site-contact-row">
          <div class="ico">✉️</div>
          <div class="site-contact-text">
            <strong>E-posta:</strong>
            <a href="mailto:{d["email"]}">{d["email"]}</a>
          </div>
        </div>
        <div class="site-contact-row">
          <div class="ico">📍</div>
          <div class="site-contact-text">
            <strong>Adres:</strong>
            <span>{d["address"]}</span>
          </div>
        </div>
        <a class="site-linkedin-row" href="{d["linkedin"]}" target="_blank" rel="noopener">
          <img src="https://cdn-icons-png.flaticon.com/512/174/174857.png" alt="LinkedIn"> Adem Yılmaz ile Bağlanın
        </a>
      </div>
      <div class="site-map-box">
        <iframe src="{d["map_src"]}" loading="lazy"></iframe>
        <a class="site-map-go-btn" href="{d["map_go"]}" target="_blank" rel="noopener">Konuma Git</a>
      </div>
    </div>
  </div>
</section>

<a class="site-whatsapp-fab" href="https://wa.me/{d["phone_href"]}" target="_blank" rel="noopener" aria-label="WhatsApp ile iletişim">
  <svg viewBox="0 0 24 24"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.435 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg>
</a>'''


FULL_BLOCK_RE = re.compile(
    r'<section class="site-contact-section".*?</section>\s*<a class="site-whatsapp-fab".*?</a>',
    re.S,
)
SECTION_ONLY_RE = re.compile(
    r'<section class="site-contact-section".*?</section>',
    re.S,
)
FAB_ONLY_RE = re.compile(
    r'<a class="site-whatsapp-fab".*?</a>',
    re.S,
)
# Bazı sayfalarda "site-" ön eksiz kendi whatsapp-fab'ı zaten var (ör. index.html
# ve birkaç sayfa); bunlara ikinci bir yüzen buton eklemeyelim.
OTHER_FAB_RE = re.compile(r'class="whatsapp-fab"')


def _append_before_body_close(content, snippet):
    if "</body>" in content:
        return content.replace("</body>", snippet + "\n</body>", 1)
    return content.replace("</html>", snippet + "\n</body>\n</html>", 1)


def sync_file(path, full_block, section_only, fab_only):
    content = open(path, encoding="utf-8").read()
    original = content

    if FULL_BLOCK_RE.search(content):
        content = FULL_BLOCK_RE.sub(lambda m: full_block, content, count=1)
        return _write_if_changed(path, original, content)

    has_section = bool(SECTION_ONLY_RE.search(content))
    has_own_fab = bool(FAB_ONLY_RE.search(content))
    has_other_fab = bool(OTHER_FAB_RE.search(content)) and not has_own_fab

    if has_section:
        content = SECTION_ONLY_RE.sub(lambda m: section_only, content, count=1)
    if has_own_fab:
        content = FAB_ONLY_RE.sub(lambda m: fab_only, content, count=1)

    if has_section and not has_own_fab and not has_other_fab:
        # Kart+harita var, hiç fab yok: bölümün hemen sonrasına ekle.
        content = SECTION_ONLY_RE.sub(lambda m: m.group(0) + "\n\n" + fab_only, content, count=1)
    elif has_own_fab and not has_section:
        # Kendi fab'ımız var ama kart yok: fab'ın hemen öncesine ekle.
        content = FAB_ONLY_RE.sub(lambda m: section_only + "\n\n" + m.group(0), content, count=1)
    elif has_other_fab and not has_section:
        # Sayfanın kendi (site- ön eksiz) fab'ı var: sadece kartı sona ekle.
        content = _append_before_body_close(content, section_only)
    elif not has_section and not has_own_fab and not has_other_fab:
        # Hiçbiri yok: ikisini birden ekle.
        content = _append_before_body_close(content, full_block)

    return _write_if_changed(path, original, content)


def _write_if_changed(path, original, content):
    if content != original:
        open(path, "w", encoding="utf-8").write(content)
        return True
    return False


def main():
    source_html = open(SOURCE_FILE, encoding="utf-8").read()
    data = extract_contact_data(source_html)

    full_block = build_block(data)
    section_only = SECTION_ONLY_RE.search(full_block).group(0)
    fab_only = FAB_ONLY_RE.search(full_block).group(0)

    changed = []
    for path in sorted(glob.glob("*.html")):
        if path == SOURCE_FILE:
            continue
        # Eski URL'leri yeni adreslerine tasiyan noindex yonlendirme sayfalari
        # sade kalmali; iletisim blogu eklenmez.
        with open(path, encoding="utf-8", errors="replace") as fh:
            if re.search(r'name=["\']robots["\'][^>]*noindex', fh.read(4000), re.I):
                continue
        if sync_file(path, full_block, section_only, fab_only):
            changed.append(path)

    print(f"Kaynak: {SOURCE_FILE}")
    print(f"Telefon: {data['phone_display']} ({data['phone_href']})")
    print(f"E-posta: {data['email']}")
    print(f"Adres: {data['address']}")
    print(f"LinkedIn: {data['linkedin']}")
    print(f"Güncellenen sayfa sayısı: {len(changed)}")
    for f in changed:
        print(f"  - {f}")


if __name__ == "__main__":
    main()
