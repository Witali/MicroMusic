"""Check catalog SREG masks against the pinned official instruction manual PDF."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from pypdf import PdfReader

root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--manual", required=True, type=Path)
parser.add_argument("--output", type=Path, default=root / "build/avr-sreg-manual.json")
args = parser.parse_args()
catalog_bytes = (root / "web-player/reports/attiny13a-instructions.json").read_bytes()
catalog = json.loads(catalog_bytes)
source = next(s for s in catalog["sources"] if "DS40002198A.pdf" in s["url"])
manual_sha = hashlib.sha256(args.manual.read_bytes()).hexdigest()
assert manual_sha == source["sha256"], "Manual differs from the pinned official PDF"

# CPSE's flag row straddles pages; remove only known document header/footer lines.
pages = PdfReader(args.manual).pages
lines = []
for page_number, page in enumerate(pages, 1):
    for line in page.extract_text().splitlines():
        stripped = line.strip()
        if stripped in ("AVR\u00ae Instruction Set Manual", "Instruction Description"):
            continue
        if stripped.startswith("\u00a9 2020 Microchip Technology Inc."):
            continue
        lines.append((line, page_number))
text = "\n".join(line for line, _ in lines)
pattern = re.compile(
    r"(5\.\d+)\.2\s+Status Register(?: \(SREG\))? and Boolean Formula\s+"
    r"I\s+T\s+H\s+S\s+V\s+N\s+Z\s+C\s+((?:[\u2013\u21d401]\s*){8})"
)
sections = {}
for match in pattern.finditer(text):
    cells = match[2].split()
    mask = sum(1 << (7 - i) for i, cell in enumerate(cells) if cell != "\u2013")
    page_number = lines[text.count("\n", 0, match.start())][1]
    assert match[1] not in sections, "Duplicate manual section"
    sections[match[1]] = (mask, page_number)
rows = []
for entry in catalog["instructions"]:
    section = entry["manualSection"]
    assert section in sections, "Unparsed official flag table: " + entry["form"]
    mask, page_number = sections[section]
    assert mask == entry["sregMask"], "Flag mask mismatch: " + entry["form"]
    rows.append({"form": entry["form"], "section": section, "pdfPage": page_number, "writeMask": mask})
report = {"schema": "micromusic-avr-sreg-manual-v1", "source": source["url"],
          "manualSha256": manual_sha, "catalogSha256": hashlib.sha256(catalog_bytes.replace(b"\r\n", b"\n")).hexdigest(),
          "meaning": "Union of potentially written bits; BSET/BCLR select only the decoded operand bit.",
          "rows": rows}
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"forms": len(rows), "matched": len(rows), "manualSha256": manual_sha}))
