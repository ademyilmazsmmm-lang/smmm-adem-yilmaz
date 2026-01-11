import os
import datetime
import xml.etree.ElementTree as ET

BASE_URL = "https://smmmyilmaz.com"

def generate_sitemap():
    urls = []
    today = datetime.date.today().isoformat()

    for root, dirs, files in os.walk("."):
        for file in files:
            if not file.endswith(".html"):
                continue

            full_path = os.path.join(root, file)

            # ./ ve \ temizliği (kritik)
            url_path = os.path.relpath(full_path, ".")
            url_path = url_path.replace("\\", "/")

            # index.html ana sayfa
            if url_path == "index.html":
                priority = "1.00"
            else:
                priority = "0.85"

            urls.append((f"{BASE_URL}/{url_path}", today, priority))

    urlset = ET.Element(
        "urlset",
        attrib={"xmlns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    )

    for url, lastmod, priority in urls:
        url_el = ET.SubElement(urlset, "url")
        ET.SubElement(url_el, "loc").text = url
        ET.SubElement(url_el, "lastmod").text = lastmod
        ET.SubElement(url_el, "priority").text = priority

    tree = ET.ElementTree(urlset)
    tree.write("sitemap.xml", encoding="utf-8", xml_declaration=True)

    print("✔ SEO-uyumlu sitemap.xml oluşturuldu")

if __name__ == "__main__":
    generate_sitemap()
