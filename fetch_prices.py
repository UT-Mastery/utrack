#!/usr/bin/env python3
"""Tarik harga NAV semua unit trust daripada FIMM -> prices.json"""
import io, json, re, sys, datetime, urllib.request

URL = "https://www.fimm.com.my/report/dailyprice.php"
END = re.compile(r"(?<![\w.])(\d+\.\d{2,4}|NA|SUSP)$")
COMPANY = re.compile(r"(BERHAD|BHD\.?)(\s*\(.*\))?$")
FLAG = re.compile(r"\(([a-zA-Z])\)")
LEGEND = re.compile(r"^\(([a-z])\)\s*Price in (MYR|USD|AUD|SGD|EUR|RMB|GBP|HKD)", re.I)
NOISE = re.compile(r"^(NAV|RM|GLOBAL FUND NOTES:?)$|^\([a-z]\)\s*[A-Za-z]|^\*?FIMM shall|"
                   r"^[zZ]\d*\s+(Formerly|Daily|Manager|Unlisted)|^\d+\s+Formerly|"
                   r"^(Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day ")
GLOBAL = {"j": "USD", "l": "AUD", "s": "SGD", "p": "EUR", "r": "RMB", "v": "GBP"}

def clean(buf, company=False):
    """Buang sisa nota kaki (perkataan huruf kecil) di hadapan nama."""
    t = buf.split()
    if company and "(formerly" in buf:
        return " ".join(t)
    last = -1
    for i, w in enumerate(t):
        if re.search(r"[a-z]", w) and not re.fullmatch(r"\(?[a-z]\)?|[zZ]\d+", w):
            last = i
    return " ".join(t[last + 1:])

def parse(text):
    asof, company, buf, rows, legend = None, None, "", [], {}
    for l in (x.strip() for x in text.splitlines()):
        if not l:
            continue
        if asof is None:
            m = re.search(r"(\d{1,2} [A-Za-z]+ \d{4})", l)
            if m:
                try:
                    asof = datetime.datetime.strptime(m.group(1), "%d %B %Y").date().isoformat()
                except ValueError:
                    pass
        m = LEGEND.match(l)
        if m:
            legend.setdefault(company, {})[m.group(1)] = m.group(2).upper()
            continue
        if NOISE.match(l):
            continue
        buf = (buf + " " + l).strip()
        m = END.search(buf)
        if m:
            raw = clean(buf[:m.start()])
            flags = FLAG.findall(raw)
            name = FLAG.sub("", raw)
            name = re.sub(r"\s+[zZ]\d+$", "", re.sub(r"\s+", " ", name)).strip()
            val = m.group(1)
            if name and company:
                rows.append({"c": company, "n": name,
                             "p": float(val) if val[0].isdigit() and float(val) > 0 else None,
                             "s": val if not val[0].isdigit() else "", "f": flags})
            buf = ""
        elif COMPANY.search(buf):
            company = clean(buf, True) or company
            buf = ""
    for r in rows:
        cur = "MYR"
        for f in r.pop("f"):
            cur = legend.get(r["c"], {}).get(f) or GLOBAL.get(f) or cur
        r["cur"] = cur
    return asof, rows

def update_history(rows, asof, path="history.json", keep=800):
    """Simpan sejarah NAV harian semua dana (untuk pulangan, carta dan kalendar)."""
    try:
        h = json.load(open(path, encoding="utf-8"))
        d, ser = h["d"], h["s"]
    except Exception:
        d, ser = [], {}
    if asof in d:
        return
    today = {r["c"] + "|" + r["n"]: r["p"] for r in rows}
    n = len(d)
    d.append(asof)
    for k, p in today.items():
        ser.setdefault(k, [None] * n).append(p)
    for k in ser:
        if len(ser[k]) < len(d):
            ser[k].append(None)
    if len(d) > keep:
        cut = len(d) - keep
        d = d[cut:]
        ser = {k: v[cut:] for k, v in ser.items()}
    ser = {k: v for k, v in ser.items() if any(x is not None for x in v)}
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"d": d, "s": ser}, f, ensure_ascii=False, separators=(",", ":"))

def main():
    from pypdf import PdfReader
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 uttrace"})
    data = urllib.request.urlopen(req, timeout=60).read()
    text = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages)
    asof, rows = parse(text)
    if len(rows) < 500 or not asof:
        sys.exit(f"Hasil pelik ({len(rows)} dana, tarikh {asof}) - fail lama dikekalkan")
    out = {"asOf": asof, "updated": datetime.datetime.utcnow().isoformat() + "Z", "funds": rows}
    with open("prices.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    update_history(rows, asof)
    print(len(rows), "dana,", asof)

if __name__ == "__main__":
    main()
