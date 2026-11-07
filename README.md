# mastery-course-builder

A Claude Code plugin that builds mastery-learning courses the way Math Academy does: a prerequisite graph of small
topics, a worked example for every knowledge point, practice with checked answer keys, spaced and interleaved review,
and a diagnostic. It also ships the evals that check whether the courses it builds are any good.

The plugin has three parts:

- **`mastery-course-builder` skill** (`skills/mastery-course-builder/SKILL.md`). The pedagogy, the build process and
  the `course.json` shape, plus `validate_course.py`, a structural validator.
- **`course-builder` agent** (`agents/course-builder.md`). Builds one course from a brief and your documents, then
  validates it and runs the correctness pass.
- **`course-checker` agent** (`agents/course-checker.md`). Blind-solves every item without seeing the keys, checks
  facts against your sources, and scans for prerequisite leaks. It never edits the course.

## Install

```
/plugin marketplace add logPhase/mastery-course-builder
/plugin install mastery-course-builder@logphase
```

## Build a course

In Claude Code, ask for the agent and give it a brief:

```
Use the course-builder agent. Build a course on SQL GROUP BY and HAVING for analysts who know SELECT and WHERE,
about 2 hours, single-answer multiple choice, from the docs in ./notes. Write it to ./course.
```

Without a session, run the agent directly:

```
claude -p --plugin-dir /path/to/mastery-course-builder --agent mastery-course-builder:course-builder \
	--permission-mode acceptEdits "Build the course described in ./brief.md and write it to ./course"
```

The agent writes `course.json`, one `topics/<id>.json` per topic with the script that assembles them, and
`build-report.md` with the validator result, the correctness-pass counts, the warnings it kept, and its assumptions.

## Check a course

```
python3 skills/mastery-course-builder/validate_course.py course.json              # full check
python3 skills/mastery-course-builder/validate_course.py course.json --graph-only # graph and sequence only
```

The validator checks structure only. The skill's correctness pass and the `course-checker` agent cover answer keys,
facts and leaks.

## Run the evals

The eval suite is being built in `evals/`, error analysis first: run the agent on real cases, read what it gets
wrong, then write one grader per failure mode. `evals/README.md` tracks the cases and graders as they land. The suite
runs with Claude Code's plugin eval runner, `claude plugin eval . --no-publish`.

## Run the tests

```
python3 -m unittest discover tests
```

## Pedagogy

The design follows Math Academy's published pedagogy (mathacademy.com/pedagogy, mathacademy.com/how-our-ai-works),
J. Skycak's *The Math Academy Way*, Bloom (1984) on one-to-one tutoring, and Kulik et al. (1990) on mastery learning.
`SKILL.md` marks every number taken from Math Academy with **[MA]** and every number the skill chose with
**[default]**.

## License

MIT, see `LICENSE`.
