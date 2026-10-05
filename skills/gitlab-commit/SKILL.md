---
name: gitlab-commit
description: Prepare or create Git commits for this repository using GitLab commit-message conventions. Use when asked to draft a commit message, commit changes, or review commit wording.
---

# GitLab commit style

Before drafting or creating a commit, inspect the relevant diff and repository
status. Describe the change that is actually included; do not include unrelated
work or claim tests that were not run.

Write the commit message using these rules:

- Use an imperative subject that starts with a capital letter.
- Use at least three words and no more than 72 characters.
- Do not end the subject with a period and do not use emoji.
- Keep each commit focused on one logical change.
- Add a body when context helps a reviewer understand why the change exists.
- Separate the subject and body with a blank line and wrap body lines at 72
  characters.
- For changes spanning at least 30 lines across at least three files, include a
  body describing the change.
- Use full URLs when referencing issues or merge requests.

Prefixes such as `docs:` or `[API]` are allowed when useful or already
established in the repository, but they are not required. The message following
the prefix must still begin with a capital letter.

Do not stage, amend, push, or create a commit unless the user has authorized
that action. If asked only for wording, return the proposed message without
changing Git state.

Reference: [GitLab commit message guidelines](https://docs.gitlab.com/development/contributing/merge_request_workflow/#commit-messages-guidelines)
