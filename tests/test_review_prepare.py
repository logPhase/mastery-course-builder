"""Behaviour of evals/review/prepare.py and server.py on small courses. Run: python3 -m unittest discover tests"""
import json
import subprocess
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # also when run as a file, not only by discover
from test_validate_course import course, topic  # noqa: E402

REVIEW = Path(__file__).resolve().parent.parent / "evals" / "review"
FILES = {"samples.json", "graph.json", "patterns.json", "suggestions.json", "annotations.json"}


def mc_course():
    """The validator tests' course, with multiple-choice items on T02.1."""
    c = course()
    for q in c["topics"][1]["knowledge_points"][0]["practice"]:
        q.update(choices=["one", "two", "three"], answer="B")
    return c


def transcript():
    events = [
        {"type": "system", "subtype": "init", "model": "claude-test", "cwd": "/tmp"},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Reading the brief."}]}},
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "cat brief.md"}}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": "# Brief"}]}},
        {"type": "result", "subtype": "success", "result": "Done.", "num_turns": 2},
    ]
    return "\n".join(json.dumps(e) for e in events)


def prepare(out, c, check=None, validator=None, trace=None):
    d = Path(out).parent
    (d / "course.json").write_text(json.dumps(c))
    args = [sys.executable, str(REVIEW / "prepare.py"), str(d / "course.json"), "--out", str(out)]
    for flag, name, text in (("--check-report", "check-report.json", check and json.dumps(check)),
                             ("--validator", "validator.txt", validator), ("--transcript", "transcript.jsonl", trace)):
        if text:
            (d / name).write_text(text)
            args += [flag, str(d / name)]
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode:
        raise AssertionError(r.stderr)
    return {name: json.loads((Path(out) / name).read_text()) for name in FILES}


class Prepare(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "error_discovery_data"

    def tearDown(self):
        self.tmp.cleanup()

    def test_writes_the_five_files_with_one_record_per_knowledge_point_and_topic(self):
        data = prepare(self.out, mc_course(), trace=transcript())
        self.assertEqual({p.name for p in self.out.iterdir()}, FILES)
        kinds = {}
        for r in data["samples.json"]["records"]:
            kinds.setdefault(r["kind"], []).append(r["id"])
        self.assertEqual(kinds["kp"], ["T01.1", "T01.2", "T02.1", "T02.2", "T03.1", "T03.2"])
        self.assertEqual(kinds["topic"], ["T01", "T02", "T03"])
        self.assertEqual(set(data["samples.json"]["sample"]), set(kinds["kp"] + kinds["topic"] + ["build"]))  # 10 records: all
        self.assertEqual(len(data["graph.json"]["points"]), 10)
        self.assertEqual((data["patterns.json"], data["annotations.json"]), ({}, []))
        step = next(r for r in data["samples.json"]["records"] if r["id"] == "build")["steps"][0]
        self.assertEqual([i["type"] for i in step["items"]], ["text", "tool_call", "tool_result"])

    def test_a_rerun_keeps_annotations_and_suggestion_decisions(self):
        check = {"leaks": [{"item": "T03/review/1", "construct": "HAVING", "taught_in": "T09 (later)"}]}
        first = prepare(self.out, mc_course(), check=check)
        self.assertEqual(first["suggestions.json"][0]["status"], "pending")
        mine = [{"id": "a1", "record_id": "T02.1", "quote": "Problem 3?", "note": "too easy"}]
        (self.out / "annotations.json").write_text(json.dumps(mine))
        (self.out / "suggestions.json").write_text(json.dumps([{**first["suggestions.json"][0], "status": "dismissed"}]))
        data = prepare(self.out, mc_course(), check=check)
        self.assertEqual(data["annotations.json"], mine)
        self.assertEqual([s["status"] for s in data["suggestions.json"]], ["dismissed"])

    def test_check_report_and_validator_findings_become_suggestions_on_their_records(self):
        check = {"blind_solve": {"checked": 30, "mismatches": [
            {"item": "T02.1/practice/3", "key": "B", "mine": "C", "verdict": "key_wrong", "why": "three is right"}]}}
        data = prepare(self.out, mc_course(), check=check,
                       validator="RESULT: FAIL\nWARN    T03.2: explanation 160 words (>150); cut to minimum needed\nWARN    size: 3 topics")
        by_source = {s["source"]: s for s in data["suggestions.json"]}
        s = by_source["course-checker"]
        self.assertEqual((s["record_id"], s["field"], s["quote"], s["mode"]), ("T02.1", "practice.3", "Problem 3?", "wrong answer key"))
        v = by_source["validator"]
        self.assertEqual((v["record_id"], v["field"]), ("T03.2", "explanation"))
        self.assertEqual(len(data["suggestions.json"]), 2)  # the size line names no record

    def test_a_large_course_gets_a_sample_of_15_to_25_from_6_to_10_clusters(self):
        c = course()
        c["topics"] = [topic("T01", foundation=True)] + [topic(f"T{i:02}", [f"T{i - 1:02}"], strand=f"s{i % 3}") for i in range(2, 25)]
        for i, t in enumerate(c["topics"]):  # vary the structure so the clusters have something to find
            t["knowledge_points"][0]["practice"] *= 1 + i % 3
            t["knowledge_points"][1]["explanation"] += " More words." * (i % 5)
        c["sequence"] = [t["id"] for t in c["topics"]]
        data = prepare(self.out, c)
        self.assertEqual(len(data["samples.json"]["records"]), 72)
        self.assertTrue(15 <= len(data["samples.json"]["sample"]) <= 25)
        self.assertTrue(6 <= len(data["graph.json"]["clusters"]) <= 10)


class Server(unittest.TestCase):
    def test_samples_and_an_annotation_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "error_discovery_data"
            prepare(out, mc_course())
            with subprocess.Popen([sys.executable, str(REVIEW / "server.py"), "--data", str(out), "--port", "0"],
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True) as proc:
                try:
                    url = proc.stdout.readline().split()[2]  # "Review app: http://127.0.0.1:<port>/ ..."
                    with urllib.request.urlopen(url + "api/samples") as r:
                        self.assertEqual(len(json.load(r)["records"]), 9)
                    note = [{"id": "a1", "record_id": "T01.1", "quote": "Short explanation", "note": "fine", "start": 0, "end": 17}]
                    req = urllib.request.Request(url + "api/annotations", data=json.dumps(note).encode(), method="POST",
                                                 headers={"Content-Type": "application/json"})
                    with urllib.request.urlopen(req) as r:
                        self.assertEqual(r.status, 200)
                    with urllib.request.urlopen(url + "api/annotations") as r:
                        self.assertEqual(json.load(r), note)
                    self.assertEqual(json.loads((out / "annotations.json").read_text()), note)
                finally:
                    proc.terminate()


if __name__ == "__main__":
    unittest.main()
