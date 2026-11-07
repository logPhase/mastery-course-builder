# Failure modes

Each mode found in a real run, the evidence, and the grader that now catches it. Error analysis adds rows; a mode
leaves this list only when its grader has passed on several runs.

| Mode | What happened | Evidence | Grader |
|---|---|---|---|
| Waits on dead writers | The agent split the content across 7 background subagents, then ended its turn and waited with scheduled wake-ups. Headless mode stops background work 10 minutes after the last turn, so 4 writers were stopped and 5 of 14 topics stayed empty. The agent did not notice and kept waking every 15 minutes to say "still waiting". | Private run r1 (7 Nov 2026): stderr "Background tasks still running 10m after the last turn ... stopping them"; four task notifications with status `stopped`. | `no-scheduled-wait` in each build case (`tool_used ScheduleWakeup`, max 0). The agent now starts subagents in the foreground and never ends its turn while they run. |
