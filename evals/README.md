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

## Review a run (error analysis)

`review/` is the app for step 2: a person reads the course a run built, notes what is wrong in free text, and an agent
groups the notes into failure modes (the `error-discovery` method). Prepare the data, then start the app:

```
python3 skills/mastery-course-builder/validate_course.py runs/r1/course.json > runs/r1/validator.txt
python3 evals/review/prepare.py runs/r1/course.json --out ~/reviews/r1/error_discovery_data \
	--check-report runs/r1/check-report.json --transcript runs/r1/transcript.jsonl --validator runs/r1/validator.txt
python3 evals/review/server.py --data ~/reviews/r1/error_discovery_data     # open http://127.0.0.1:8770/
```

`prepare.py` makes one record per knowledge point, per topic and for the build transcript, clusters them, picks the
first sample (every record when there are 50 or fewer) and seeds agent suggestions from the checker's report and the
validator's WARN and ERROR lines. Running it again keeps the notes, the accepted and dismissed suggestions and the
failure modes. The data folder holds the whole course: when the course is private, keep it outside this repository.

The agent running the review loop reads `annotations.json` (the app writes it) and pushes to the server:
`POST /api/suggestions` with `[{record_id, field, quote, mode, note, source}]` (merged by id; the reviewer's
decisions stay), `POST /api/patterns` with `{mode: {description, count, example_ids, example_quotes}}` where
`example_ids` are annotation ids, and `POST /api/samples` with `samples.json` after adding record ids to `sample`.
`field` is a path in the record such as `practice.4`, and `quote` is text copied from that field.

## Cases

Public cases live in this folder. A private case, for example one built from a client's internal documents, lives in
`evals-private/` at the plugin root, which git ignores, and runs with `claude plugin eval . --eval-dir evals-private
--no-publish`, so neither the case nor its report leaves your machine. The eval runner only reads eval folders
below the plugin.

| Case | What it checks |
|---|---|
| `sql-group-by` | A one-hour SQL course: the files exist, the skill was used, the validator ran and its last run
passed, the SQL items were executed, the items were blind-solved, the report counts leaks, and the build never waited
on background writers with a scheduled wake-up. |

The failure modes found so far, their evidence and their graders are in `failure-modes.md`.
