# Repository guidance

## Local task artifacts

- Keep generated BB plans, logs, PR snapshots, test evidence and other local task artifacts under `.bb/` and keep `/.bb/` in the repository `.gitignore`.
- Never force-add or commit these generated artifacts. Preserve them locally for task continuity.
- Before handoff, check `git status` for generated noise. Add narrowly scoped ignores for local artifacts; do not hide source files, project documentation, tests or tracked lockfiles with broad patterns.
