# Git conventions

## Authorization

- Agents may create task branches and local commits without a separate
  instruction.
- Push only when explicitly instructed by the user.
- Merge only when explicitly instructed by the user. Permission to push
  does not authorize a merge.
- Keep unrelated user changes out of task commits, including changes
  already staged before the task.

## Branch names

Use one of these forms:

```text
<type>/<short-kebab-description>
<type>/<issue-number>-<short-kebab-description>
```

- Choose a type from the commit types below.
- Write the description in English, using lowercase words separated by
  hyphens. Describe the task rather than a date or an agent's name.
- Include the issue number when a related GitHub Issue exists. An issue
  need not be created solely to name a branch for a small task.

Examples:

```text
docs/agent-rules
fix/42-tiktok-download
```

## Commits

Use this subject format, with an optional scope:

```text
type: summary
type(scope): summary
```

- Write the summary in English, in the imperative mood, without a trailing
  period.
- Limit the complete subject to 72 characters, including type, scope, and
  any explicitly requested CI-skip marker.
- Use a scope to identify the affected component when that helps readers.
- Make each commit one complete change. Include its related code, tests,
  and documentation together; separate independent changes.

| Type | Use |
| --- | --- |
| `feat` | Add functionality |
| `fix` | Correct a bug |
| `refactor` | Restructure code while preserving behavior |
| `perf` | Improve performance |
| `test` | Add or change tests |
| `docs` | Add or change documentation, including agent instructions |
| `build` | Change build configuration or dependencies |
| `ci` | Change CI workflows |
| `chore` | Maintain tooling or repository configuration |
| `style` | Change formatting without changing behavior |
| `revert` | Revert an earlier change |

Examples:

```text
fix(media): handle unavailable video metadata
docs: define agent coding and git conventions
```

## Skipping CI

Add `[skip ci]` only when the user explicitly requests a CI skip. A change
limited to agent instructions or other documentation does not authorize
adding it automatically.
