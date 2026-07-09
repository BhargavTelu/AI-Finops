---
description: Update docs/ to reflect the pending changes, then create a Conventional Commit
---

Bring the project documentation in sync with the pending working-tree changes, then commit everything as one logical Conventional Commit.

Optional argument (commit type/scope hint or extra context): $ARGUMENTS

## Steps

1. **Review the pending changes.** Run `git status` and `git diff` (plus `git diff --staged` if anything is staged). Understand what changed and why before touching docs.

2. **Update the relevant docs.** Check each of these and edit only the ones the change actually affects:
   - `docs/changelog.md` - add an entry for any user-visible or behavioral change
   - `docs/project_status.md` - update if milestone progress moved (something completed, started, or got blocked)
   - `docs/architecture.md` - update if the schema, API surface, data flow, or stack changed
   - `docs/project_spec.md` - update only if requirements/FRs themselves changed
   - `CLAUDE.md` § UI Style - update if UI/design-system tokens or conventions changed (token conventions are also documented inline in `globals.css`)
   - `CLAUDE.md` - update if a hard rule, the stack, a constraint, or the milestone one-liner changed, or a new doc was added under `docs/` (link it in §Documentation)

   Do NOT invent doc updates for changes that don't warrant them. Skipping all docs is valid for pure refactors/test fixes - say so instead of padding.

3. **Verify before committing.** If web code changed: `pnpm lint` and `pnpm typecheck` (and `pnpm test`) in `apps/web`. If API code changed: `pytest` in the API package. Fix failures before committing - never commit red.

4. **Commit.** Stage the code changes and the doc updates together (same PR/commit per repo etiquette). Write a Conventional Commit message (`feat:` / `fix:` / `refactor:` / `chore:` / `docs:`), imperative mood, one logical change. Never commit secrets, generated files, or `.claude/settings.local.json`.

5. **Report.** Show the commit hash and summarize which docs were updated and which were deliberately skipped. Do not push unless asked.
