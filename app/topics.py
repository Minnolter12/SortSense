"""
SortSense deterministic topic engine (offline, no LLM).

Scores extracted text against a general subject taxonomy using weighted,
word-boundary term matches. Evidence is counted per *distinct* term so a
repeated word cannot inflate confidence. Headings and filenames add
corroboration. The result carries the matched terms so the UI can show why.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# subject -> {term: weight}. Weight 3 = near-unique to the subject, 2 = strong, 1 = supporting.
_LEXICON: dict[str, dict[str, int]] = {
    "DBMS": {
        "dbms": 3, "database management system": 3, "database management systems": 3,
        "normalization": 2, "normalisation": 2, "1nf": 3, "2nf": 3, "3nf": 3, "bcnf": 3,
        "functional dependency": 3, "functional dependencies": 3, "candidate key": 2,
        "primary key": 2, "foreign key": 2, "sql": 2, "join": 1, "inner join": 2, "left join": 2,
        "acid": 2, "transaction": 1, "transactions": 1, "commit": 1, "rollback": 2, "savepoint": 2,
        "er diagram": 3, "entity relationship": 3, "relational": 1, "relation": 1, "schema": 1,
        "database": 2, "databases": 2, "query": 1, "select": 1, "index": 1, "concurrency control": 2,
    },
    "DSA": {
        "dsa": 3, "data structure": 3, "data structures": 3, "algorithm": 2, "algorithms": 2,
        "binary search tree": 3, "bst": 3, "linked list": 3, "stack": 1, "queue": 1,
        "breadth first search": 3, "depth first search": 3, "bfs": 3, "dfs": 3,
        "merge sort": 3, "quick sort": 3, "heap sort": 3, "sorting": 1, "time complexity": 3,
        "space complexity": 3, "big o": 2, "adjacency list": 3, "adjacency matrix": 2,
        "dijkstra": 3, "dynamic programming": 3, "recursion": 1, "hash table": 3,
        "binary search": 2, "inorder traversal": 2, "subtree": 1, "pivot": 1, "heap": 1,
    },
    "OOPS": {
        "oops": 3, "oop": 3, "object oriented": 3, "object-oriented": 3, "inheritance": 3,
        "polymorphism": 3, "encapsulation": 3, "abstraction": 2, "abstract class": 3,
        "interface": 1, "method overriding": 3, "overloading": 2, "constructor": 2,
        "class": 1, "object": 1, "objects": 1, "access modifier": 3, "access modifiers": 3,
        "private": 1, "protected": 1, "public": 1, "java": 1, "data hiding": 3, "instance": 1,
    },
    "Discrete Mathematics": {
        "discrete mathematics": 3, "discrete math": 3, "propositional logic": 3, "proposition": 2,
        "truth table": 3, "logical connectives": 3, "biconditional": 3, "implication": 2,
        "set theory": 3, "relations": 1, "reflexive": 3, "symmetric": 2, "antisymmetric": 3,
        "transitive": 2, "partial order": 3, "partial orders": 3, "cartesian product": 3,
        "graph theory": 3, "vertices": 1, "edges": 1, "spanning tree": 2, "spanning trees": 2,
        "combinatorics": 3, "permutation": 2, "combination": 1, "pigeonhole": 3, "induction": 2,
        "cycles": 1, "connectedness": 2, "acyclic": 2, "predicate logic": 3, "boolean algebra": 2,
    },
    "Operating Systems": {
        "operating system": 3, "operating systems": 3, "process scheduling": 3, "deadlock": 3,
        "semaphore": 3, "mutex": 3, "paging": 3, "virtual memory": 3, "context switch": 3,
        "kernel": 2, "thread": 1, "threads": 1, "cpu scheduling": 3, "round robin": 2,
        "page replacement": 3, "file system": 1, "inode": 3, "race condition": 2,
    },
    "Computer Networks": {
        "computer network": 3, "computer networks": 3, "tcp": 3, "udp": 3, "ip address": 3,
        "osi model": 3, "routing": 2, "subnet": 3, "dns": 3, "http": 2, "ethernet": 3,
        "router": 2, "packet": 2, "bandwidth": 2, "latency": 1, "protocol": 1, "firewall": 2,
    },
    "Machine Learning": {
        "machine learning": 3, "neural network": 3, "neural networks": 3, "gradient descent": 3,
        "overfitting": 3, "regression": 2, "classification": 1, "training set": 3,
        "supervised learning": 3, "unsupervised learning": 3, "backpropagation": 3,
        "random forest": 3, "decision tree": 2, "feature": 1, "loss function": 3, "clustering": 2,
    },
    "NLP": {
        "nlp": 3, "natural language processing": 3, "tokenization": 3, "tokenisation": 3,
        "named entity": 3, "part of speech": 3, "language model": 2, "word embedding": 3,
        "sentiment analysis": 3, "stemming": 2, "lemmatization": 3, "corpus": 2,
    },
    "Python": {"python": 3, "pandas": 3, "numpy": 3, "list comprehension": 3, "pip install": 3, "def ": 1},
    "Mathematics": {
        "calculus": 3, "linear algebra": 3, "matrix": 2, "matrices": 2, "eigenvalue": 3,
        "derivative": 2, "integral": 2, "differential equation": 3, "probability": 2,
        "statistics": 2, "theorem": 1, "mathematics": 2, "limit": 1,
    },
    "Physics": {
        "physics": 3, "quantum": 3, "electrodynamics": 3, "thermodynamics": 3, "velocity": 2,
        "momentum": 2, "newton": 2, "electric field": 3, "magnetic field": 3, "wavelength": 2,
    },
    "Chemistry": {
        "chemistry": 3, "organic chemistry": 3, "molecule": 2, "molecules": 2, "periodic table": 3,
        "reaction": 1, "covalent": 3, "ionic bond": 3, "stoichiometry": 3, "acid": 1, "electron": 1,
    },
}

_COMPILED: dict[str, list[tuple[str, int, re.Pattern[str]]]] = {
    subj: [
        (term, w, re.compile(r"(?<![a-z0-9])" + re.escape(term.strip()) + r"(?![a-z0-9])", re.I))
        for term, w in terms.items()
    ]
    for subj, terms in _LEXICON.items()
}

_TITLE_LINE_RE = re.compile(r"^\s*(?:topic|title|chapter|unit|module|lesson|subject|course|notification|circular|invoice|bill)\s*[:\-–]\s*(.+?)\s*$", re.I)


@dataclass(frozen=True)
class TopicResult:
    subject: str | None
    confidence: float          # evidence-based, 0..0.92
    matched_terms: list[str] = field(default_factory=list)
    runner_up: str | None = None
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)


def _lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def classify_topic(text: str, filename: str = "") -> TopicResult:
    """Return the best subject for *text*, or subject=None when evidence is too thin."""
    body = text[:8000]
    head = " \n".join(_lines(body)[:3])
    fname = re.sub(r"[_\-.]+", " ", filename)
    scores: dict[str, float] = {}
    hits: dict[str, list[str]] = {}
    head_hits: dict[str, int] = {}
    for subj, entries in _COMPILED.items():
        total = 0.0
        for term, w, pat in entries:
            in_body = bool(pat.search(body))
            in_head = bool(pat.search(head))
            in_name = bool(pat.search(fname))
            if not (in_body or in_head or in_name):
                continue
            total += w + (1.5 * w if in_head else 0) + (0.5 * w if in_name else 0)
            hits.setdefault(subj, []).append(term.strip())
            if in_head and w >= 2:
                head_hits[subj] = head_hits.get(subj, 0) + 1
        if total:
            scores[subj] = total
    if not scores:
        return TopicResult(None, 0.0)
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    best, top = ranked[0]
    second_name, second = ranked[1] if len(ranked) > 1 else (None, 0.0)
    distinct = len(hits[best])
    strong = sum(1 for t in hits[best] if any(t == tt.strip() and w >= 2 for tt, w, _ in _COMPILED[best]))
    if distinct < 2 or strong < 1:
        return TopicResult(None, 0.0, hits[best], best, top)
    margin = (top - second) / top if top else 0.0
    strength = min(1.0, top / 18.0)
    conf = 0.30 + 0.38 * strength + 0.22 * margin + (0.04 if head_hits.get(best) else 0.0)
    if margin < 0.15:
        conf = min(conf, 0.60)  # genuinely ambiguous between two subjects
    conf = round(min(0.92, conf), 2)
    reasons = [f"Matched {distinct} {best} terms: " + ", ".join(hits[best][:6])]
    if head_hits.get(best):
        reasons.append("Subject terms appear in the document heading")
    if second_name and second:
        reasons.append(f"Next closest subject: {second_name}")
    return TopicResult(best, conf, hits[best], second_name, top, reasons)


def suggest_title(text: str, subject: str | None = None) -> str | None:
    """Pick a concise human title from the document content (no filename hardcoding)."""
    lines = _lines(text[:3000])
    for ln in lines[:15]:
        m = _TITLE_LINE_RE.match(ln)
        if m:
            return _clean_title(m.group(1))
    for ln in lines[:8]:
        md = re.match(r"^#{1,3}\s+(.+)$", ln)
        if md:
            return _clean_title(md.group(1))
    for ln in lines[:8]:
        if re.search(r"\b(tax invoice|invoice|payment receipt|fee receipt|circular|notification|examination paper|question paper|lecture notes|study material)\b", ln, re.I):
            ct = _clean_title(ln)
            if ct:
                return ct
    if lines:
        first = lines[0]
        if 3 <= len(first) <= 80 and not first.endswith((".", ",", ";")):
            return _clean_title(first)
    return None


def _clean_title(raw: str) -> str | None:
    raw = re.sub(r"[`*_#>]+", "", raw)
    raw = re.sub(r"[^\w\s&+\-]", " ", raw)
    words = raw.split()[:8]
    if not words:
        return None
    small = {"and", "or", "of", "the", "in", "to", "a", "an", "for", "with"}
    out = []
    for i, w in enumerate(words):
        if w.isupper() and len(w) <= 4 and w.upper() in {"BST", "BFS", "DFS", "SQL", "ACID", "DBMS", "DSA", "OOP", "OOPS", "NLP", "TCP", "UDP", "ER", "1NF", "2NF", "3NF"}:
            out.append(w)
        elif w.lower() in small and i:
            out.append(w.lower())
        else:
            out.append(w.capitalize() if not w[0].isdigit() else w.upper())
    title = "_".join(out)
    return title[:60].rstrip("_") or None
