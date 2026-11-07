---
name: sql-group-by
description: Build a one-hour mastery course on SQL GROUP BY and HAVING; checks that the skill's build process ran and that the course file is valid.
expected_outcome: course/course.json and course/build-report.md exist, the validator's last run passed, the SQL items were executed, and the checker blind-solved the items.
tags: [build, public, sql]
runs: 1
max_turns: 200
timeout_seconds: 3600
allowed_tools: [Read, Glob, Grep, Skill, Agent, TodoWrite]
---

Build a mastery-learning course on SQL GROUP BY and HAVING for data analysts who already write SELECT, WHERE and ORDER BY queries. Aim for about 1 hour all-in. Define a small sample database (customers and orders, with a few NULLs and ties) as the course fixture, and make every answer a result set in the answer format you define, or a single-answer multiple-choice letter where a result set does not fit. Write course.json, one file per topic and build-report.md to ./course/. Do not ask questions; state your assumptions in the report.
