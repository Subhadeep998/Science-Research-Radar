#!/usr/bin/env python3
"""Science Research Radar — daily research-only feeds.

Sources (all free, public APIs):
  * Europe PMC  — newest papers in flagship peer-reviewed journals (by ISSN)
  * arXiv       — newest preprints by field
  * bioRxiv / medRxiv — newest life-science and medical preprints

Writes fields/<id>.md (one page per field) and LATEST.md (daily digest).
Each source is isolated: if one API is down, the last good data is kept.
"""
import datetime as dt
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "cache.json")
UA = {"User-Agent": "Science-Research-Radar (github.com/Subhadeep998)"}
ATOM = "{http://www.w3.org/2005/Atom}"
TODAY = dt.date.today()

JOURNALS = [  # (label, ISSN)
    ("Nature", "0028-0836"), ("Science", "0036-8075"), ("Cell", "0092-8674"),
    ("The New England Journal of Medicine", "0028-4793"), ("The Lancet", "0140-6736"),
    ("Nature Medicine", "1078-8956"), ("Nature Biotechnology", "1087-0156"),
    ("PNAS", "0027-8424"),
]

FIELDS = [
    # id, title, emoji, source, spec
    ("ai-computing", "AI & Computing", "🤖", "arxiv", "cat:cs.AI OR cat:cs.LG OR cat:cs.CL"),
    ("robotics", "Robotics", "🦾", "arxiv", "cat:cs.RO"),
    ("physics", "Physics", "⚛️", "arxiv", "cat:hep-th OR cat:hep-ph OR cat:gr-qc OR cat:physics.gen-ph OR cat:nucl-th"),
    ("quantum", "Quantum Science", "🌀", "arxiv", "cat:quant-ph"),
    ("astronomy-space", "Astronomy & Space", "🔭", "arxiv", "cat:astro-ph.EP OR cat:astro-ph.GA OR cat:astro-ph.CO OR cat:astro-ph.SR OR cat:astro-ph.HE OR cat:astro-ph.IM"),
    ("materials-energy", "Materials & Energy", "🔋", "arxiv", "cat:cond-mat.mtrl-sci OR cat:physics.app-ph"),
    ("chemistry", "Chemistry", "🧪", "arxiv", "cat:physics.chem-ph OR cat:cond-mat.soft"),
    ("earth-climate", "Earth & Climate", "🌍", "arxiv", "cat:physics.ao-ph OR cat:physics.geo-ph"),
    ("mathematics", "Mathematics", "➗", "arxiv", "cat:math.CO OR cat:math.NT OR cat:math.PR OR cat:math.AG OR cat:math.ST"),
    ("genomics", "Genomics & Genetics", "🧬", "biorxiv", ["genomics", "genetics", "bioinformatics"]),
    ("neuroscience", "Neuroscience", "🧠", "biorxiv", ["neuroscience"]),
    ("cell-molecular", "Cell & Molecular Biology", "🔬", "biorxiv", ["cell biology", "molecular biology", "biochemistry", "biophysics"]),
    ("microbes-immunity", "Microbiology & Immunology", "🦠", "biorxiv", ["microbiology", "immunology"]),
    ("cancer", "Cancer Research", "🎯", "biorxiv", ["cancer biology"]),
    ("synbio-bioeng", "Synthetic Biology & Bioengineering", "🛠️", "biorxiv", ["synthetic biology", "bioengineering"]),
    ("ecology-evolution", "Ecology & Evolution", "🌿", "biorxiv", ["ecology", "evolutionary biology", "plant biology"]),
    ("medicine", "Medicine & Public Health", "🩺", "medrxiv", None),
]


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8")


def clean(s):
    return " ".join((s or "").split()).replace("|", "\\|")


def first_author(a):
    sep = ";" if ";" in (a or "") else ","
    names = [x.strip() for x in (a or "").split(sep) if x.strip()]
    return (names[0] + " et al.") if len(names) > 1 else (names[0] if names else "—")


def europepmc(issn, start, end, n=8):
    query = f'ISSN:"{issn}" AND FIRST_PDATE:[{start} TO {end}] AND PUB_TYPE:"journal article"'
    url = ("https://www.ebi.ac.uk/europepmc/webservices/rest/search?"
           + urllib.parse.urlencode({"query": query, "format": "json", "pageSize": 40, "resultType": "lite"}))
    res = json.loads(get(url)).get("resultList", {}).get("result", [])
    out = []
    for r in res:
        title = clean(r.get("title")).rstrip(".")
        if not title or len(title) < 25:
            continue  # skip corrections, editorials with short titles
        link = f"https://doi.org/{r['doi']}" if r.get("doi") else f"https://europepmc.org/article/{r.get('source', 'MED')}/{r.get('id')}"
        out.append({"date": r.get("firstPublicationDate", ""), "title": title, "link": link,
                    "who": first_author(r.get("authorString"))})
    out.sort(key=lambda x: x["date"], reverse=True)
    return out[:n]


def arxiv(query, n=12):
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(
        {"search_query": query, "sortBy": "submittedDate", "sortOrder": "descending", "max_results": n})
    root = ET.fromstring(get(url))
    out = []
    for e in root.findall(f"{ATOM}entry"):
        authors = [a.findtext(f"{ATOM}name") for a in e.findall(f"{ATOM}author")]
        out.append({"date": (e.findtext(f"{ATOM}published") or "")[:10],
                    "title": clean(e.findtext(f"{ATOM}title")),
                    "link": (e.findtext(f"{ATOM}id") or "").replace("http://", "https://"),
                    "who": (authors[0] + (" et al." if len(authors) > 1 else "")) if authors else "—"})
    return out


def rxiv(server, start, end, max_pages=40):
    items, cursor = [], 0
    for _ in range(max_pages):
        data = json.loads(get(f"https://api.biorxiv.org/details/{server}/{start}/{end}/{cursor}/json"))
        batch = data.get("collection", [])
        if not batch:
            break
        items += batch
        cursor += len(batch)
        total = int((data.get("messages") or [{}])[0].get("total", 0) or 0)
        if cursor >= total:
            break
        time.sleep(0.3)
    return items


def rxiv_pick(items, server, cats, n=12):
    seen, out = set(), []
    for it in sorted(items, key=lambda x: x.get("date", ""), reverse=True):
        cat = (it.get("category") or "").strip().lower()
        if cats and cat not in cats:
            continue
        if it.get("doi") in seen:
            continue
        seen.add(it.get("doi"))
        out.append({"date": it.get("date", ""), "title": clean(it.get("title")),
                    "link": f"https://www.{server}.org/content/{it.get('doi')}v{it.get('version', 1)}",
                    "who": first_author(it.get("authors"))})
        if len(out) >= n:
            break
    return out


def table(rows):
    if not rows:
        return "_The feed fills on the next daily run._\n"
    t = ["| Date | Paper | First author |", "|:--|:--|:--|"]
    t += [f"| {r['date']} | [{r['title']}]({r['link']}) | {clean(r['who'])} |" for r in rows]
    return "\n".join(t) + "\n"


def main():
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {"journals": {}, "fields": {}}
    end = TODAY.isoformat()
    week = (TODAY - dt.timedelta(days=7)).isoformat()
    pull_start = (TODAY - dt.timedelta(days=3)).isoformat()

    for label, issn in JOURNALS:
        try:
            cache["journals"][label] = europepmc(issn, week, end)
        except Exception as exc:
            print(f"[europepmc] {label}: {exc}", file=sys.stderr)
        time.sleep(0.5)

    pools = {}
    for server in ("biorxiv", "medrxiv"):
        try:
            pools[server] = rxiv(server, pull_start, end)
        except Exception as exc:
            print(f"[{server}] {exc}", file=sys.stderr)

    for fid, title, emoji, src, spec in FIELDS:
        try:
            if src == "arxiv":
                rows = arxiv(spec)
                time.sleep(3)  # arXiv asks for a pause between calls
            else:
                if src not in pools:
                    continue
                rows = rxiv_pick(pools[src], src, set(spec) if spec else None)
            if rows:
                cache["fields"][fid] = rows
        except Exception as exc:
            print(f"[{fid}] {exc}", file=sys.stderr)

    cache["updated"] = TODAY.isoformat()
    os.makedirs(os.path.join(ROOT, "fields"), exist_ok=True)
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    json.dump(cache, open(CACHE, "w"), indent=1, ensure_ascii=False)
    render(cache)


def render(cache):
    src_name = {"arxiv": "arXiv", "biorxiv": "bioRxiv", "medrxiv": "medRxiv"}
    for fid, title, emoji, src, spec in FIELDS:
        page = [f"# {emoji} {title}", "",
                f"> Newest research preprints from **{src_name[src]}** · refreshed daily · last update {cache.get('updated', '—')}",
                "> Preprints are **not yet peer-reviewed** — treat findings as preliminary.", "",
                "[← Radar home](../README.md) · [Today's digest](../LATEST.md) · [Peer-reviewed journals](journals.md)", "",
                table(cache["fields"].get(fid, []))]
        open(os.path.join(ROOT, "fields", f"{fid}.md"), "w", encoding="utf-8").write("\n".join(page))

    j = ["# 📚 Flagship peer-reviewed journals", "",
         f"> Research articles published in the last 7 days, via Europe PMC · last update {cache.get('updated', '—')}", "",
         "[← Radar home](../README.md) · [Today's digest](../LATEST.md)", ""]
    for label, _ in JOURNALS:
        j += [f"## {label}", "", table(cache["journals"].get(label, []))]
    open(os.path.join(ROOT, "fields", "journals.md"), "w", encoding="utf-8").write("\n".join(j))

    d = [f"# 🛰️ Research digest — {TODAY.strftime('%d %B %Y')}", "",
         "> The newest research across every field, in one page. Refreshed every morning (IST).", "",
         "[← Radar home](README.md)", "",
         "## 📚 Peer-reviewed highlights (last 7 days)", ""]
    for label, _ in JOURNALS:
        rows = cache["journals"].get(label, [])[:2]
        for r in rows:
            d.append(f"- **{label}** · [{r['title']}]({r['link']}) — _{clean(r['who'])}_")
    d.append("")
    for fid, title, emoji, src, spec in FIELDS:
        rows = cache["fields"].get(fid, [])[:4]
        d += [f"## {emoji} {title}", ""]
        d += [f"- {r['date']} · [{r['title']}]({r['link']})" for r in rows] or ["- _Fills on the next run._"]
        d += ["", f"[More {title} →](fields/{fid}.md)", ""]
    d += ["---", "<sub>Sources: Europe PMC, arXiv, bioRxiv and medRxiv public APIs. Titles and links only.</sub>", ""]
    open(os.path.join(ROOT, "LATEST.md"), "w", encoding="utf-8").write("\n".join(d))


if __name__ == "__main__":
    if "--offline" in sys.argv:
        render(json.load(open(CACHE)) if os.path.exists(CACHE) else {"journals": {}, "fields": {}})
    else:
        main()
