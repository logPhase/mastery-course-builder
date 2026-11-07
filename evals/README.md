# Evals

These evals answer one question: does the `course-builder` agent, with the `mastery-course-builder` skill, produce a
course a learner can trust and learn from?

## How the suite is built

1. **Real runs first.** The agent builds courses for real briefs. Each run keeps its transcript, `course.json`,
   `build-report.md` and the `course-checker` report.
2. **Error analysis.** A person reads the runs and the learner's feedback, writes down what went wrong, and groups the
   notes into failure modes.
3. **One grader per failure mode.** A code grader when a rule can be checked mechanically (the validator, answer-key
   checks, word limits), an LLM grader when it needs judgement (does each knowledge point add exactly one difficulty,
   does an item test understanding rather than recall).
4. **Validated graders.** Each LLM grader is checked against human labels before its score counts.

## Cases

Public cases live in this folder. A private case, for example one built from a client's internal documents, lives
outside the repository and runs with `--eval-dir` pointing at its folder, with `--no-publish` so its report stays
local.
