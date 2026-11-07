#!/usr/bin/env python3
"""Structural validator for mastery-course-builder course.json. Usage: python3 validate_course.py course.json [--graph-only]
Exit 0 = no errors (warnings may remain). Checks structure only; the manual checklist still applies."""
import json, os, sys
from collections import defaultdict

E, W = [], []
def err(m): E.append(m)
def warn(m): W.append(m)
def item_ok(q): return isinstance(q, dict) and all(q.get(k) not in (None, "") for k in ("problem", "answer", "solution"))
def pk(a, b): return tuple(sorted((a, b)))

c = json.load(open(sys.argv[1]))
HERE = os.path.dirname(os.path.abspath(sys.argv[1]))  # diagram paths are relative to course.json
DIAGRAMS = 0
GRAPH_ONLY = "--graph-only" in sys.argv  # validate graph + sequence before writing content
T = {}
for t in c.get("topics", []):
    if t.get("id") in T: err(f"duplicate topic id {t.get('id')}")
    T[t.get("id")] = t
for k in ("title", "exit_competencies", "entry_assumptions", "sequence", "answer_format", "delivery"):
    if not c.get(k): err(f"course missing '{k}'")

# graph: refs exist, DAG, direct prerequisites only
children = defaultdict(list)
for tid, t in T.items():
    for p in t.get("prerequisites", []):
        if p not in T: err(f"{tid}: unknown prerequisite {p}")
        else: children[p].append(tid)
state, CYCLE = {}, False
def visit(n, stack):
    global CYCLE
    if state.get(n) == 1: err(f"cycle: {' -> '.join(stack + [n])}"); CYCLE = True; return
    if state.get(n) == 2: return
    state[n] = 1
    for p in T[n].get("prerequisites", []):
        if p in T: visit(p, stack + [n])
    state[n] = 2
for n in T: visit(n, [])
anc, depth = {}, {}
def ancestors(n):
    if CYCLE: return set(T)
    if n not in anc:
        s = set()
        for p in T[n].get("prerequisites", []):
            if p in T: s |= {p} | ancestors(p)
        anc[n] = s
    return anc[n]
def dep(n):
    if CYCLE: return 0
    if n not in depth: depth[n] = 1 + max([dep(p) for p in T[n].get("prerequisites", []) if p in T] or [0])
    return depth[n]
if not CYCLE:
    for tid, t in T.items():
        ps = [p for p in t.get("prerequisites", []) if p in T]
        for p in ps:
            if any(p in ancestors(q) for q in ps if q != p):
                warn(f"{tid}: prerequisite {p} is transitive (already implied); list direct prerequisites only")

# confusable pairs: symmetric; 'entry:<skill>' allowed for assumed-known skills
pairs = set()
for tid, t in T.items():
    for x in t.get("confusable_with", []):
        if not x.startswith("entry:") and x not in T: err(f"{tid}: confusable_with unknown {x}")
        elif x != tid: pairs.add(pk(tid, x))
seqpos = {x: i for i, x in enumerate(c.get("sequence", []))}
covered = set()
for tid, t in T.items():
    for q in t.get("review", []):
        d = q.get("discriminates", []) if isinstance(q, dict) else []
        for x in d:
            if x in T and seqpos.get(x, -1) > seqpos.get(tid, -1):
                err(f"{tid} review: discriminates {x}, which comes later in sequence; put the item in the later topic's review")
        covered |= {pk(a, b) for a in d for b in d if a != b}
for a, b in sorted(pairs):
    if not GRAPH_ONLY and (a, b) not in covered: err(f"confusable pair {a}/{b}: no review item whose 'discriminates' lists both")

# per-topic content
comp_ids = {x.get("id") for x in c.get("exit_competencies", [])}
for tid, t in T.items():
    m = t.get("est_minutes", 0)
    if not 8 <= m <= 25: warn(f"{tid}: est_minutes={m} (first lesson) outside 8-25; split or merge")
    if not t.get("prerequisites") and not t.get("foundation"):
        warn(f"{tid}: no prerequisites but not marked foundation")
    for e in t.get("encompasses", []):
        if e.get("id") not in T: err(f"{tid}: encompasses unknown {e.get('id')}")
        elif e["id"] not in ancestors(tid): warn(f"{tid}: encompasses non-ancestor {e['id']} (allowed, check intent)")
        if not 0 < e.get("weight", 0) <= 1: err(f"{tid}: encompass weight for {e.get('id')} must be in (0,1]")
    if GRAPH_ONLY: continue
    kps = t.get("knowledge_points") or []
    if not 2 <= len(kps) <= 4: err(f"{tid}: {len(kps)} knowledge points (need 2-4)")
    for i, kp in enumerate(kps):
        kid = kp.get("id", f"{tid}.{i+1}")
        if not kp.get("label"): err(f"{kid}: missing subgoal label")
        if not kp.get("adds"): err(f"{kid}: missing 'adds' (the one new difficulty this KP introduces)")
        elif any(w in f" {kp['adds']} " for w in (";", " plus ", " as well as ", " and also ")):
            warn(f"{kid}: 'adds' looks like more than one difficulty: {kp['adds']!r}")
        words = len((kp.get("explanation") or "").split())
        if words == 0: err(f"{kid}: missing explanation")
        elif words > 150: warn(f"{kid}: explanation {words} words (>150); cut to minimum needed")
        we = kp.get("worked_example") or {}
        steps = we.get("steps") or []
        if not we.get("problem") or not we.get("answer"): err(f"{kid}: worked example needs problem and answer")
        if len(steps) < 2: err(f"{kid}: worked example needs >=2 steps")
        if any(not s.get("subgoal") for s in steps): err(f"{kid}: every worked-example step needs a subgoal label")
        if len(steps) > 8: warn(f"{kid}: {len(steps)} steps; KP may be too big")
        d = we.get("diagram")
        if d not in (None, ""):
            if not isinstance(d, str) or not d.endswith(".drawio"):
                err(f"{kid}: diagram must be the path of a .drawio file, not a description of a picture")
            elif not os.path.isfile(os.path.join(HERE, d)): err(f"{kid}: diagram file {d} not found")
            elif "<mxGraphModel" not in open(os.path.join(HERE, d), encoding="utf-8", errors="replace").read():
                err(f"{kid}: {d} is not uncompressed draw.io XML")
            else: DIAGRAMS += 1
        pr = kp.get("practice") or []
        if len(pr) < 5: err(f"{kid}: {len(pr)} practice items (need >=5)")
        for j, q in enumerate(pr):
            if not item_ok(q): err(f"{kid} practice[{j}]: needs problem, answer, solution")
        if not kp.get("misconceptions"): warn(f"{kid}: no misconceptions listed")
        elif len(kp["misconceptions"]) > 2: warn(f"{kid}: {len(kp['misconceptions'])} misconceptions (keep the 1-2 most common)")
        for j, q in enumerate(pr):
            a = str(q.get("answer", "")) if isinstance(q, dict) else ""
            if item_ok(q) and len(a) <= 40 and a.split("\n")[-1].strip() not in str(q["solution"]):
                warn(f"{kid} practice[{j}]: solution never states the final answer {a!r}")
        for k in kp.get("key_prerequisites", []):
            if k not in T: err(f"{kid}: unknown key prerequisite {k}")
            elif k not in ancestors(tid): err(f"{kid}: key prerequisite {k} is not an ancestor of {tid}")
        if t.get("prerequisites") and not kp.get("key_prerequisites"):
            warn(f"{kid}: no key_prerequisites; remediation has no target and layering is unclear")
    rv = t.get("review") or []
    if len(rv) < 3: err(f"{tid}: {len(rv)} review items (need >=3)")
    for j, q in enumerate(rv):
        if not item_ok(q): err(f"{tid} review[{j}]: needs problem, answer, solution")
    if not item_ok(t.get("diagnostic")): err(f"{tid}: diagnostic needs problem, answer, solution")
    for x in t.get("serves", []):
        if x not in comp_ids: err(f"{tid}: serves unknown competency {x}")
    if t.get("core", True) and not children[tid] and not t.get("serves"):
        warn(f"{tid}: core leaf topic serves no exit competency (set core=false or link it)")
served = {x for t in T.values() for x in t.get("serves", [])}
for cid in (comp_ids - served if not GRAPH_ONLY else set()): err(f"exit competency {cid} served by no topic")

# sequence
seq = c.get("sequence", [])
if set(seq) != set(T) or len(seq) != len(T): err("sequence must list every topic exactly once")
else:
    pos = {x: i for i, x in enumerate(seq)}
    for tid, t in T.items():
        for p in t.get("prerequisites", []):
            if p in pos and pos[p] > pos[tid]: err(f"sequence: {tid} before its prerequisite {p}")
    for a, b in pairs:
        if a in pos and b in pos and abs(pos[a] - pos[b]) < 3: err(f"sequence: confusable {a}/{b} fewer than 3 apart")
    enrich = [x for x in seq if T[x].get("core") is False]
    for x in seq:
        if T[x].get("core", True) and any(pos[e] < pos[x] and e not in ancestors(x) for e in enrich):
            warn(f"sequence: core {x} placed after unrelated enrichment; put core first"); break
    strands, run = [T[x].get("strand") for x in seq], 1
    for i in range(1, len(strands)):
        run = run + 1 if strands[i] and strands[i] == strands[i-1] else 1
        if run == 4: warn(f"sequence: 4+ consecutive topics from strand '{strands[i]}' near {seq[i]}; interleave")

# size: ~20 min per topic all-in (lesson + reviews + quizzes)
n, hours = len(T), c.get("target_hours")
if hours and n and not 0.6 <= (n * 20) / (hours * 60) <= 1.5:
    warn(f"size: {n} topics x ~20 min all-in = {n*20/60:.1f} h vs target_hours={hours}")
enc = sum(1 for t in T.values() if t.get("encompasses"))
print(f"topics={n} kps={sum(len(t.get('knowledge_points') or []) for t in T.values())} diagrams={DIAGRAMS} "
      f"depth={max([dep(x) for x in T] or [0])} with_encompassings={enc} ({100*enc//max(n,1)}%) "
      f"est_all_in_hours={n*20/60:.1f}")
for m in E: print("ERROR  ", m)
for m in W: print("WARN   ", m)
print("RESULT:", "FAIL" if E else "PASS", f"({len(E)} errors, {len(W)} warnings)")
sys.exit(1 if E else 0)
