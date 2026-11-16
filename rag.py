"""Tiny free RAG: load files -> chunk -> BM25 search. No paid APIs, no extra services."""
import math, os, re
from collections import Counter

KNOWLEDGE_DIR = os.environ.get("KNOWLEDGE_DIR", "knowledge")
CHUNK_SIZE, OVERLAP = 800, 150
_tok = re.compile(r"\w+", re.UNICODE)
chunks = []   # {"source", "text", "tf", "len"}
df = Counter()
avg_len = 0.0


def stem(w):
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w


STOP = set("a an the i me my you your is are am was be do does did how what why when where which can could should would to of in on for and or it this that with from at as by please tell about".split())


def tokens(s):
    return [stem(w) for w in _tok.findall(s.lower()) if w not in STOP]


def read_file(path):
    ext = path.lower().rsplit(".", 1)[-1]
    if ext in ("txt", "md", "csv", "json", "html"):
        return open(path, encoding="utf-8", errors="ignore").read()
    if ext == "pdf":
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(path).pages)
    if ext == "docx":
        import docx
        return "\n".join(p.text for p in docx.Document(path).paragraphs)
    return ""


def split(text):
    """FAQ files (Q:/A: pairs) -> one chunk per pair. Other text -> paragraph chunks with overlap."""
    if re.search(r"(?m)^Q:", text):
        return [e.strip() for e in re.split(r"(?m)^(?=Q:)", text) if e.strip()]
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    out, cur = [], ""
    for p in paras:
        while len(p) > CHUNK_SIZE:               # very long paragraph
            out.append(p[:CHUNK_SIZE]); p = p[CHUNK_SIZE - OVERLAP:]
        if len(cur) + len(p) + 1 > CHUNK_SIZE and cur:
            out.append(cur); cur = cur[-OVERLAP:] + "\n" + p
        else:
            cur = (cur + "\n" + p).strip()
    if cur:
        out.append(cur)
    return out


def load():
    global avg_len
    chunks.clear(); df.clear()
    for root, _, files in os.walk(KNOWLEDGE_DIR):
        for f in sorted(files):
            path = os.path.join(root, f)
            if not f.lower().endswith((".txt", ".md", ".csv", ".json", ".html", ".pdf", ".docx")):
                continue
            try:
                text = read_file(path)
            except Exception as e:
                print(f"[rag] skipped {f}: {e}"); continue
            for piece in split(text):
                # question words count double so "how do I X" matches the right entry
                toks = tokens(piece) + (tokens(piece.split("\nA:")[0]) if piece.startswith("Q:") else [])
                chunks.append({"source": f, "text": piece, "tf": Counter(toks), "len": len(toks)})
    for c in chunks:
        df.update(c["tf"].keys())
    avg_len = sum(c["len"] for c in chunks) / max(len(chunks), 1)
    print(f"[rag] loaded {len(chunks)} chunks from {KNOWLEDGE_DIR}/")
    return len(chunks)


def search(query, k=4):
    if len(chunks) <= k:                      # tiny knowledge base: use everything
        return list(chunks)
    q = set(tokens(query))
    n, scored = len(chunks), []
    for c in chunks:
        s = 0.0
        for t in q:
            f = c["tf"].get(t, 0)
            if not f:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            s += idf * f * 2.5 / (f + 1.5 * (0.25 + 0.75 * c["len"] / avg_len))
        if s > 0:
            scored.append((s, c))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:k]]