# Coding standards

These rules apply to all agents working in this repository. Apply them to
new or substantially changed code; preserve unrelated code and formatting.

## Scope

- Implement the requested behavior in a focused change.
- Include refactoring only when necessary to implement that behavior.
- Describe unrelated improvements separately for future work.
- Introduce new formatting, linting, or commit-checking automation as a
  separate task, rather than as part of adopting these written rules.

## Language

- Use English for identifiers, comments, and technical documentation,
  including agent instructions.
- Discuss the work with the user in Russian.
- Follow the application's existing localization conventions for
  user-facing text.

## Python

- Follow PEP 8 and use four spaces for indentation.
- Use `snake_case` for functions and variables, `PascalCase` for classes,
  and `UPPER_SNAKE_CASE` for constants.
- Annotate parameters and return values of new or substantially changed
  functions.

## TypeScript and React

- Use two spaces for indentation, double quotes, and semicolons.
- Use `camelCase` for functions and variables, and `PascalCase` for
  components and types.
- Preserve strict type checking. Fix type errors at their source; explain
  any necessary type-checking exceptions.
- Treat unvalidated external data as `unknown` and narrow it before use,
  rather than bypassing checks with `any` or unchecked type assertions.

## Boundaries

- Validate values at API and external-data boundaries before relying on
  their types or contents.

## Verification

- For a behavior bug, add a regression test that reproduces the failure
  and passes with the fix.
- For new logic, test observable results rather than copying the
  implementation into assertions.
- Documentation and formatting changes do not require additional tests.
- Use the repository's existing checks. Read their current commands from
  package scripts and workflow configuration; consult `docs/operations.md`
  for environment setup.
- Run checks relevant to the affected components and behavior.
- Report which checks passed or failed. If a check cannot run, state the
  reason and identify the behavior that remains unverified.
