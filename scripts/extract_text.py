#!/usr/bin/env python3
"""Print the plain text of a resume or job-description file, plus the links hidden in it.

Usage: python extract_text.py <path>      (.pdf, .docx, .txt, .md, .html)

The text goes to stdout. After it comes a "links found in the file" list (a resume's LinkedIn word usually hides its URL in
the file's link data, not in the text). Page size and page count of a PDF go to stderr.
Old .doc, .rtf and unknown types are refused with a message. Exit code 1 with a message on stderr when nothing could be read.
"""
import codecs
import html
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BULLET = chr(0x2022)
TEXT_TYPES = ("", ".txt", ".md", ".markdown", ".text", ".log")


def decode_text(raw):
    """Notepad's 'Unicode' (UTF-16), UTF-8 with or without a BOM, and Windows-1252 all turn up in saved files."""
    if raw.startswith(codecs.BOM_UTF8):
        return raw.decode("utf-8-sig")
    if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return raw.decode("utf-16")
    half = len(raw) // 2
    if half > 8 and raw[1::2].count(0) > half * 0.8:
        return raw.decode("utf-16-le", errors="replace")
    if half > 8 and raw[0::2].count(0) > half * 0.8:
        return raw.decode("utf-16-be", errors="replace")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def tidy(text):
    text = text.replace(chr(0x7F), BULLET).replace("\x00", "")
    text = re.sub(r"\(cid:\d+\)", BULLET, text)
    return text


def page_kind(w, h):
    for name, (pw, ph) in {"A4": (595.3, 841.9), "Letter": (612.0, 792.0)}.items():
        if abs(w - pw) < 3 and abs(h - ph) < 3:
            return name
    return f"{w:.0f}x{h:.0f} pt"


def pdf_links_raw(data):
    return sorted({m.decode("latin-1") for m in re.findall(rb"/URI\s*\(([^)]*)\)", data)})


def from_pdf(path):
    links = []
    text = ""
    if not os.environ.get("RESUME_TAILOR_NO_PYPDF"):
        try:
            from pypdf import PdfReader
        except ImportError:
            PdfReader = None
        if PdfReader is not None:
            rd = PdfReader(str(path))
            text = "\n\n".join((p.extract_text() or "") for p in rd.pages)
            box = rd.pages[0].mediabox
            print(f"info: {len(rd.pages)} page(s), page size {page_kind(float(box.width), float(box.height))}", file=sys.stderr)
            for p in rd.pages:
                for a in p.get("/Annots") or []:
                    uri = ((a.get_object().get("/A") or {}).get("/URI"))
                    if uri:
                        links.append(str(uri))
    if len(text.strip()) < 50:
        exe = shutil.which("pdftotext")
        if exe:
            text = subprocess.run([exe, "-enc", "UTF-8", "-eol", "unix", "-layout", str(path), "-"], capture_output=True,
                                  text=True, encoding="utf-8", errors="replace").stdout
            links = links or pdf_links_raw(Path(path).read_bytes())
        elif not text:
            sys.exit("Cannot read PDFs here (no pypdf and no pdftotext). Read the file with your own file tools, "
                     "or run: python -m pip install pypdf")
    if len(text.strip()) < 50:
        sys.exit("This PDF has almost no text (probably a scan). Paste the text of the document instead.")
    return tidy(text), links


def from_docx(path):
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
            try:
                rels = z.read("word/_rels/document.xml.rels").decode("utf-8", "replace")
            except KeyError:
                rels = ""
    except (zipfile.BadZipFile, KeyError):
        sys.exit("This is not a readable .docx file. Save it again as .docx or .pdf, or paste the text.")
    links = [html.unescape(m) for m in re.findall(r'Type="[^"]*/hyperlink"[^>]*Target="([^"]+)"', rels)]
    links += [html.unescape(m) for m in re.findall(r'Target="([^"]+)"[^>]*Type="[^"]*/hyperlink"', rels)]
    xml = re.sub(r"(?s)<w:(instrText|delText)[^>]*>.*?</w:\1>", "", xml)
    xml = xml.replace("</w:tc>", "\t").replace("</w:tr>", "\n").replace("</w:p>", "\n").replace("<w:tab/>", "\t")
    xml = re.sub(r"<w:br[^>]*/>", "\n", xml)
    text = html.unescape(re.sub(r"<[^>]+>", "", xml))
    return re.sub(r"[ \t]*\t+[ \t]*\n", "\n", text), links


def strip_tags(raw):
    raw = re.sub(r"(?is)<(script|style).*?</\1>", "", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>|</div>", "\n", raw)
    return html.unescape(re.sub(r"<[^>]+>", "", raw))


def job_posting_json(raw):
    """Many job pages keep the full description only in a JSON-LD JobPosting block."""
    out = []
    for blob in re.findall(r"(?is)<script[^>]+application/ld\+json[^>]*>(.*?)</script>", raw):
        try:
            data = json.loads(blob)
        except ValueError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict) and item.get("@type") == "JobPosting" and item.get("description"):
                out.append(strip_tags(html.unescape(str(item["description"]))))
    return "\n\n".join(out)


def from_html(raw):
    text = strip_tags(raw)
    if len(text.strip()) < 300:
        text = (text + "\n\n" + job_posting_json(raw)).strip()
    links = [html.unescape(m) for m in re.findall(r'(?i)<a[^>]+href="([^"]+)"', raw)]
    return text, [u for u in links if u.startswith(("http://", "https://", "mailto:"))]


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    path = Path(sys.argv[1])
    if not path.exists():
        sys.exit(f"File not found: {path}")
    if path.is_dir():
        sys.exit(f"{path} is a folder, not a file.")
    kind, links = path.suffix.lower(), []
    if kind == ".pdf":
        text, links = from_pdf(path)
    elif kind == ".docx":
        text, links = from_docx(path)
    elif kind in (".html", ".htm"):
        text, links = from_html(decode_text(path.read_bytes()))
    elif kind in (".doc", ".rtf", ".pages", ".odt"):
        sys.exit(f"{kind} files are not supported. Save as .docx or .pdf, or paste the text.")
    elif kind in TEXT_TYPES:
        text = decode_text(path.read_bytes())
    else:
        sys.exit(f"Unsupported file type '{kind}'. Use .pdf, .docx, .txt, .md or .html, or paste the text.")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        sys.exit("No text could be read from this file. Paste the text instead.")
    print(text)
    links = [u for i, u in enumerate(links) if u and u not in links[:i]]
    if links:
        print("\n--- links found in the file ---")
        print("\n".join(links))


if __name__ == "__main__":
    main()

