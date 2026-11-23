#!/usr/bin/env python3
"""Render a tailored resume (1 or 2 pages) from a profile and a job spec, and check it.

Usage:
  python build_resume.py check-profile profile.json
  python build_resume.py build profile.json spec.json out.pdf [--pages 1|2] [--proof] [--no-tune] [--strict-fill]

The profile holds the person's facts, taken from their own resume. The spec holds the content tailored to one job.
Every fact on the page has to come from the profile; the checks flag anything that is not in it.
Needs Python 3.8+ and reportlab (python -m pip install reportlab). Always prints a report: fix every FAIL, and every
WARN you can fix without inventing anything.

Exit code 0: no FAIL, the PDF is written. 2: the report has a FAIL, nothing is written to out.pdf (a draft is saved as
out.FAILED.pdf). 1: an input file is missing or invalid.
"""
import argparse
import datetime
import difflib
import html
import io
import json
import math
import re
import sys
from pathlib import Path

try:
    from reportlab.lib.colors import Color
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes import A4, letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas
    from reportlab.platypus import Flowable, Paragraph, Table, TableStyle
except ImportError:
    sys.exit("reportlab is not installed. Run: python -m pip install reportlab")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BULLET = chr(0x2022)
SAFE_SWAPS = {chr(0x2010): "-", chr(0x2011): "-", chr(0x2212): "-", chr(0x2009): " ", chr(0x200A): " ", chr(0x202F): " ",
              chr(0x2002): " ", chr(0x2003): " ", chr(0xA0): " ", chr(0x200B): "", chr(0x200C): "", chr(0x200D): "",
              chr(0xFEFF): "", chr(0xAD): "", "\t": " ", "\n": " ", "\r": " "}

PAGE_SIZES = {"A4": A4, "Letter": letter}
ML = MR = 0.55 * 72
MT = MB = 0.5 * 72
GEO = {}
LAYOUT = {"label_w": 85.0}
CTX = {"years": None}
SPACING = {"section_before": 10, "section_after": 5, "bullet_gap": 3.5, "list_end": 6, "skill_gap": 3}
FILL_LO, FILL_HI = 94, 98
TARGET = (FILL_LO + FILL_HI) / 2.0
S_MIN, S_MAX = 0.5, 2.0
S_OK_LO, S_OK_HI = 0.8, 1.9


def set_page(name):
    w, h = PAGE_SIZES[name]
    GEO.update(name=name, w=w, h=h, text_w=w - ML - MR, frame_h=h - MT - MB)


set_page("A4")

INK = Color(0.08, 0.08, 0.08)
GREY = Color(0.3, 0.3, 0.3)
RULE = Color(0.83, 0.83, 0.83)

DEFAULT_TITLES = {"summary": "SUMMARY", "skills": "SKILLS", "experience": "PROFESSIONAL EXPERIENCE", "projects": "PROJECTS",
                  "education": "EDUCATION", "certifications": "CERTIFICATIONS", "awards": "AWARDS"}
DEFAULT_ORDER = ["summary", "skills", "experience", "projects", "education", "certifications", "awards", "extra"]
OMITTABLE = ("summary", "skills", "projects", "certifications", "awards", "extra")
COMMON_WORDS = ["Summary", "Skills", "Technical", "Professional", "Experience", "Projects", "Education", "Awards",
                "Certifications", "Years", "Tech", "Engineer", "Developer", "Software", "Backend", "Frontend", "Full", "Stack",
                "Data", "Analyst", "Designer", "Consultant", "Specialist"]
LEAD_WORDS = {"led", "lead", "leads", "leading", "managed", "manage", "managing", "mentored", "mentoring", "mentor",
              "supervised", "supervising", "headed", "directed", "spearheaded", "coached", "recruited", "hired"}
SENIORITY_WORDS = {"senior", "principal", "staff", "architect", "manager", "head", "director", "chief"}

NUM_TOKEN = re.compile(r"(?<![A-Za-z0-9.\-/])(\d+(?:\.\d+)?)([kKmMbB]?)(%?)(\+?)(?![A-Za-z0-9])")
WORD = re.compile(r"[A-Za-z][A-Za-z0-9+#.]*(?:-[A-Za-z0-9+#.]+)*")
SPELLED = re.compile(r"\b(?:two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|"
                     r"seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|"
                     r"million|billion|dozen)\b", re.I)
YEARS_RE = re.compile(r"(?:(?<![\w.])(\d+(?:\.\d+)?)|\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
                      r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty))\s*(?:\+|plus)?[\s-]*"
                      r"(?:years?|yrs?)\b|\b(?:a|one|two|three|half a|several)\s+decades?\b|\bdecades? of\b", re.I)
CLAUSE_END = r"[.;:()\[\]\n,]"
STOP = {"a", "an", "and", "the", "of", "in", "on", "for", "to", "with", "by", "across", "per", "as", "at", "from", "into",
        "over", "using", "via", "or", "than", "that", "this", "its", "their", "our", "up", "is", "are", "was", "be"}


# ------------------------------------------------------------------ text helpers
def is_text(v):
    return isinstance(v, str) and v.strip() != ""


def total_years(profile):
    cs = profile.get("career_start")
    if not cs:
        return None
    y, m = (int(v) for v in cs.split("-"))
    t = datetime.date.today()
    return (((t.year - y) * 12 + (t.month - m)) // 6) / 2


def years_str(profile):
    ty = total_years(profile)
    return None if ty is None else f"{ty:g}+"


def fill_years(text):
    return text.replace("{YEARS}", CTX["years"]) if CTX.get("years") else text


def plain(text):
    return re.sub(r"\*", "", fill_years(text))


def markup(text):
    t = fill_years(text)
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", t)
    return t


def esc(s):
    return html.escape(s, quote=True)


def clean(s):
    for a, b in SAFE_SWAPS.items():
        s = s.replace(a, b)
    return s


def normalise(v):
    if isinstance(v, str):
        return clean(v)
    if isinstance(v, list):
        return [normalise(x) for x in v]
    if isinstance(v, dict):
        return {k: normalise(x) for k, x in v.items()}
    return v


UNREADABLE = object()


def load_json(path, what):
    """The parsed JSON, or UNREADABLE after printing why (a file holding just null is valid JSON, so None cannot mean failure)."""
    p = Path(path)
    if not p.is_file():
        print(f"FAIL {what}: file not found: {path}")
        return UNREADABLE
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except ValueError as e:
        print(f"FAIL {what}: {path} is not valid JSON: {e}")
        return UNREADABLE


# ------------------------------------------------------------------------- styles
def style(name, size, leading, bold=False, italic=False, align=0, color=INK, **kw):
    font = "Helvetica-BoldOblique" if bold and italic else "Helvetica-Bold" if bold else "Helvetica-Oblique" if italic else "Helvetica"
    return ParagraphStyle(name, fontName=font, fontSize=size, leading=leading, alignment=align, textColor=color, **kw)


S_NAME = style("name", 24.88, 30, bold=True, align=TA_CENTER)
S_HEAD = style("head", 11, 13.6, align=TA_CENTER)
S_SMALL_C = style("smallc", 10, 12, align=TA_CENTER)
S_BODY = style("body", 11, 13.6)
S_SMALL = style("small", 10, 12)
S_BULLET = style("bullet", 10, 12, leftIndent=14, bulletIndent=5.5, bulletFontName="Helvetica", bulletFontSize=10)
S_LABEL = style("label", 10, 12, bold=True)
S_RIGHT = style("right", 10, 12, align=TA_RIGHT, color=GREY)


class SectionHeading(Flowable):
    def __init__(self, title):
        super().__init__()
        self.title = title
        self.proof = title

    def wrap(self, aw, ah):
        self.aw = aw
        return aw, 18.0

    def draw(self):
        c = self.canv
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(0, 6.2, self.title)
        c.setStrokeColor(RULE)
        c.setLineWidth(1.5)
        c.line(0, 1.5, self.aw, 1.5)


def plain_table(rows, widths):
    t = Table(rows, colWidths=widths)
    t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                           ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return t


def two_col(left_para, right_text):
    rw = stringWidth(plain(right_text), S_RIGHT.fontName, S_RIGHT.fontSize) + 4
    return plain_table([[left_para, Paragraph(markup(right_text), S_RIGHT)]], [GEO["text_w"] - rw, rw])


def role_flow(r, cont=False):
    tail = ' <font color="#4d4d4d">(continued)</font>' if cont else ""
    left = Paragraph(f"<b>{markup(r['title'])}</b> | <b>{markup(r['company'])}</b>{tail}", S_BODY)
    right = "  |  ".join(x for x in (r.get("location"), r["dates"]) if x)
    t = two_col(left, right)
    t.proof = f"{r['title']} | {r['company']}   {right}" + (" (continued)" if cont else "")
    return t


def project_flow(p, cont=False):
    desc = f" ({markup(p['descriptor'])})" if p.get("descriptor") else ""
    ctx = f" | <i>{markup(p['context'])}</i>" if p.get("context") else ""
    tail = ' <font color="#4d4d4d">(continued)</font>' if cont else ""
    left = Paragraph(f"<b>{markup(p['name'])}</b>{desc}{ctx}{tail}", S_BODY)
    t = two_col(left, p.get("dates", ""))
    t.proof = f"{p['name']}{' (' + p['descriptor'] + ')' if p.get('descriptor') else ''}{' | ' + p['context'] if p.get('context') else ''}" + (" (continued)" if cont else "")
    return t


def skill_row(label, text):
    lab, txt = Paragraph(markup(label), S_LABEL), Paragraph(markup(text), S_SMALL)
    t = plain_table([[lab, txt]], [LAYOUT["label_w"], GEO["text_w"] - LAYOUT["label_w"]])
    t.label_para, t.text_para = lab, txt
    t.proof = f"{label} {text}"
    return t


def bullet(text):
    return Paragraph(markup(text), S_BULLET, bulletText=BULLET)


def edu_flow(e):
    second = f"<i>{markup(e['degree'])}</i>" + (f" | {markup(e['details'])}" if e.get("details") else "")
    t = plain_table([[Paragraph(f"<b>{markup(e['institution'])}</b>", S_BODY), Paragraph(markup(e.get("dates", "")), S_RIGHT)],
                     [Paragraph(second, S_BODY), Paragraph(markup(e.get("place", "")), S_RIGHT)]], [GEO["text_w"] - 150, 150])
    t.proof = f"{e['institution']}   {e.get('dates', '')}\n{e['degree']}{' | ' + e['details'] if e.get('details') else ''}   {e.get('place', '')}"
    return t


def contact_line(profile):
    c = profile.get("contact", {})
    parts = []
    if c.get("phone"):
        parts.append(f"Mobile: {markup(c['phone'])}")
    parts.append(f'Email: <a href="mailto:{esc(c["email"])}">{markup(c["email"])}</a>')
    for label, url in (profile.get("links") or {}).items():
        parts.append(f'<a href="{esc(url)}"><u>{markup(label)}</u></a>')
    if c.get("location"):
        parts.append(markup(c["location"]))
    return "  |  ".join(parts)


# -------------------------------------------------------------------------- facts
def fact_strings(p):
    """Every string of the person's own facts that may be reused (contact, links and settings are not facts)."""
    out = [p.get("headline", ""), p.get("summary", "")]
    for r in p.get("experience", []):
        out += [r["title"], r["company"], r.get("location", ""), r["dates"], *r["bullets"]]
    for q in p.get("projects", []):
        out += [q["name"], q.get("descriptor", ""), q.get("context", ""), q.get("dates", ""), *q["bullets"]]
    for e in p.get("education", []):
        out += [e["institution"], e["degree"], e.get("dates", ""), e.get("place", ""), e.get("details", "")]
    for s in p.get("skills", []):
        out += [s["label"], s["text"]]
    out += list(p.get("certifications", [])) + list(p.get("awards", []))
    for x in p.get("extra_sections", []):
        out += [x["title"], *x["bullets"]]
    return [s for s in out if s]


def _stem(w):
    w = re.sub(r"[^a-z0-9]", "", w.lower())
    return (w[:-1] if w.endswith("s") else w)[:6]


def _content_words(seg):
    return [w for w in re.findall(r"[A-Za-z][A-Za-z0-9+#.\-]*", seg) if w.lower() not in STOP]


def _after(text, end):
    seg = re.split(CLAUSE_END, text[end:end + 90], maxsplit=1)[0]
    return {_stem(w) for w in _content_words(seg)[:3]}


def _before(text, start):
    seg = re.split(CLAUSE_END, text[max(0, start - 60):start])[-1]
    return {_stem(w) for w in _content_words(seg)[-2:]}


def _key(m):
    return m.group(1) + m.group(2).lower() + m.group(3)


class Facts:
    def __init__(self, profile):
        self.profile = profile
        self.strings = fact_strings(profile)
        self.text = "\n".join(self.strings)
        self.tokens = {t.lower().rstrip(".") for t in WORD.findall(self.text)}
        for term in list(profile.get("known_terms", [])) + COMMON_WORDS:
            self.tokens |= {t.lower().rstrip(".") for t in WORD.findall(term)}
        self.words = {w.lower() for w in re.findall(r"[A-Za-z]+", self.text)}
        self.num_index = {}
        for m in NUM_TOKEN.finditer(self.text):
            self.num_index.setdefault(_key(m), set()).update(_after(self.text, m.end()) | _before(self.text, m.start()))
        self.total = total_years(profile)
        self.year_values = {float(m.group(1)) for m in YEARS_RE.finditer(self.text) if m.group(1)}


def never_hits(text, profile):
    hits = []
    for raw in profile.get("never_claim", []):
        term = raw.strip()
        if not term:
            continue
        flags, tail = re.I, r"(?:e?s)?\d*"
        if term.startswith("="):
            term, flags, tail = term[1:], 0, ""
        if re.search(r"(?<![A-Za-z0-9])" + re.escape(term) + tail + r"(?![A-Za-z0-9])", text, flags):
            hits.append(term)
    return hits


def years_claims(text, facts):
    """Years-of-experience style claims that are neither the real total nor a phrase already in the resume."""
    low, out = facts.text.lower(), []
    for m in YEARS_RE.finditer(text):
        phrase = re.sub(r"\s+", " ", m.group(0).strip())
        if m.group(1) is not None:
            v = float(m.group(1))
            if (facts.total is not None and abs(v - facts.total) <= 0.01) or v in facts.year_values:
                continue
        if phrase.lower() in low:
            continue
        out.append(phrase)
    return out


def scrub_contact(text):
    t = re.sub(r"https?://\S+|\S+@\S+", " ", text)
    return re.sub(r"\+?\d[\d\- ]{8,}\d", " ", t)


def join_wraps(text):
    """A single newline inside a paragraph is a line wrap, not the end of a clause (blank lines and bullets still are)."""
    return re.sub(r"\n(?![\n" + BULLET + "])", " ", text.replace("\r", ""))


def unverified_numbers(text, facts):
    """Numbers that are not in the facts, or are used for something the facts do not say (and spelled-out numbers)."""
    text = join_wraps(scrub_contact(text))
    allowed = f"{facts.total:g}" if facts.total is not None else None
    found = []
    for m in NUM_TOKEN.finditer(text):
        key = _key(m)
        if key == allowed:
            continue
        if key not in facts.num_index:
            found.append(m.group(0))
        elif not re.fullmatch(r"(?:19|20)\d\d", key):
            have = _after(text, m.end()) or _before(text, m.start())
            if have and facts.num_index[key] and not (have & facts.num_index[key]):
                found.append(m.group(0))
    low = facts.text.lower()
    for m in SPELLED.finditer(text):
        nxt = re.match(r"\s+([A-Za-z]+)", text[m.end():])
        if ((m.group(0) + " " + nxt.group(1)) if nxt else m.group(0)).lower() not in low:
            found.append(m.group(0))
    return sorted(set(found))


def unverified_terms(text, facts):
    """Capitalised words in mid-sentence that the person's resume does not contain."""
    known_s = {k[:-1] if k.endswith("s") else k for k in facts.tokens}
    found = set()
    for line in join_wraps(text).splitlines():
        for m in WORD.finditer(line):
            tok = m.group(0).rstrip(".")
            before = line[:m.start()].rstrip()
            if before == "" or before.endswith((".", BULLET)):
                continue
            low = tok.lower()
            ls = low[:-1] if low.endswith("s") else low
            if any(ch.isupper() for ch in tok) and low not in facts.tokens and ls not in known_s:
                found.add(tok)
    return sorted(found)


def word_claims(text, facts, words):
    return sorted(({w.lower() for w in re.findall(r"[A-Za-z]+", text)} & words) - facts.words)


def similar_bullets(bullets):
    out = []
    for i in range(len(bullets)):
        for j in range(i + 1, len(bullets)):
            (la, a), (lb, b) = bullets[i], bullets[j]
            if la != lb and difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio() >= 0.82:
                out.append(f"'{a[:32]}...' ~ '{b[:32]}...'")
    return out


def unsupported_chars(strings):
    bad = []
    for name, t in strings:
        for ch in sorted(set(t)):
            try:
                ch.encode("cp1252")
            except UnicodeEncodeError:
                bad.append(f"{ch} (U+{ord(ch):04X}) in {name}")
    return bad


# ---------------------------------------------------------------------- validation
PROFILE_KEYS = {"name", "headline", "summary", "contact", "links", "career_start", "page_size", "show_years", "experience",
                "projects", "education", "skills", "certifications", "awards", "extra_sections", "section_order",
                "section_titles", "known_terms", "never_claim", "notes", "source"}
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def check_obj(errs, where, obj, required, optional=(), bullets=False):
    """Check one object of the profile: required text keys, optional text keys, and (if wanted) a bullets list."""
    if not isinstance(obj, dict):
        errs.append(f"{where} must be an object")
        return False
    allowed = list(required) + list(optional) + (["bullets"] if bullets else [])
    for k in required:
        if not is_text(obj.get(k)):
            errs.append(f"{where} needs a non-empty '{k}'")
    for k in obj:
        if k not in allowed:
            errs.append(f"{where} has an unknown key '{k}' (allowed: {', '.join(allowed)})")
    for k in optional:
        if k in obj and not isinstance(obj[k], str):
            errs.append(f"{where}.{k} must be a string")
    if bullets:
        b = obj.get("bullets")
        if not (isinstance(b, list) and b and all(is_text(x) for x in b)):
            errs.append(f"{where}.bullets must be a non-empty list of strings (a list, not one string)")
    return True


def validate_profile(p):
    """Returns (errors, warnings) for a profile; errors stop the build."""
    errs, warns = [], []
    if not isinstance(p, dict):
        return ["the profile must be a JSON object ({...}) at the top level"], warns
    errs += [f"unknown top-level key '{k}'" for k in p if k not in PROFILE_KEYS]
    if not is_text(p.get("name")):
        errs.append("profile needs a non-empty 'name'")
    c = p.get("contact")
    if not isinstance(c, dict):
        errs.append("profile needs a 'contact' object with at least an 'email'")
    else:
        errs += [f"contact has an unknown key '{k}' (allowed: phone, email, location)" for k in c if k not in ("phone", "email", "location")]
        if not (isinstance(c.get("email"), str) and "@" in c["email"]):
            errs.append("contact.email must be an email address")
        for k in ("phone", "location"):
            if k in c and not isinstance(c[k], str):
                errs.append(f"contact.{k} must be a string")
        if not c.get("phone"):
            warns.append("no phone number in contact (most recruiters expect one)")
    links = p.get("links", {})
    if not isinstance(links, dict) or not all(is_text(k) and isinstance(v, str) and re.match(r"^https?://", v) for k, v in links.items()):
        errs.append("links must be an object of label -> full URL starting with http:// or https://, for example {\"LinkedIn\": \"https://...\"}")
    cs = p.get("career_start")
    if cs is not None and not (isinstance(cs, str) and re.match(r"^\d{4}-(0[1-9]|1[0-2])$", cs)):
        errs.append("career_start must look like 2019-06 (year-month of the first job)")
    if "page_size" in p and p["page_size"] not in PAGE_SIZES:
        errs.append(f"page_size must be one of {list(PAGE_SIZES)}")
    if "show_years" in p and not isinstance(p["show_years"], bool):
        errs.append("show_years must be true or false")
    for key in ("headline", "summary", "notes"):
        if key in p and not isinstance(p[key], str):
            errs.append(f"{key} must be a string")
    for key, req, opt, bl in (("experience", ("id", "title", "company", "dates"), ("location",), True),
                              ("projects", ("id", "name"), ("descriptor", "context", "dates"), True),
                              ("education", ("institution", "degree"), ("dates", "place", "details"), False)):
        lst = p.get(key, [])
        if not isinstance(lst, list):
            errs.append(f"{key} must be a list")
            continue
        seen = set()
        for i, item in enumerate(lst, 1):
            if check_obj(errs, f"{key}[{i}]", item, req, opt, bl) and "id" in req:
                if is_text(item.get("id")) and not ID_RE.match(item["id"]):
                    errs.append(f"{key}[{i}].id must use letters, digits, - or _ only")
                if item.get("id") in seen:
                    errs.append(f"{key}[{i}].id '{item.get('id')}' is used twice")
                seen.add(item.get("id"))
    sk = p.get("skills", [])
    if not isinstance(sk, list):
        errs.append("skills must be a list of {label, text} objects")
    else:
        for i, row in enumerate(sk, 1):
            check_obj(errs, f"skills[{i}]", row, ("label", "text"))
    for key in ("certifications", "awards"):
        v = p.get(key, [])
        if not (isinstance(v, list) and all(is_text(x) for x in v)):
            errs.append(f"{key} must be a list of strings")
    ex = p.get("extra_sections", [])
    if not isinstance(ex, list):
        errs.append("extra_sections must be a list")
    else:
        for i, x in enumerate(ex, 1):
            check_obj(errs, f"extra_sections[{i}]", x, ("title",), (), True)
    so = p.get("section_order")
    if so is not None and not (isinstance(so, list) and so and all(k in DEFAULT_ORDER for k in so) and len(set(so)) == len(so)):
        errs.append(f"section_order must be a list of unique names from {DEFAULT_ORDER}")
    st = p.get("section_titles")
    if st is not None and not (isinstance(st, dict) and all(k in DEFAULT_TITLES and is_text(v) for k, v in st.items())):
        errs.append(f"section_titles must map names from {list(DEFAULT_TITLES)} to text")
    for key in ("known_terms", "never_claim"):
        if key in p and not (isinstance(p[key], list) and all(is_text(x) for x in p[key])):
            errs.append(f"{key} must be a list of strings")
    if errs:
        return errs, warns
    roles = p.get("experience", [])
    starts = [(re.findall(r"\b((?:19|20)\d\d)\b", r["dates"]) or [None])[0] for r in roles]
    starts = [int(s) if s else None for s in starts]
    for i in range(len(roles) - 1):
        if starts[i] is not None and starts[i + 1] is not None and starts[i] < starts[i + 1]:
            warns.append(f"roles must be newest first: '{roles[i]['id']}' starts in {starts[i]} but the next role '{roles[i + 1]['id']}' starts in {starts[i + 1]}")
    known = [s for s in starts if s is not None]
    if p.get("career_start") and known and abs(min(known) - int(p["career_start"][:4])) > 1:
        warns.append(f"career_start {p['career_start']} does not match the earliest role (starts in {min(known)}); the years on the resume come from career_start")
    if p.get("experience") and not p.get("career_start"):
        warns.append("career_start is not set, so {YEARS} and the years check cannot be used (set it to the first job's start, like 2019-06)")
    if not (p.get("experience") or p.get("projects")):
        warns.append("the profile has no experience and no projects, so the resume would have little to show")
    return errs, warns


def validate_spec(spec, profile):
    if not isinstance(spec, dict):
        return ["the spec must be a JSON object ({...}) at the top level"]
    errs = [f"unknown top-level key '{k}' (allowed: job, header, summary, skills, experience, projects, omit_sections, pages)"
            for k in spec if k not in ("job", "header", "summary", "skills", "experience", "projects", "omit_sections", "pages")]
    h = spec.get("header")
    if not isinstance(h, dict):
        errs.append("spec needs a 'header' object with 'headline'")
    else:
        errs += [f"header has an unknown key '{k}'" for k in h if k not in ("headline", "keywords", "show_years")]
        if not is_text(h.get("headline")):
            errs.append("header.headline must be a non-empty string")
        kw = h.get("keywords", [])
        if not (isinstance(kw, list) and all(is_text(x) for x in kw)):
            errs.append("header.keywords must be a list of strings (a list, not one string)")
        if "show_years" in h and not isinstance(h["show_years"], bool):
            errs.append("header.show_years must be true or false")
    if "summary" in spec and not is_text(spec["summary"]):
        errs.append("'summary' must be a non-empty string (leave the key out for no summary)")
    sk = spec.get("skills", [])
    if not isinstance(sk, list):
        errs.append("'skills' must be a list of {\"label\": ..., \"text\": ...} objects")
    else:
        for i, row in enumerate(sk, 1):
            if not (isinstance(row, dict) and is_text(row.get("label")) and is_text(row.get("text"))):
                errs.append(f"skills row {i} must be an object with non-empty 'label' and 'text' strings")
    for key, owner in (("experience", "experience"), ("projects", "projects")):
        lst = spec.get(key, [])
        have = {x["id"] for x in profile.get(owner, [])}
        if not isinstance(lst, list):
            errs.append(f"'{key}' must be a list of {{\"id\": ..., \"bullets\": [...]}} objects")
            continue
        seen = set()
        for i, item in enumerate(lst, 1):
            if not (isinstance(item, dict) and set(item) == {"id", "bullets"} and isinstance(item["bullets"], list)
                    and item["bullets"] and all(is_text(b) for b in item["bullets"])):
                errs.append(f"{key}[{i}] must be {{\"id\": ..., \"bullets\": [non-empty strings]}} (bullets is a list, not one string)")
                continue
            if item["id"] not in have:
                errs.append(f"{key}[{i}].id '{item['id']}' is not in the profile (ids: {sorted(have)})")
            if item["id"] in seen:
                errs.append(f"{key}[{i}].id '{item['id']}' is used twice")
            seen.add(item["id"])
        if key == "experience" and profile.get("experience") and not lst:
            errs.append("'experience' must list at least one role from the profile")
    om = spec.get("omit_sections", [])
    if not (isinstance(om, list) and all(x in OMITTABLE for x in om)):
        errs.append(f"omit_sections must be a list of names from {list(OMITTABLE)}")
    if "pages" in spec and spec["pages"] not in (1, 2):
        errs.append("pages must be 1 or 2")
    if "job" in spec and not isinstance(spec["job"], dict):
        errs.append("'job' must be an object like {\"company\": ..., \"role\": ...}")
    if "{YEARS}" in json.dumps(spec) and total_years(profile) is None:
        errs.append("{YEARS} is used but the profile has no career_start")
    elif "{YEARS}" in json.dumps(spec) and total_years(profile) < 1:
        errs.append("{YEARS} cannot be used with less than 1 year of experience")
    return errs


# ------------------------------------------------------------------------- layout
class Item:
    def __init__(self, kind, flow, sec, blk=-1, bi=-1, nb=0):
        self.kind, self.flow, self.sec = kind, flow, sec
        self.blk, self.bi, self.nb = blk, bi, nb
        self.ok = False


def gap_before(kind, prev_kind, s):
    sp = SPACING
    if kind == "first":
        return 0.0
    if kind == "fixed5":
        return 5.0
    if kind == "fixed3":
        return 3.0
    if kind == "after_heading":
        return sp["section_after"]
    if kind == "first_bullet":
        return 3.0
    if kind == "bullet":
        return sp["bullet_gap"] * s
    if kind == "skill":
        return sp["skill_gap"] * s
    if kind == "edu_gap":
        return 9.0
    if kind == "role":
        return sp["list_end"] * s
    if kind == "section":
        pending = sp["list_end"] * s if prev_kind in ("bullet", "first_bullet") else 0.0
        return max(pending, sp["section_before"] * s)
    return 0.0


def used_height(page, s):
    y, prev = 0.0, None
    for i, (kind, f) in enumerate(page):
        if i:
            y += gap_before(kind, prev, s)
        y += f._h
        prev = kind
    return y


def solve_scale(page, target_pts):
    h0, h1 = used_height(page, 0.0), used_height(page, 1.0)
    return (target_pts - h0) / (h1 - h0) if h1 - h0 > 1e-6 else 1.0


def measure(flows):
    for f in flows:
        _, h = f.wrap(GEO["text_w"], 10000)
        f._h = h


def para_lines(p):
    out = []
    for ln in p.blPara.lines:
        if hasattr(ln, "words"):
            out.append("".join(getattr(w, "text", str(w)) for w in ln.words))
        else:
            words = ln[1]
            out.append(" ".join(words) if isinstance(words, (list, tuple)) else str(words))
    return [t.replace(chr(0xA0), " ").strip() for t in out]


def build_doc(profile, spec):
    """Turn profile + spec into layout items (the flowables, in order) and the continuation headings."""
    CTX["years"] = years_str(profile)
    set_page(profile.get("page_size", "A4"))
    rows = spec.get("skills", [])
    LAYOUT["label_w"] = min(max([stringWidth(r["label"], "Helvetica-Bold", 10) + 10 for r in rows] + [60.0]), 130.0)
    titles = {**DEFAULT_TITLES, **profile.get("section_titles", {})}
    omit = set(spec.get("omit_sections", []))
    items, conts = [], {}
    doc = {"items": items, "conts": conts, "bullets": [], "summary": None, "header": {}, "rows": [], "notes": []}

    h = spec["header"]
    ys = years_str(profile)
    show = bool(h.get("show_years", profile.get("show_years", True)) and ys is not None and total_years(profile) >= 1)
    doc["show_years"] = show
    parts = h["headline"].split(" | ") + ([f"{ys} Years Experience"] if show else [])
    head_p = Paragraph(" | ".join(f"<b>{markup(x)}</b>" for x in parts), S_HEAD)
    items.append(Item("first", Paragraph(markup(profile["name"]), S_NAME), "header"))
    items.append(Item("fixed5", head_p, "header"))
    doc["header"]["headline"] = head_p
    if h.get("keywords"):
        kw_p = Paragraph(("  " + BULLET + "  ").join(markup(k) for k in h["keywords"]), S_SMALL_C)
        items.append(Item("fixed3", kw_p, "header"))
        doc["header"]["keywords"] = kw_p
    con_p = Paragraph(contact_line(profile), S_SMALL_C)
    items.append(Item("fixed5", con_p, "header"))
    doc["header"]["contact line"] = con_p

    def heading(sec, title):
        items.append(Item("section", SectionHeading(title), sec))
        conts[("sec", sec)] = SectionHeading(title + " (continued)")

    def blocks(sec, title, entries, flow_fn, spec_items, label):
        got = {x["id"]: x["bullets"] for x in spec_items}
        chosen = [e for e in entries if e["id"] in got]
        if not chosen:
            return
        heading(sec, title)
        for k, e in enumerate(chosen):
            bl = got[e["id"]]
            items.append(Item("after_heading" if k == 0 else "role", flow_fn(e), sec, k, -1, len(bl)))
            conts[("blk", sec, k)] = flow_fn(e, True)
            for j, b in enumerate(bl):
                items.append(Item("first_bullet" if j == 0 else "bullet", bullet(b), sec, k, j, len(bl)))
                doc["bullets"].append((f"{label} {e['id']}", b))
        skipped = [e["id"] for e in entries if e["id"] not in got]
        if skipped:
            doc["notes"].append(f"{label} left out: {skipped}")

    order = profile.get("section_order") or DEFAULT_ORDER
    for key in order:
        if key in omit:
            continue
        if key == "summary" and spec.get("summary"):
            heading("summary", titles["summary"])
            p = Paragraph(markup(spec["summary"]), S_BODY)
            items.append(Item("after_heading", p, "summary"))
            doc["summary"] = p
        elif key == "skills" and rows:
            heading("skills", titles["skills"])
            for i, row in enumerate(rows):
                t = skill_row(row["label"], row["text"])
                items.append(Item("after_heading" if i == 0 else "skill", t, "skills"))
                doc["rows"].append((row, t))
        elif key == "experience":
            blocks("experience", titles["experience"], profile.get("experience", []), role_flow, spec.get("experience", []), "role")
        elif key == "projects":
            blocks("projects", titles["projects"], profile.get("projects", []), project_flow, spec.get("projects", []), "project")
        elif key == "education" and profile.get("education"):
            heading("education", titles["education"])
            for i, e in enumerate(profile["education"]):
                items.append(Item("after_heading" if i == 0 else "edu_gap", edu_flow(e), "education"))
        elif key in ("certifications", "awards") and profile.get(key):
            heading(key, titles[key])
            for i, b in enumerate(profile[key]):
                items.append(Item("after_heading" if i == 0 else "bullet", bullet(b), key))
        elif key == "extra":
            for n, x in enumerate(profile.get("extra_sections", [])):
                heading(f"extra{n}", x["title"].upper())
                for i, b in enumerate(x["bullets"]):
                    items.append(Item("after_heading" if i == 0 else "bullet", bullet(b), f"extra{n}"))
    for i, it in enumerate(items):
        it.ok = i > 0 and (it.kind == "section" or it.kind == "role" or (it.bi >= 2 and it.nb - it.bi >= 2))
    measure([it.flow for it in items] + list(conts.values()))
    return doc


def page_lists(items, conts, b):
    """Items before b are page 1; page 2 starts at b with a continuation heading when it opens inside a section."""
    p1 = [(it.kind, it.flow) for it in items[:b]]
    first, rest = items[b], [(it.kind, it.flow) for it in items[b + 1:]]
    if first.kind == "section":
        return p1, [(first.kind, first.flow)] + rest
    if first.kind == "role":
        return p1, [("first", conts[("sec", first.sec)]), ("after_heading", first.flow)] + rest
    return p1, [("first", conts[("blk", first.sec, first.blk)]), ("first_bullet", first.flow)] + rest


def fill_range(page):
    """Fill (percent of the frame) a page can reach with natural spacing: from the tightest to the loosest allowed."""
    fh = GEO["frame_h"]
    return used_height(page, S_OK_LO) / fh * 100, used_height(page, S_OK_HI) / fh * 100


def plan_pages(items, conts, pages_opt):
    """Choose 1 page, or the break for two pages. Page 1 must be able to reach the fill band (a hard need), page 2 may fall short
    (a soft cost: there may simply not be enough content), the spacing should be similar on both, and a clean break (between
    sections, then between roles) beats splitting inside a role."""
    fh = GEO["frame_h"]
    target = TARGET / 100.0 * fh
    whole = [(it.kind, it.flow) for it in items]
    if pages_opt == 1 or (pages_opt is None and used_height(whole, S_OK_LO) <= (FILL_HI + 0.5) / 100.0 * fh):
        return [whole], None
    best = None
    for b in range(1, len(items)):
        if not items[b].ok:
            continue
        p1, p2 = page_lists(items, conts, b)
        (lo1, hi1), (lo2, hi2) = fill_range(p1), fill_range(p2)
        miss1 = max(0.0, FILL_LO - hi1) + max(0.0, lo1 - FILL_HI)
        over2, under2 = max(0.0, lo2 - FILL_HI), max(0.0, FILL_LO - hi2)
        s1, s2 = (min(max(solve_scale(p, target), S_OK_LO), S_OK_HI) for p in (p1, p2))
        penalty = {"section": 0.0, "role": 0.15}.get(items[b].kind, 0.6)
        spacing = abs(math.log(s1 / s2)) if under2 == 0 else 0.3 * abs(math.log(s1))
        cost = 10 * miss1 + 10 * over2 + 0.01 * under2 + spacing + penalty
        if best is None or cost < best[0]:
            best = (cost, b, p1, p2)
    if best is None:
        return [whole], None
    return [best[2], best[3]], best[1]


def draw_page(c, page, s):
    y, prev = GEO["h"] - MT, None
    for i, (kind, f) in enumerate(page):
        if i:
            y -= gap_before(kind, prev, s)
        f.drawOn(c, ML, y - f._h)
        y -= f._h
        prev = kind


# -------------------------------------------------------------------------- report
def layout_checks(doc, spec, report):
    orphans, long_bullets = [], []

    def note(lines):
        if len(lines) > 1 and (len(lines[-1].split()) <= 1 or len(lines[-1]) <= 14):
            orphans.append(f"'{lines[-1]}' ends the text starting '{lines[0][:40]}'")

    for it in doc["items"]:
        f = it.flow
        if isinstance(f, Paragraph) and f.style.name in ("bullet", "body"):
            ls = para_lines(f)
            note(ls)
            if f.style.name == "bullet" and len(ls) > 3:
                long_bullets.append(ls[0][:40] + "...")
    skill_long, wide = [], []
    for row, t in doc["rows"]:
        ls = para_lines(t.text_para)
        note(ls)
        if len(ls) > 2:
            skill_long.append(row["label"])
        if len(para_lines(t.label_para)) > 1:
            wide.append(row["label"])
    report("WARN" if orphans else "OK", "orphan lines (one-word last lines)", orphans or "none")
    if doc["summary"] is not None:
        n = len(para_lines(doc["summary"]))
        report("OK" if n <= 6 else "WARN", "summary length", f"{n} lines (max 6)")
    wrapped = [f"{name} wraps" for name, f in doc["header"].items() if len(para_lines(f)) > 1]
    report("WARN" if wrapped else "OK", "header lines (each should fit on one line)", wrapped or "none")
    report("WARN" if long_bullets else "OK", "long bullets (3 lines at most)", long_bullets or "none")
    if doc["rows"]:
        report("WARN" if skill_long else "OK", "skills row length (2 lines at most)", skill_long or "none")
        report("OK" if len(doc["rows"]) <= 8 and not wide else "WARN", "skills rows",
               f"{len(doc['rows'])} rows (max 8); labels that wrap: {wide or 'none'}")
    counts = {}
    for label, _ in doc["bullets"]:
        counts[label] = counts.get(label, 0) + 1
    few = [k for k, v in counts.items() if v > 6]
    report("WARN" if few else "OK", "bullets per role or project (6 at most)", few or "none")


def content_checks(profile, spec, doc, facts, report):
    rendered = [("name", profile["name"])]
    rendered += [(f"{k}", str(v)) for k, v in (profile.get("contact") or {}).items()]
    rendered += [(f"link {k}", k) for k in (profile.get("links") or {})]
    rendered += [("profile text", s) for s in facts.strings]
    tailored = [("headline", spec["header"]["headline"]), ("keywords", ", ".join(spec["header"].get("keywords", [])))]
    if spec.get("summary"):
        tailored.append(("summary", spec["summary"]))
    tailored += [("skills", f"{r['label']} {r['text']}") for r in spec.get("skills", [])]
    tailored += [(label, b) for label, b in doc["bullets"]]
    bad = unsupported_chars(rendered + tailored)
    report("FAIL" if bad else "OK", "unsupported characters (the PDF font cannot draw them)", bad or "none")
    blob = "\n\n".join(plain(t) for _, t in tailored)
    nh = never_hits(blob, profile)
    report("FAIL" if nh else "OK", "never-claim terms (from the profile)", nh or "none")
    yc = years_claims(blob, facts)
    report("FAIL" if yc else "OK", "years claims (only your real total or a figure from your resume)", yc or "none")
    if doc["show_years"] and re.search(r"\byears?\b", spec["header"]["headline"], re.I):
        report("FAIL", "headline", "do not write the years in the headline; the script adds them (set header.show_years false to hide)")
    un = unverified_numbers(blob, facts)
    report("WARN" if un else "OK", "numbers not in your resume", un or "none")
    ut = unverified_terms(blob, facts)
    report("WARN" if ut else "OK", "terms not in your resume", ut or "none")
    lc = word_claims(blob, facts, LEAD_WORDS)
    report("WARN" if lc else "OK", "leadership words not in your resume (led, managed, mentored...)", lc or "none")
    sc = word_claims(blob, facts, SENIORITY_WORDS)
    report("WARN" if sc else "OK", "seniority words not in your resume (senior, manager...)", sc or "none")
    sb = similar_bullets([(label, plain(b)) for label, b in doc["bullets"]])
    report("WARN" if sb else "OK", "near-duplicate bullets in different roles or projects", sb or "none")
    stray = [n for n, t in tailored if "*" in re.sub(r"<[^>]+>", "", markup(t))]
    report("WARN" if stray else "OK", "stray asterisks (unbalanced ** or *)", stray or "none")
    left = sorted({m for _, t in tailored for m in re.findall(r"\{[A-Za-z_]+\}", plain(t))})
    report("WARN" if left else "OK", "placeholders left in the text", left or "none")
    for note_ in doc["notes"]:
        report("INFO", "left out of this version", note_)


def page_report(pages, scales, a, report):
    fh = GEO["frame_h"]
    for k, (page, s) in enumerate(zip(pages, scales), 1):
        f = used_height(page, s) / fh * 100
        last = k == len(pages)
        if f > 100:
            report("FAIL", f"page {k} fill", f"{f:.1f}% OVERFLOWS the page; cut about {int((f - 98) / 100 * fh / 12) + 1} lines")
        elif f > FILL_HI + 0.5:
            report("FAIL", f"page {k} fill", f"{f:.1f}% is above {FILL_HI}%; cut about {int((f - FILL_HI) / 100 * fh / 12) + 1} line(s)")
        elif f < FILL_LO - 0.5:
            lines = int((FILL_LO - f) / 100 * fh / 12) + 1
            msg = f"{f:.1f}% is below {FILL_LO}% even with looser spacing"
            if last and not a.strict_fill:
                extra = ""
                if len(pages) == 2:
                    fit = (used_height(pages[0], 1.0) + used_height(pages[1], 1.0)) / fh * 100 - 98
                    extra = f"; or cut about {int(fit / 100 * fh / 12) + 1} line(s) to fit one page" if fit > 0 else ""
                report("WARN", f"page {k} fill", f"{msg}. Only add content that is true: about {lines} line(s){extra}")
            else:
                report("FAIL", f"page {k} fill", f"{msg}; add about {lines} line(s) of true content")
        else:
            report("OK", f"page {k} fill", f"{f:.1f}% (target {FILL_LO}-{FILL_HI}%, spacing x{s})")
        if a.tune and not S_OK_LO <= s <= S_OK_HI and f >= FILL_LO - 0.5:
            lines = max(1, round(abs(used_height(page, s) - used_height(page, 1.0)) / 14))
            report("WARN", f"page {k} spacing", f"x{s} makes the gaps look {'loose' if s > 1 else 'tight'}; "
                   f"{'add' if s > 1 else 'cut'} about {lines} line(s) for more natural spacing")


# ----------------------------------------------------------------------- commands
def cmd_check_profile(a):
    p = load_json(a.profile, "profile")
    if p is UNREADABLE:
        return 1
    errs, warns = validate_profile(p)
    if errs:
        print("\n".join(f"FAIL profile: {e}" for e in errs))
        return 1
    p = normalise(p)
    c = p["contact"]
    print(f"Profile OK: {p['name']} | {c['email']} | {c.get('phone') or 'no phone'} | {c.get('location') or 'no location'}")
    print("Links: " + (", ".join(f"{k} -> {v}" for k, v in (p.get("links") or {}).items()) or "none"))
    ty = total_years(p)
    print(f"Page size: {p.get('page_size', 'A4')} | total experience: " + (f"{ty:g}+ years (career_start {p['career_start']})" if ty is not None else "not set"))
    print(f"Experience ({len(p.get('experience', []))}):")
    def count(n):
        return f"{n} bullet" + ("" if n == 1 else "s")
    for r in p.get("experience", []):
        print(f"  [{r['id']}] {r['title']} | {r['company']} | {r['dates']} | {count(len(r['bullets']))}")
    print(f"Projects ({len(p.get('projects', []))}):")
    for q in p.get("projects", []):
        print(f"  [{q['id']}] {q['name']} | {count(len(q['bullets']))}")
    print(f"Education ({len(p.get('education', []))}):")
    for e in p.get("education", []):
        print(f"  {e['institution']} | {e['degree']} | {e.get('dates', '')}")
    print(f"Skills rows: {len(p.get('skills', []))} | certifications: {len(p.get('certifications', []))} | awards: {len(p.get('awards', []))}")
    bad = unsupported_chars([("profile", s) for s in fact_strings(p)] + [("name", p["name"])])
    for w in warns:
        print(f"WARN profile: {w}")
    if bad:
        print(f"FAIL profile: characters the PDF font cannot draw: {bad}")
        return 1
    return 0


def cmd_build(a):
    profile, spec = load_json(a.profile, "profile"), load_json(a.spec, "spec")
    if profile is UNREADABLE or spec is UNREADABLE:
        return 1
    errs, _ = validate_profile(profile)
    if errs:
        print("\n".join(f"FAIL profile: {e}" for e in errs))
        return 1
    errs = validate_spec(spec, profile)
    if errs:
        print("\n".join(f"FAIL spec: {e}" for e in errs))
        return 1
    out = Path(a.out)
    if out.is_dir():
        print(f"FAIL output: {a.out} is a folder; give a file name such as {Path(a.out) / 'Resume.pdf'}")
        return 1
    profile, spec = normalise(profile), normalise(spec)
    lines_out = []

    def report(level, label, detail=""):
        tag = {"OK": "OK  ", "WARN": "WARN", "FAIL": "FAIL", "INFO": "INFO"}[level]
        lines_out.append(f"{tag} {label}: {detail}")

    facts = Facts(profile)
    doc = build_doc(profile, spec)
    pages_opt = a.pages or spec.get("pages")
    pages, brk = plan_pages(doc["items"], doc["conts"], pages_opt)
    fh = GEO["frame_h"]
    scales = []
    for k, page in enumerate(pages):
        s = solve_scale(page, TARGET / 100.0 * fh) if a.tune else 1.0
        scales.append(round(min(max(s, S_MIN), S_MAX), 3))
    page_report(pages, scales, a, report)
    mode = "as requested" if pages_opt else "chosen automatically"
    report("INFO", "pages", f"{len(pages)} ({mode}); page size {GEO['name']}")
    if brk is not None:
        first = doc["items"][brk]
        report("INFO", "page break", f"page 2 starts with: {getattr(first.flow, 'proof', '') or para_lines(first.flow)[0][:60]}")
    layout_checks(doc, spec, report)
    content_checks(profile, spec, doc, facts, report)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(GEO["w"], GEO["h"]), pageCompression=0)
    role = (spec.get("job") or {}).get("role", "Resume")
    c.setTitle(f"{profile['name']} - {role} Resume")
    c.setAuthor(profile["name"])
    for page, s in zip(pages, scales):
        draw_page(c, page, s)
        c.showPage()
    c.save()
    # reportlab writes a bullet as code 127, which Poppler reads as a bullet but pdfminer and pypdf do not.
    # Code 149 is the standard WinAnsi bullet; both are 4 characters, so nothing else in the file moves.
    data = buf.getvalue().replace(rb"\177", rb"\225")
    want = list((profile.get("links") or {}).values()) + [f"mailto:{profile['contact']['email']}"]
    missing = [u for u in want if esc(u).encode() not in data and u.encode() not in data]
    report("WARN" if missing else "OK", "links embedded", f"{len(want) - len(missing)}/{len(want)}" + (f" missing {missing}" if missing else ""))

    failed = any(l.startswith("FAIL") for l in lines_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    draft = out.with_name(out.stem + ".FAILED.pdf")
    if failed:
        draft.write_bytes(data)
        lines_out.append(f"FAIL NOT WRITTEN: {out} (fix the FAIL lines above and run again); a draft for inspection is {draft}")
    else:
        out.write_bytes(data)
        if draft.exists():
            draft.unlink()
    print(f"{'DRAFT' if failed else 'PDF'}: {draft if failed else out}")
    print("\n".join(lines_out))
    if a.proof:
        print("\n----- laid-out text -----")
        for n, page in enumerate(pages, 1):
            print(f"[page {n}]")
            for _, f in page:
                text = getattr(f, "proof", None)
                if text:
                    print("  " + text.replace("\n", "\n  "))
                elif isinstance(f, Paragraph):
                    for ln in para_lines(f):
                        print("  " + ln)
    return 2 if failed else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    cp = sub.add_parser("check-profile", help="validate a profile and print what was understood")
    cp.add_argument("profile")
    b = sub.add_parser("build", help="render a tailored resume PDF")
    b.add_argument("profile")
    b.add_argument("spec")
    b.add_argument("out")
    b.add_argument("--pages", type=int, choices=(1, 2), help="force 1 or 2 pages (default: chosen from the content)")
    b.add_argument("--proof", action="store_true", help="print the laid-out text for proofreading")
    b.add_argument("--no-tune", dest="tune", action="store_false", help="skip automatic spacing tuning")
    b.add_argument("--strict-fill", action="store_true", help="treat a last page below the fill band as a FAIL")
    a = ap.parse_args()
    return cmd_check_profile(a) if a.cmd == "check-profile" else cmd_build(a)


if __name__ == "__main__":
    sys.exit(main())

