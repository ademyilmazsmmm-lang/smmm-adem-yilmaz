from bs4 import BeautifulSoup
import os
import csv
import requests

def analyze_html(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    # SEO alanları
    title = soup.title.string if soup.title else ""
    description = soup.find("meta", attrs={"name": "description"})
    description = description["content"] if description else ""

    h1_tag = soup.find("h1")
    h1 = h1_tag.text.strip() if h1_tag else ""

    # Alt text eksik görseller
    images = soup.find_all("img")
    missing_alt = sum(1 for img in images if not img.get("alt"))

    # İç link sayısı
    links = soup.find_all("a")
    internal_links = [a["href"] for a in links if a.get("href", "").startswith("/")]

    # Kelime uzunluğu
    text = soup.get_text(" ", strip=True)
    word_count = len(text.split())

    return {
        "file": file_path,
        "title": title,
        "meta_description": description,
        "h1": h1,
        "missing_alt": missing_alt,
        "internal_links": len(internal_links),
        "word_count": word_count
    }


def generate_report():
    results = []

    for root, dirs, files in os.walk("."):
        for file in files:
            if file.endswith(".html"):
                path = os.path.join(root, file)
                results.append(analyze_html(path))

    # CSV oluştur
    with open("seo_report.csv", "w", newline="", encoding="utf-8") as csvfile:
        fieldnames = ["file", "title", "meta_description", "h1", "missing_alt", "internal_links", "word_count"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print("✔ SEO raporu oluşturuldu → seo_report.csv")


if __name__ == "__main__":
    generate_report()
