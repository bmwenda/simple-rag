---
name: pull-request
description: Draft or create pull requests for this repository with the required project structure. Use when asked to prepare, review, or open a pull request or merge request.
---

# Pull request format

Inspect the branch diff, commits, and relevant verification results before
drafting the pull request. Keep the content specific to the changes in the
branch and do not invent tests, artifacts, issue links, or outcomes.

Every pull request must include:

## Title

Use a concise, outcome-focused title that reflects the full change. When
creating the pull request through a tool, use this as the pull request's title
rather than duplicating it as a heading in the description.

## Description

Write one or two concise prose paragraphs explaining what changed and why. Do
not use bullet points in the Description section. Include important design
choices, limitations, or follow-up work only when they help reviewers understand
the change.

## Acceptance criteria

Copy the linked issue's acceptance criteria into this section and state how
each criterion is satisfied. If the issue has no explicit criteria, derive a
short, reviewable set from its requested outcome and call that out.

## Issue

Reference the issue with a GitHub closing keyword so it closes automatically
when the pull request merges. Use `Closes #<number>` (or `Fixes #<number>`)
for every issue addressed by the pull request. Do not rely on a plain URL
alone. If the issue number is unknown, stop and request it before creating the
pull request.

## Testing

List the checks that were actually run and their results. Include manual test
steps when reviewer reproduction is useful. If testing is relevant but could
not be performed, state that clearly with the reason.

## Artifacts

Link or attach reviewer evidence such as screenshots, recordings, logs, sample
output, benchmarks, generated documents, or migration/schema output. Use this
section only when the work produces useful review artifacts.

Use the repository host's normal Markdown. Preserve any more specific pull
request template or user-requested sections in addition to this minimum.
