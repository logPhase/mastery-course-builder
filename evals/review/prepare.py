#!/usr/bin/env python3
"""Prepare a built course for error analysis in the review app (server.py, index.html).

Usage: python3 prepare.py course.json --out <dir>/error_discovery_data
           [--check-report check-report.json] [--transcript transcript.jsonl] [--validator validator.txt]

Writes samples.json (every record plus the current sample), graph.json (clusters and the 2D map) and
suggestions.json (seeded from the check report and the validator, merged with the suggestions already there).
patterns.json ({}) and annotations.json ([]) are written only when missing, so a second run never loses review work.
Standard library only: the k-means and the PCA are written out below."""
import argparse
import hashlib
import json
import math
import os
import random
import re
import tempfile
import time
from collections import Counter
from pathlib import Path

# feature -> its words in outlier badges and cluster names; features() computes them, z-scored within each kind
FEATURES = {
    "explanation_words": "explanation words",
    "worked_steps": "worked-example steps",
    "practice_items": "practice items",
    "misconceptions": "misconceptions",
    "key_prerequisites": "key prerequisites",
    "knowledge_points": "knowledge points",
    "review_items": "review items",
    "discriminating_items": "discriminating review items",
    "prerequisites": "prerequisites",
    "encompasses": "encompassed topics",
    "confusable": "confusable topics",
    "sources": "sources",
    "est_minutes": "first-lesson minutes",
    "choices_per_item": "choices per item",
    "problem_words": "problem words per item",
    "solution_words": "solution words per item",
    "graph_depth": "graph depth",
}
GRAPH = {"key_prerequisites", "prerequisites", "encompasses", "confusable", "graph_depth"}  # cluster on these, never badge them
MISMATCH = {"key_wrong": "wrong answer key", "ambiguous": "ambiguous item", "mine_wrong": "checker answered wrong"}


def d(x): return x if isinstance(x, dict) else {}
def l(x): return x if isinstance(x, list) else []
def words(s): return len(str(s or "").split())
def mean(xs): return sum(xs) / len(xs) if xs else 0.0
def dist2(a, b): return sum((x - y) ** 2 for x, y in zip(a, b))


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def write_json(path, data):
    """Temp file and rename, so a reader never sees half a file."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def read_json(path, default):
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


# ---------- records ----------

def course_records(course):
    """One record per topic (graph, review, diagnostic) followed by one per knowledge point, in sequence order."""
    topics = [t for t in l(course.get("topics")) if isinstance(t, dict)]
    by_tid = {str(t.get("id")): t for t in topics}
    seq = [str(x) for x in l(course.get("sequence"))]
    pos = {x: i for i, x in enumerate(seq)}
    depth, used, recs = {}, set(), []

    def dep(tid, seen=()):
        if tid not in depth:
            if tid in seen or tid not in by_tid:
                return 0
            depth[tid] = 1 + max([dep(str(p), seen + (tid,)) for p in l(by_tid[tid].get("prerequisites"))] or [0])
        return depth[tid]

    def uniq(x):  # a duplicated id would hide a record in the app, so the copy gets a suffix
        x = base = str(x)
        n = 2
        while x in used:
            x, n = f"{base}~{n}", n + 1
        used.add(x)
        return x

    for i, t in sorted(enumerate(topics), key=lambda it: (pos.get(str(it[1].get("id")), len(seq)), it[0])):
        tid = str(t.get("id") or f"topic{i + 1}")
        rid = uniq(tid)
        kps = [kp for kp in l(t.get("knowledge_points")) if isinstance(kp, dict)]
        kp_ids = [uniq(kp.get("id") or f"{tid}.{j + 1}") for j, kp in enumerate(kps)]
        title = str(t.get("title") or tid)
        recs.append({**{k: v for k, v in t.items() if k != "knowledge_points"}, "id": rid, "kind": "topic",
                     "title": title, "depth": dep(tid),
                     "kps": [{"id": k, "label": str(kp.get("label") or "")} for k, kp in zip(kp_ids, kps)]})
        for kid, kp in zip(kp_ids, kps):
            recs.append({**kp, "id": kid, "kind": "kp", "title": str(kp.get("label") or kid), "topic_id": rid,
                         "topic_title": title, "strand": t.get("strand"), "depth": dep(tid)})
    return recs


def result_text(content):
    if isinstance(content, str):
        return content
    return "\n".join(str(b.get("text", "")) if b.get("type") == "text" else f"[{b.get('type')}]"
                     for b in l(content) if isinstance(b, dict))


def trace_record(path):
    """Group the stream-json events of a `claude -p` run into steps: thinking and text, tool calls, their results.
    A subagent's events (parent_tool_use_id set) form their own steps, labelled with the subagent's type."""
    steps, current, step_of, calls, meta, tools = [], {}, {}, {}, {}, Counter()

    def step(parent, fresh=False):
        s = current.get(parent)
        if fresh or s is None or s["_done"]:
            inp = d(d(calls.get(parent)).get("input"))
            agent = (": ".join(str(x) for x in (inp.get("subagent_type"), inp.get("description")) if x) or "subagent") if parent else None
            s = current[parent] = {"agent": agent, "items": [], "_done": False}
            steps.append(s)
        return s

    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if not isinstance(e, dict):
            continue
        kind, parent = e.get("type"), e.get("parent_tool_use_id")
        content = d(e.get("message")).get("content")
        blocks = [{"type": "text", "text": content}] if isinstance(content, str) else [b for b in l(content) if isinstance(b, dict)]
        if kind == "system" and e.get("subtype") == "init":
            meta.update(model=e.get("model"), cwd=e.get("cwd"))
        elif kind == "result":
            meta.update({k: e.get(k) for k in ("subtype", "is_error", "duration_ms", "num_turns", "total_cost_usd")})
            if e.get("result"):
                step(None, fresh=True)["items"].append({"type": "final", "text": str(e["result"])})
        elif kind == "assistant":
            for b in blocks:
                t = b.get("type")
                if t in ("thinking", "text") and str(b.get(t) or "").strip():  # redacted thinking arrives empty
                    step(parent)["items"].append({"type": t, "text": str(b[t])})
                elif t == "tool_use":
                    s = step(parent)
                    calls[b.get("id")] = item = {"type": "tool_call", "id": b.get("id"), "name": b.get("name"), "input": b.get("input")}
                    s["items"].append(item)
                    step_of[b.get("id")] = s
                    tools[str(b.get("name"))] += 1
        elif kind == "user":
            for b in blocks:
                if b.get("type") == "tool_result":
                    s = step_of.get(b.get("tool_use_id")) or step(parent)
                    text = result_text(b.get("content"))
                    at = next((i for i, x in enumerate(s["items"]) if x.get("id") == b.get("tool_use_id")), len(s["items"]) - 1)
                    s["items"].insert(at + 1, {"type": "tool_result", "tool_use_id": b.get("tool_use_id"),
                                               "is_error": bool(b.get("is_error")), "text": text,
                                               "summary": next((x.strip() for x in text.splitlines() if x.strip()), "")[:160]})
                    s["_done"] = True
                elif b.get("type") == "text" and str(b.get("text") or "").strip():
                    s = step(parent, fresh=True)
                    s["_done"] = True
                    # the skill's own text, injected when the agent loads it: the same in every run
                    s["items"].append({"type": "user", "text": str(b["text"]),
                                       "boilerplate": str(b["text"]).startswith("Base directory for this skill:")})
    for s in steps:
        s.pop("_done")
    meta["tool_calls"] = dict(tools.most_common())
    return {"id": "build", "kind": "trace", "title": "Build transcript", "meta": meta, "steps": steps}


# ---------- features, clusters, map, sample ----------

def features(r):
    items = l(r.get("practice")) if r["kind"] == "kp" else l(r.get("review")) + [r.get("diagnostic")]
    items = [q for q in items if isinstance(q, dict)]
    f = {"choices_per_item": mean([len(l(q.get("choices"))) for q in items]),
         "problem_words": mean([words(q.get("problem")) for q in items]),
         "solution_words": mean([words(q.get("solution")) for q in items]),
         "graph_depth": r.get("depth", 0)}
    if r["kind"] == "kp":
        f.update(explanation_words=words(r.get("explanation")), worked_steps=len(l(d(r.get("worked_example")).get("steps"))),
                 practice_items=len(items), misconceptions=len(l(r.get("misconceptions"))),
                 key_prerequisites=len(l(r.get("key_prerequisites"))))
    else:
        review = [q for q in l(r.get("review")) if isinstance(q, dict)]
        f.update(knowledge_points=len(r["kps"]), review_items=len(review),
                 discriminating_items=sum(1 for q in review if q.get("discriminates")),
                 prerequisites=len(l(r.get("prerequisites"))), encompasses=len(l(r.get("encompasses"))),
                 confusable=len(l(r.get("confusable_with"))), sources=len(l(r.get("sources"))),
                 est_minutes=num(r.get("est_minutes")))
    return f


def vectors(group):
    """One kind's features as z-scores within the kind, plus its strand one-hot (two strands differ by one unit)."""
    names = [n for n in FEATURES if n in group[0]["features"]]
    stats = {}
    for n in names:
        vals = [r["features"][n] for r in group]
        m = mean(vals)
        stats[n] = (m, math.sqrt(mean([(v - m) ** 2 for v in vals])))
    strands = sorted({str(r.get("strand")) for r in group})
    X = [[(r["features"][n] - stats[n][0]) / stats[n][1] if stats[n][1] else 0.0 for n in names]
         + [(str(r.get("strand")) == s) / math.sqrt(2) for s in strands] for r in group]
    return X, stats, names


def flag_outliers(group, stats):
    """Header badges: a content feature where the record sits beyond 90% of its kind and 2 SD from the mean; at most 2."""
    for r in group:
        found = []
        for name, (m, sd) in stats.items():
            v = r["features"][name]
            if len(group) < 5 or name in GRAPH or not sd or abs(v - m) / sd < 2:
                continue
            hi = v > m
            share = sum(o["features"][name] < v if hi else o["features"][name] > v for o in group if o is not r) / (len(group) - 1)
            if share >= 0.9:
                where = f"{'highest' if hi else 'lowest'} of {len(group)}" if share == 1 else f"{'higher' if hi else 'lower'} than {round(100 * share)}%"
                found.append((abs(v - m) / sd, f"{FEATURES[name]}: {round(v, 1):g} ({where})"))
        r["flags"] = [t for _, t in sorted(found, reverse=True)[:2]]


def kmeans(X, k, rng, iters=100):
    cents = [X[rng.randrange(len(X))]]
    while len(cents) < k:  # k-means++ seeding
        d2 = [min(dist2(x, c) for c in cents) for x in X]
        if not sum(d2):
            break  # fewer distinct points than k
        pick = rng.random() * sum(d2)
        for x, w in zip(X, d2):
            pick -= w
            if pick <= 0 and w:
                cents.append(x)
                break
    assign = None
    for _ in range(iters):
        new = [min(range(len(cents)), key=lambda j: dist2(x, cents[j])) for x in X]
        if new == assign:
            break
        assign = new
        for j in range(len(cents)):
            members = [x for x, a in zip(X, assign) if a == j]
            if members:
                cents[j] = [sum(col) / len(members) for col in zip(*members)]
    used = sorted(set(assign), key=lambda j: -assign.count(j))  # renumber by size, dropping empty clusters
    return [used.index(a) for a in assign], [cents[j] for j in used]


def pca2(X):
    """Top two principal components by power iteration with deflation."""
    n, dim = len(X), len(X[0]) if X else 0
    if n < 2 or not dim:
        return [(0.0, 0.0)] * n
    mu = [sum(c) / n for c in zip(*X)]
    Xc = [[v - m for v, m in zip(x, mu)] for x in X]
    C = [[sum(r[i] * r[j] for r in Xc) / (n - 1) for j in range(dim)] for i in range(dim)]
    comps = []
    for _ in range(2):
        v = [1.0 + 0.01 * i for i in range(dim)]
        for _ in range(500):
            w = [sum(C[i][j] * v[j] for j in range(dim)) for i in range(dim)]
            norm = math.sqrt(sum(x * x for x in w))
            if norm < 1e-12:
                v = [0.0] * dim
                break
            w = [x / norm for x in w]
            done = dist2(w, v) < 1e-14
            v = w
            if done:
                break
        lam = sum(v[i] * C[i][j] * v[j] for i in range(dim) for j in range(dim))
        C = [[C[i][j] - lam * v[i] * v[j] for j in range(dim)] for i in range(dim)]
        if v[max(range(dim), key=lambda i: abs(v[i]))] < 0:  # fix the sign so reruns draw the same map
            v = [-x for x in v]
        comps.append(v)
    return [(sum(a * b for a, b in zip(x, comps[0])), sum(a * b for a, b in zip(x, comps[1]))) for x in Xc]


def cluster_label(kind, members, centroid, names):
    traits = [f"{FEATURES[name]} {'high' if c > 0 else 'low'}"
              for _, name, c in sorted(((abs(c), name, c) for name, c in zip(names, centroid) if abs(c) >= 0.5), reverse=True)[:2]]
    strand, count = Counter(str(r.get("strand")) for r in members).most_common(1)[0]
    if strand != "None" and count / len(members) > 0.6:
        traits.append(f"strand {strand}")
    return f"{'knowledge points' if kind == 'kp' else 'topics'}: {', '.join(traits) or 'typical'}"


def cluster_and_sample(recs, rng):
    """Per kind (knowledge points, topics): features, outlier flags, k-means clusters and a PCA map scaled to 0-1,
    so a cluster never mixes kinds and both axes show variation within the kind. Returns (graph, initial sample ids)."""
    n = len(recs)
    k_total = min(10, max(6, round(math.sqrt(n)))) if n >= 12 else max(1, n // 2)
    clusters, points, ranked = [], [], []
    for kind in ("kp", "topic"):
        group = [r for r in recs if r["kind"] == kind]
        if not group:
            continue
        for r in group:
            r["features"] = features(r)
        X, stats, names = vectors(group)
        flag_outliers(group, stats)
        assign, cents = kmeans(X, min(len(group), max(1, round(k_total * len(group) / n))), rng)
        xy = pca2(X)
        lo, hi = [min(c) for c in zip(*xy)], [max(c) for c in zip(*xy)]
        base = len(clusters)
        for r, a, (x, y) in zip(group, assign, xy):
            r["cluster"] = base + a
            points.append({"id": r["id"], "kind": kind, "title": r["title"], "cluster": base + a,
                           "x": round((x - lo[0]) / (hi[0] - lo[0]), 4) if hi[0] > lo[0] else 0.5,
                           "y": round((y - lo[1]) / (hi[1] - lo[1]), 4) if hi[1] > lo[1] else 0.5})
        for j, c in enumerate(cents):
            members = [i for i, a in enumerate(assign) if a == j]
            clusters.append({"id": base + j, "kind": kind, "size": len(members),
                             "label": cluster_label(kind, [group[i] for i in members], c, names)})
            ranked.append([group[i]["id"] for i in sorted(members, key=lambda i: dist2(X[i], c))])
    graph, ids = {"features": list(FEATURES), "clusters": clusters, "points": points}, [r["id"] for r in recs]
    if n <= 50:
        return graph, ids
    size = min(25, max(15, round(n * 0.2)))  # about 65% cluster representatives (1-2 closest to each centroid), the rest random
    ranked.sort(key=len, reverse=True)
    sample = [m[rank] for rank in range(2) for m in ranked if rank < len(m)][:round(size * 0.65)]
    rest = [i for i in ids if i not in sample]
    rng.shuffle(rest)
    sample += rest[:size - len(sample)]
    return graph, [i for i in ids if i in sample]  # in course order


# ---------- suggestions ----------

def quote_of(value):
    if isinstance(value, str):
        return value
    return str(d(value).get("problem") or d(value).get("work") or "")


def locate(text, by_id):
    """The record and field a finding names: 'T03.2/practice/4', 'T03/review[1]', 'T02.1: explanation 160 words'.
    Returns (record id, field path such as 'practice.4', quoted text) or None when no record id appears."""
    parts = [p.strip(".:,;'\"()") for p in re.split(r"[/\[\]\s]+", str(text or ""))]
    at = next((i for i, p in enumerate(parts) if p in by_id), None)
    if at is None:
        return None
    value, path = by_id[parts[at]], []
    for p in (s for p in parts[at + 1:] for s in p.split(".") if s):
        if isinstance(value, list) and p.isdigit() and int(p) < len(value):
            value = value[int(p)]
        elif isinstance(value, dict) and p in value:
            value = value[p]
        else:
            break  # the rest is prose ("explanation 160 words") or a path this record does not have
        path.append(p)
    return parts[at], ".".join(path), quote_of(value) if path else ""


def suggestion(source, mode, record_id, field, quote, note):
    key = f"{source}|{record_id}|{field}|{mode}|{note}"
    return {"id": "s_" + hashlib.sha1(key.encode()).hexdigest()[:12], "mode": mode, "record_id": record_id,
            "field": field, "quote": quote, "note": note, "source": source}  # no status: a rerun keeps the reviewer's


def check_suggestions(report, by_id):
    """Blind-solve mismatches, facts not supported, leaks and form lines from course-checker's check-report.json."""
    found = []  # (where, mode, note, claim)
    for m in map(d, l(d(report.get("blind_solve")).get("mismatches"))):
        why = f" {m['why']}" if m.get("why") else ""
        found.append((m.get("item"), MISMATCH.get(m.get("verdict"), "blind-solve mismatch"),
                      f"Key {m.get('key')}, checker answered {m.get('mine')} ({m.get('verdict')}).{why}", None))
    for f in map(d, l(report.get("facts"))):
        if f.get("verdict") != "supported":
            found.append((f.get("where"), f"{f.get('verdict')} fact",
                          f"{f.get('claim')} ({f.get('verdict')}; checked against {f.get('source')})", f.get("claim")))
    for k in map(d, l(report.get("leaks"))):
        found.append((k.get("item"), "prerequisite leak", f"Uses {k.get('construct')}, taught in {k.get('taught_in')}.", None))
    for line in l(report.get("form")):
        found.append((line, "form problem", str(line), None))
    out, skipped = [], 0
    for where, mode, note, claim in found:
        loc = locate(where, by_id)
        if not loc:
            skipped += 1
            continue
        rid, field, quote = loc
        if claim and " ".join(str(claim).split()) in " ".join(quote.split()):
            quote = str(claim)  # the claim is verbatim in the field: highlight just the claim
        out.append(suggestion("course-checker", mode, rid, field, quote, note))
    return out, skipped


def validator_suggestions(text, by_id):
    out, skipped = [], 0
    for line in text.splitlines():
        m = re.match(r"\s*(ERROR|WARN)\s+(.*)", line)
        if m:
            loc = locate(m[2], by_id)
            if loc:
                out.append(suggestion("validator", "validator error" if m[1] == "ERROR" else "validator warning", *loc, m[2].strip()))
            else:
                skipped += 1  # course-level lines ("size: ...") name no record
    return out, skipped


def merge_suggestions(old, new):
    """Upsert by id. A suggestion pushed without a status keeps the one already recorded (accepted, dismissed)."""
    by_id = {s.get("id"): s for s in old if isinstance(s, dict)}
    for s in new:
        if not isinstance(s, dict):
            continue
        s = {**s, "id": s.get("id") or "s_" + hashlib.sha1(json.dumps(s, sort_keys=True, default=str).encode()).hexdigest()[:12]}
        prev = by_id.get(s["id"], {})
        by_id[s["id"]] = {**prev, **s, "status": s.get("status") or prev.get("status") or "pending"}
    return list(by_id.values())


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("course")
    ap.add_argument("--out", required=True, help="the error_discovery_data folder")
    ap.add_argument("--check-report")
    ap.add_argument("--transcript")
    ap.add_argument("--validator", help="validate_course.py output saved to a file")
    a = ap.parse_args()

    course = json.loads(Path(a.course).read_text(encoding="utf-8"))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    recs = course_records(course)
    graph, sample = cluster_and_sample(recs, random.Random(7))
    by_id = {r["id"]: r for r in recs}  # findings name course records only, never the build trace
    if a.transcript:
        recs.append(trace_record(a.transcript))
        sample.append("build")  # one record, the whole build: always reviewed
        graph["points"].append({"id": "build", "kind": "trace", "title": "Build transcript", "cluster": None, "x": None, "y": None})

    seeded, skipped = [], 0
    if a.check_report:
        s, n = check_suggestions(d(json.loads(Path(a.check_report).read_text(encoding="utf-8"))), by_id)
        seeded, skipped = seeded + s, skipped + n
    if a.validator:
        s, n = validator_suggestions(Path(a.validator).read_text(encoding="utf-8"), by_id)
        seeded, skipped = seeded + s, skipped + n

    # a rerun keeps what the review already touched: pushed samples and annotated records stay in the sample
    ann_path = out / "annotations.json"
    try:
        annotated = [x.get("record_id") for x in l(read_json(ann_path, [])) if isinstance(x, dict)]
    except ValueError:
        annotated = []
    keep = l(d(read_json(out / "samples.json", {})).get("sample")) + annotated
    sample += [x for x in dict.fromkeys(keep) if x in by_id and x not in sample]

    meta = {k: course.get(k) for k in ("title", "audience", "target_hours", "answer_format", "entry_assumptions",
                                       "exit_competencies", "fixtures")}
    meta.update(dataset=str(out.resolve()), course_path=str(Path(a.course).resolve()),
                prepared=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    write_json(out / "samples.json", {"meta": meta, "sample": sample, "records": recs})
    write_json(out / "graph.json", graph)
    write_json(out / "suggestions.json", merge_suggestions(l(read_json(out / "suggestions.json", [])), seeded))
    if not (out / "patterns.json").exists():
        write_json(out / "patterns.json", {})
    if not ann_path.exists():
        write_json(ann_path, [])

    kinds = Counter(r["kind"] for r in recs)
    print(f"{len(recs)} records ({kinds['kp']} knowledge points, {kinds['topic']} topics, {kinds['trace']} trace), "
          f"sample {len(sample)}, {len(graph['clusters'])} clusters, {len(seeded)} suggestions seeded"
          + (f", {skipped} findings name no record" if skipped else "") + f". Data: {out}")


if __name__ == "__main__":
    main()
