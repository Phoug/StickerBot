# Issue tracker: GitHub

Issues and specs live in GitHub Issues for `Phoug/StickerBot`.
Use the `gh` CLI from this repo.

## Conventions

- Before creating issues, verify the target with
  `gh repo view --json nameWithOwner`.
- Create: `gh issue create --title "..." --body-file <file>`.
- Read: `gh issue view <number> --json number,title,body,labels,comments`.
- List: `gh issue list --state open`, with appropriate label filters.
- Comment: `gh issue comment <number> --body-file <file>`.
- Apply or remove labels: `gh issue edit <number> --add-label "..."`
  or `--remove-label "..."`.
- Close: post an explanation with `gh issue comment`, then run
  `gh issue close <number>`.
- Use native GitHub sub-issues for parent/child relationships.
  If unavailable, put `Part of #<parent>` at the top of the child body
  and link the child in the parent's task list.
- Use native GitHub issue dependencies for blockers. If unavailable,
  put `Blocked by: #<number>` at the top of the blocked issue.
  An issue is unblocked when every blocker is closed.

When a skill says "publish to the issue tracker", create a GitHub issue.
When it says "fetch the relevant ticket", read the GitHub issue.

## Pull requests as a triage surface

**PRs as a request surface: no.**
