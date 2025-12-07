import os
import datetime
import xml.etree.ElementTree as ET

BASE_URL = "https://smmmyilmaz.com"

def generate_sitemap():
    urls = []

    for root, dirs, files in os.walk("."):
        for file in files:
            if file.endswith(".html"):
                full_path = os.path.join(root, file)
                url_path = full_path.replace(".\\", "").replace("\\", "/")

                # Priority belirleme
                if "index.html" in file:
                    priority = "1.00"
                else:
                    priority = "0.85"

                # Tarih
                lastmod = datetime.datetime.now().strftime("%Y-%m-%d")

                urls.append((f"{BASE_URL}/{url_path}", lastmod, priority))

    # XML oluşturma
    urlset = ET.Element("urlset", attrib={"xmlns": "http://www.sitemaps.org/schemas/sitemap/0.9"})

    for url, lastmod, priority in urls:
        url_el = ET.SubElement(urlset, "url")

        ET.SubElement(url_el, "loc").text = url
        ET.SubElement(url_el, "lastmod").text = lastmod
        ET.SubElement(url_el, "priority").text = priority

    tree = ET.ElementTree(urlset)
    tree.write("sitemap.xml", encoding="utf-8", xml_declaration=True)

    print("✔ sitemap.xml oluşturuldu")


if __name__ == "__main__":
    generate_sitemap()
