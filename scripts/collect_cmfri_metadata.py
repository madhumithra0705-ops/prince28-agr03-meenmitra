import csv
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

LISTING = "https://eprints.cmfri.org.in/view/doctype/article.html"
CSV_PATH = Path("data/sources.csv")
LIMIT = 300


class AnchorParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.current_href = None
        self.current_text = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self.current_href = dict(attrs).get("href")
            self.current_text = []

    def handle_data(self, data):
        if self.current_href is not None:
            self.current_text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.current_href is not None:
            self.links.append((self.current_href, " ".join(self.current_text).strip()))
            self.current_href = None
            self.current_text = []


headers = {"User-Agent": "examate-student-bot/0.1"}
with httpx.Client(headers=headers, timeout=30, follow_redirects=True) as client:
    response = client.get(LISTING)
    response.raise_for_status()

parser = AnchorParser()
parser.feed(response.text)

items = []
seen = set()

for href, title in parser.links:
    url = urljoin(LISTING, href)
    parsed = urlparse(url)
    match = re.fullmatch(r"/(\d+)/?", parsed.path)

    if parsed.hostname != "eprints.cmfri.org.in" or not match:
        continue

    item_id = match.group(1)
    clean_url = f"https://eprints.cmfri.org.in/{item_id}/"

    if clean_url not in seen:
        seen.add(clean_url)
        items.append(
            {
                "url": clean_url,
                "source": "cmfri",
                "licence": (
                    "Metadata only: CMFRI Repository Policy permits metadata "
                    "harvesting and reuse with attribution to Eprints@CMFRI; "
                    "this does not grant rights to reuse full-text content."
                ),
                "title": title or f"CMFRI item {item_id}",
            }
        )

if not CSV_PATH.exists():
    raise SystemExit("ERROR: data/sources.csv not found.")

with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    fields = ["url", "source", "licence", "title"]
    if reader.fieldnames != fields:
        raise SystemExit(f"ERROR: Unexpected CSV header: {reader.fieldnames}")
    existing = list(reader)

existing_urls = {row["url"] for row in existing}
new_items = [item for item in items if item["url"] not in existing_urls][:LIMIT]

if not new_items:
    print("No new CMFRI metadata URLs to add.")
else:
    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(existing)
        writer.writerows(new_items)

print("Public CMFRI item pages found:", len(items))
print("New metadata URLs added:", len(new_items))
print("Total CSV rows:", len(existing) + len(new_items))
