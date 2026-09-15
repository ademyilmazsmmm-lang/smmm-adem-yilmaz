import os
import re
import datetime
import subprocess
import xml.etree.ElementTree as ET

BASE_URL = "https://smmmyilmaz.com"

# Ana sayfa canonical'i "https://smmmyilmaz.com/" oldugu icin sitemap de ayni URL'i vermeli.
HOMEPAGE = "index.html"

# Oncelik kademeleri: ana sayfa > hub/hizmet sayfalari > icerik sayfalari
HIGH_PRIORITY = {
    "hesaplama.html", "iletisim.html", "il.html", "hizmetler.html",
    "sektorlere-ozel-muhasebe.html", "pratik-bilgiler.html",
}


def git_lastmod(path, fallback):
    """Dosyanin son commit tarihi. Her calistirmada tum tarihleri bugune cekmek,
    Google'in lastmod sinyaline guvenini azaltir."""
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%cs", "--", path],
            capture_output=True, text=True, timeout=10,
        )
        d = out.stdout.strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
            return d
    except Exception:
        pass
    return fallback


def is_noindex(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            head = fh.read(4000)
    except OSError:
        return False
    return re.search(r'<meta[^>]+name=["\']robots["\'][^>]*noindex', head, re.I) is not None


def generate_sitemap():
    urls = []
    today = datetime.date.today().isoformat()

    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in (".git", ".github", "node_modules")]
        for file in sorted(files):
            if not file.endswith(".html"):
                continue

            full_path = os.path.join(root, file)
            url_path = os.path.relpath(full_path, ".").replace("\\", "/")

            # noindex sayfalari (eski URL yonlendirmeleri) sitemap'e girmez
            if is_noindex(full_path):
                continue

            if url_path == HOMEPAGE:
                loc, priority = f"{BASE_URL}/", "1.00"
            elif url_path in HIGH_PRIORITY:
                loc, priority = f"{BASE_URL}/{url_path}", "0.90"
            else:
                loc, priority = f"{BASE_URL}/{url_path}", "0.80"

            urls.append((loc, git_lastmod(url_path, today), priority))

    urls.sort(key=lambda u: (u[2] != "1.00", u[0]))

    urlset = ET.Element(
        "urlset",
        attrib={"xmlns": "http://www.sitemaps.org/schemas/sitemap/0.9"},
    )
    for url, lastmod, priority in urls:
        url_el = ET.SubElement(urlset, "url")
        ET.SubElement(url_el, "loc").text = url
        ET.SubElement(url_el, "lastmod").text = lastmod
        ET.SubElement(url_el, "priority").text = priority

    ET.indent(urlset, space="  ")
    ET.ElementTree(urlset).write("sitemap.xml", encoding="utf-8", xml_declaration=True)
    print(f"✔ sitemap.xml olusturuldu ({len(urls)} URL)")


if __name__ == "__main__":
    generate_sitemap()
