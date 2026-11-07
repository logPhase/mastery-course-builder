"""Behaviour of skills/mastery-course-builder/validate_course.py on small courses. Run: python3 -m unittest discover tests"""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

VALIDATOR = Path(__file__).resolve().parent.parent / "skills" / "mastery-course-builder" / "validate_course.py"


def item(n):
    return {"problem": f"Problem {n}?", "answer": f"A{n}", "solution": f"Work it out. A{n}"}


def kp(tid, i, prereqs):
    return {
        "id": f"{tid}.{i}", "label": f"Step {i}", "adds": f"difficulty {i}",
        "explanation": "Short explanation of the method.",
        "worked_example": {"problem": "Example?", "steps": [{"subgoal": "Set up", "work": "x"}, {"subgoal": "Solve", "work": "y"}], "answer": "y"},
        "practice": [item(n) for n in range(5)],
        "misconceptions": ["A common error."],
        "key_prerequisites": list(prereqs),
    }


def topic(tid, prereqs=(), foundation=False, strand="s1", serves=("C1",)):
    return {
        "id": tid, "title": f"Do {tid}", "strand": strand, "core": True, "foundation": foundation,
        "est_minutes": 15, "serves": list(serves), "prerequisites": list(prereqs), "encompasses": [],
        "confusable_with": [],
        "knowledge_points": [kp(tid, 1, prereqs), kp(tid, 2, prereqs)],
        "review": [item(n) for n in range(3)],
        "diagnostic": item(9),
    }


def course():
    return {
        "title": "Tiny course", "audience": "testers", "target_hours": 1,
        "entry_assumptions": ["reading"], "exit_competencies": [{"id": "C1", "statement": "Can do T02."}],
        "answer_format": "exact strings", "fixtures": {}, "delivery": {"kp_pass": "2 consecutive correct"},
        "sequence": ["T01", "T02", "T03"],
        "topics": [topic("T01", foundation=True, strand="a"), topic("T02", ["T01"], strand="b"), topic("T03", ["T02"], strand="a")],
    }


def run(c, *flags):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "course.json"
        p.write_text(json.dumps(c))
        r = subprocess.run([sys.executable, str(VALIDATOR), str(p), *flags], capture_output=True, text=True)
    return r.returncode, r.stdout


class ValidateCourse(unittest.TestCase):
    def test_a_complete_course_passes(self):
        code, out = run(course())
        self.assertEqual(code, 0, out)
        self.assertIn("RESULT: PASS (0 errors", out)
        self.assertIn("topics=3 kps=6 depth=3", out)

    def test_a_prerequisite_cycle_fails(self):
        c = course()
        c["topics"][0]["prerequisites"] = ["T03"]
        c["topics"][0]["foundation"] = False
        code, out = run(c)
        self.assertEqual(code, 1)
        self.assertIn("ERROR   cycle:", out)

    def test_a_transitive_prerequisite_warns(self):
        c = course()
        c["topics"][2]["prerequisites"] = ["T01", "T02"]
        code, out = run(c)
        self.assertEqual(code, 0, out)
        self.assertIn("WARN    T03: prerequisite T01 is transitive", out)

    def test_confusable_topics_next_to_each_other_fail(self):
        c = course()
        c["topics"][1]["confusable_with"] = ["T03"]
        code, out = run(c)
        self.assertEqual(code, 1)
        self.assertIn("ERROR   sequence: confusable T02/T03 fewer than 3 apart", out)
        self.assertIn("ERROR   confusable pair T02/T03: no review item", out)

    def test_too_few_practice_items_fail(self):
        c = course()
        c["topics"][1]["knowledge_points"][0]["practice"] = [item(1)]
        code, out = run(c)
        self.assertEqual(code, 1)
        self.assertIn("ERROR   T02.1: 1 practice items (need >=5)", out)

    def test_graph_only_ignores_missing_content(self):
        c = copy.deepcopy(course())
        for t in c["topics"]:
            t.pop("knowledge_points"); t.pop("review"); t.pop("diagnostic")
        self.assertEqual(run(c)[0], 1)
        code, out = run(c, "--graph-only")
        self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()
