---
name: mastery-course-builder
description: Build a mastery-learning course (prerequisite knowledge graph, small topics, worked examples, practice, spaced/interleaved review, diagnostic) using Math Academy's evidence-based pedagogy. Use when designing, generating or auditing a course, curriculum or lesson sequence.
---

# Mastery Course Builder

The output is a `course.json` that a tutor agent or app can run. It holds a prerequisite graph of small topics, the full content of every topic, and the delivery rules that gate progress, schedule review and trigger remediation.

Sources: mathacademy.com/pedagogy, mathacademy.com/how-our-ai-works, J. Skycak's *The Math Academy Way* and "Individualized Spaced Repetition in Hierarchical Knowledge Structures", Bloom (1984), Kulik et al. (1990). **[MA]** marks a number taken from Math Academy. **[default]** marks a number this skill chose, because Math Academy keeps those values proprietary.

## Why this design

Bloom (1984) found that one-on-one tutoring beats classroom teaching by about 2σ: the average tutored student outscored 98% of the class. A tutor checks prerequisites, explains briefly, makes the student work, corrects at once, and moves on only when the skill is solid. Mastery learning on its own recovers part of that gain. In meta-analysis it averages +0.5σ, and the gain grows with a higher bar: +0.64σ at a 91–100% criterion vs +0.44 to +0.49σ at 70–90% (Kulik 1990).

Math Academy's "AI" is not an LLM. It is a hand-built expert graph plus a scheduler. The steps are cut small enough for every learner, every dependency is encoded, and software does the tutor's bookkeeping. **You build the graph and the content, and their quality caps everything downstream.**

## Principles → required design → reason

| # | Principle | What the course must do | Why |
|---|---|---|---|
| 1 | Mastery learning | No topic is taught until all its prerequisites pass. Every learner meets the same bar; only time varies. | A missing prerequisite pushes the new topic past working-memory capacity, and the gaps compound. |
| 2 | Minimise cognitive load | Each topic has 2–4 knowledge points (KPs) of rising difficulty, and each KP adds **exactly one** new difficulty. That is about 10x finer than textbooks **[MA]** (calculus: ~300 topics × ~3 KPs vs ~100 sections). | Working memory holds about 4 new items. Smaller stairs let more learners reach the top. |
| 3 | Worked examples | Every KP opens with a fully worked example whose steps sit under subgoal labels. Add a diagram when the idea is spatial (dual coding). | Novices learn more from studying solutions than from solving cold. Subgoal labels show the structure. |
| 4 | Active learning / deliberate practice | Give the minimum explanation, then problems within minutes. Budget about 7x more time solving than reading **[MA]**. | The feeling of learning is not learning. Passive content feels productive and isn't. |
| 5 | Direct instruction | Show the method explicitly. Give novices no "discover it" tasks. Treat struggle as a signal to step back, not as a teaching device. | Minimal guidance underperforms for novices (Kirschner, Sweller & Clark 2006). |
| 6 | Automaticity | Low-level skills that later topics lean on get practice and review until they are fast, not just correct. | Automatic skills free working memory for the higher-level step. |
| 7 | Layering | Every non-foundation topic exercises earlier topics, so its problems contain the component skills. | Each reuse is a new connection and an implicit review. |
| 8 | Non-interference | Confusable topics are kept apart, and dissimilar topics are interleaved. | Similar material learned close together interferes in recall. |
| 9 | Spaced repetition | Every topic is reviewed at expanding intervals. An advanced topic counts as partial review of the topics it encompasses. | Spacing slows forgetting. Massed practice has little long-term benefit. |
| 10 | Interleaving | Practice inside a lesson is blocked. Reviews and quizzes mix topics. | Mixed sets train the learner to *choose* the method, not just run it. |
| 11 | Testing effect | Retrieval is frequent and low-stakes. Quizzes are closed-book and timed. | Retrieval strengthens memory more than rereading does. |
| 12 | Targeted remediation | A failure triggers practice on that KP's key prerequisites, even several levels back, not easier hints. | The cause is usually a weak component skill. |

**Fit check:** the method needs skills with checkable answers, as in math, programming, SQL, science, accounting and grammar. In judgement domains such as writing or strategy, make each KP's practice rubric-checkable and tell the user that the mastery gate is weaker there.

## Build process

Work in this order. Don't write content before the graph is fixed.

### 1. Scope
- `exit_competencies`: the things the learner can *do* at the end. Each one needs an `id` and a checkable `statement`.
- `entry_assumptions`: what the learner is assumed to know already. Anything shaky becomes a `foundation` topic.
- Size: about 20 min per topic all-in **[MA]**, counting the lesson, its later reviews and its share of quizzes. So topics ≈ `target_hours` × 3. That count is approximate: spacing rules may add one. `est_minutes` is the **first lesson only**, typically 8–25.
- `answer_format`: how answers are written so a machine can compare them. Define it once per course. Cover:
  - numbers: rounding and units
  - exact strings
  - choice letters
  - result sets: row and column separators, NULL rendering, float precision
  - outputs that end in an error, e.g. a last line of `Error: KeyError`
  - write-code items: give each item `"kind": "code"`, put a reference solution in `answer`, and add `check`, a test plus its expected output. Grading runs the learner's code against `check`, so the uniqueness rule applies to the output, not the code text. Every other item has the default `"kind": "answer"`.
- `fixtures`: shared context the problems reference, such as a sample database schema with rows, a dataset, starter code or a glossary. Fixtures are read-only, and every item runs on a fresh copy. Plant edge cases in them on purpose: NULLs, orphans, ties, empty groups. Where reusing a fixture would repeat surface values, the item defines its own small local data.
- Ask the user for target hours and learner level if they are unknown. Otherwise state your assumptions.

### 2. Graph
- Topics are verb phrases naming one method: "Solve two-step linear equations with integer coefficients", not "Equations".
- **Split** a topic that needs more than 4 KPs, more than 25 minutes for the first lesson, or a worked example over 8 steps. **Merge** a topic that can't yield 2 distinct KPs.
- `prerequisites` are **direct only**, never transitive. A is a prerequisite of B if a learner can't follow B's worked example without A.
- `encompasses` is a list of `[{id, weight}]`. B encompasses A if doing B's problems practises A. Weight 1.0 means every B problem fully exercises A; weight 0.2 means about 20% of B's problems touch A. Set a weight only when it is non-trivial and A is within 2 prerequisite hops of B. Not every prerequisite is encompassed.
- `confusable_with` lists topics with a similar surface but a different method. Use `entry:<skill>` for an assumed-known skill, e.g. HAVING is confusable with `entry:WHERE`. Use the same literal string in `discriminates`.
- `strand` is a short unit tag used to interleave the sequence.
- `serves` lists the exit-competency ids the topic leads to. Mark enrichment topics `core: false`.
- `foundation: true` marks topics with no prerequisites inside the course.

### 3. Sequence
`sequence` is the default order for non-adaptive delivery. It respects prerequisites, keeps confusable topics at least 3 positions apart, avoids 4 or more consecutive topics from one strand, and puts core topics before enrichment. An adaptive runtime instead offers the learner a choice among unlocked topics (see Delivery).

### 4. Content (per topic)
Each KP has these fields:
- `label`: the subgoal label.
- `adds`: the one new difficulty this KP introduces over the previous one, in one phrase. If you need "and", split the KP.
- `explanation`: at most 150 words, covering only what the example needs. Leave out history, motivation and analogy unless they carry the method.
- `worked_example`: `problem`, `steps` as `[{subgoal, work}]`, `answer`, and optionally a `diagram` description precise enough to draw.
- `practice`: at least 5 items that use the worked example's method with new surface values or context. Each item has `problem`, `answer` (in `answer_format`) and `solution` (full steps). Five is a *pool*, not a dose: learners usually pass after 2–3, but halts and retries need fresh items.
- `misconceptions`: 1–2 real errors. Solutions point out where each error goes wrong. For multiple choice, the distractors are these errors.
- `key_prerequisites`: the ancestor topics this KP actually uses. Remediation targets these.

KP1 is the simplest case. Each later KP adds one complication, and the last KP reaches the hardest case the topic promises. Together the KPs cover every problem type that a learner who "knows the topic" should be able to solve.

Each topic also has:
- `review`: at least 3 items that mix all the KPs. They come with no worked example and no hints, in mixed KP order, and one item may combine two KPs. For each confusable pair, at least one review item makes the learner choose between the two methods and tags them with `"discriminates": [idA, idB]`. That item goes in the review of whichever of the two topics comes **later** in the sequence, so it never tests something not yet taught.
- `diagnostic`: 1 item testing this topic's own method at last-KP level, without stacking other topics' complexity on top. It should take under 2 minutes.

**Uniqueness:** every answer must be the only correct one. For result sets, require ordering, including a tiebreaker for top-N. For numbers, state the rounding. For free text, prefer multiple choice or an exact short form.

**Correctness pass (mandatory, because LLM answer keys fail silently):**
1. **Execute** everything executable against `fixtures`: arithmetic, algebra (sympy), code, SQL (sqlite3). Compare each result to its key, and for `kind: code` items run the reference solution against `check`. Make sure the checker works by planting one wrong key and confirming it gets caught.
2. **Cross-check** what execution cannot see:
   - The task wording matches the reference code or data, so the problem says what the code actually does.
   - Every factual claim in explanations, misconceptions and solutions is true. Execute the claim where possible.
   - Every solution states the final answer.
   - Anything not executable is blind-solved from the problem text alone, without the key; use a separate subagent if one is available (this plugin ships one: `mastery-course-builder:course-checker`).
3. **Prerequisite-leak scan:** for each topic, list the constructs it teaches. Then scan every item for any construct that is not taught by the topic or its ancestors and is not an entry assumption. A leak means either the item gets rewritten or a prerequisite edge gets added.
4. **Read** every problem in full for truncated or half-edited text. Also grep for `TODO`, `...`, `???` and text ending in a dash.

Report the count for each step: keys fixed, cross-check fixes, and leaks fixed.

Writing the content is most of the cost: about 7 items per KP, each with a solution. Keep solutions to the essential steps. For any course over about 6 topics, write the content in a build script or one file per topic and assemble `course.json`. First run `python3 validate_course.py course.json --graph-only` on the graph and sequence alone. Then fill the content strand by strand, running the full validator after each strand.

### 5. Validate
Use `validate_course.py` from this skill's folder (if it is missing, save it from the appendix), and run `python3 validate_course.py course.json`. Fix every ERROR, then fix or justify every WARN. After that, run the manual checklist:
- [ ] A learner who has mastered *exactly* the listed prerequisites can follow each worked example. If not, an edge is missing or the step is too big.
- [ ] Each KP's `adds` really is one difficulty, and its practice exercises exactly that.
- [ ] Practice items share their worked example's method but are not copies of it.
- [ ] Explanations contain no motivational filler.
- [ ] Each non-foundation topic's practice actually uses its prerequisites (layering).

Report to the user:
- the validator summary line
- the counts from the correctness pass
- every WARN you kept, with its reason
- your assumptions

## Delivery (store in `course.json` → `delivery`; a tutor agent applies it)

```json
{
  "kp_pass": "2 consecutive correct [MA]",
  "kp_halt": "5 items without passing [default]",
  "feedback": "show full solution after every item [MA]",
  "on_halt": "switch to an unrelated unlocked topic; retry later. Second halt on the same KP -> remedial review of its key_prerequisites, then retry [MA]",
  "unlock": "topic unlocks when all prerequisites passed; offer 2-4 unlocked, mutually non-confusable topics [MA]",
  "review_intervals_days": [1, 3, 7, 16, 35, 75],
  "review_size": "3-5 items [MA]; pass at >=75% [default]; pass -> next interval; fail -> back 2 intervals + review key prerequisites [default]",
  "implicit_credit": "when a topic passes a lesson or review, each topic it encompasses gains weight * min(1, days_since_its_last_rep / its_current_interval); accumulated credit >= 1 counts as a passed review; credit cascades down encompassings [MA mechanism, default formula]",
  "compression": "when choosing the next task, prefer lessons or reviews whose encompassings clear the most due reviews [MA]",
  "struggling_topic": "after any halt or failed review on a topic, it gets no implicit credit: explicit reviews only [MA]",
  "quiz": "every ~150 min of work [MA]; 5-8 items [default] sampled from learned topics, down-weighting recently quizzed topics and topics encompassed by other candidates; closed-book, timed; each miss -> immediate remedial review of that topic; tune difficulty so the average is ~80% [MA]",
  "diagnostic": "test the topics that encompass the most others first; correct -> topic and ancestors known; wrong -> topic and descendants unknown; slow correct counts half; borderline -> 'conditionally complete', fall back if the learner fails; prefer under-placing [MA]",
  "learner_rules": "no looking back at examples during reviews and quizzes; steady daily practice beats bursts; 1 XP = 1 focused minute if gamified [MA]"
}
```

## course.json shape

```json
{
  "title": "...", "audience": "...", "target_hours": 3,
  "entry_assumptions": ["..."],
  "exit_competencies": [{"id": "C1", "statement": "..."}],
  "answer_format": "...",
  "fixtures": {"...": "schema, dataset, starter code"},
  "sequence": ["T01", "T02"],
  "delivery": {"...": "block above"},
  "topics": [{
    "id": "T02", "title": "verb phrase", "strand": "joins", "core": true, "foundation": false,
    "est_minutes": 15, "serves": ["C1"],
    "prerequisites": ["T01"], "encompasses": [{"id": "T01", "weight": 1.0}],
    "confusable_with": ["T03", "entry:WHERE"],
    "knowledge_points": [{
      "id": "T02.1", "label": "...", "adds": "...", "explanation": "...",
      "worked_example": {"problem": "...", "steps": [{"subgoal": "...", "work": "..."}], "answer": "...", "diagram": null},
      "practice": [{"kind": "answer", "problem": "...", "answer": "...", "solution": "..."}],
      "misconceptions": ["..."], "key_prerequisites": ["T01"]
    }],
    "review": [{"problem": "...", "answer": "...", "solution": "...", "discriminates": ["T02", "T03"]}],
    "diagnostic": {"problem": "...", "answer": "...", "solution": "..."}
  }]
}
```

## Appendix: validate_course.py

```python
#!/usr/bin/env python3
"""Structural validator for mastery-course-builder course.json. Usage: python3 validate_course.py course.json [--graph-only]
Exit 0 = no errors (warnings may remain). Checks structure only; the manual checklist still applies."""
import json, sys
from collections import defaultdict

E, W = [], []
def err(m): E.append(m)
def warn(m): W.append(m)
def item_ok(q): return isinstance(q, dict) and all(q.get(k) not in (None, "") for k in ("problem", "answer", "solution"))
def pk(a, b): return tuple(sorted((a, b)))

c = json.load(open(sys.argv[1]))
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
print(f"topics={n} kps={sum(len(t.get('knowledge_points') or []) for t in T.values())} "
      f"depth={max([dep(x) for x in T] or [0])} with_encompassings={enc} ({100*enc//max(n,1)}%) "
      f"est_all_in_hours={n*20/60:.1f}")
for m in E: print("ERROR  ", m)
for m in W: print("WARN   ", m)
print("RESULT:", "FAIL" if E else "PASS", f"({len(E)} errors, {len(W)} warnings)")
sys.exit(1 if E else 0)
```
