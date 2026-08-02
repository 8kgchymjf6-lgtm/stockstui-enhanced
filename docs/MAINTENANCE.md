# Maintenance - StockSTUI Enhanced

This document describes the recommended maintenance workflow for the enhanced
edition of StockSTUI.

---

# Repository

Repository type:

- Local Git repository
- Enhanced fork of the original stocksTUI project

Default branch:

- main

Upstream remote:

- upstream

---

# Daily maintenance

Before starting work, verify that the repository is clean.

```bash
git status
git branch
git log --oneline --decorate --graph -5
```

Expected result:

- Working tree clean
- Branch: main
- HEAD pointing at the latest enhanced commit

---

# Fetch upstream changes

Download new commits, branches and tags from the original project.

```bash
git fetch upstream --prune --tags
```

This command downloads updates only.

It does **not** modify the local enhanced branch.

---

# New development

Create a separate feature branch before making larger changes.

```bash
git switch -c feature/your-feature-name
```

After development:

- Test the changes
- Commit the changes
- Merge into `main`

---

# Stable releases

After validation, create an annotated Git tag.

Example:

```bash
git tag -a v1.1.0-enhanced -m "Second stable enhanced release"
```

---

# Installed application

Launcher:

```text
~/.local/bin/stockstui
```

pipx virtual environment:

```text
~/.local/share/pipx/venvs/stockstui
```

---

# Documentation

The enhanced edition is documented in:

- README-ENHANCED.md
- CHANGELOG-ENHANCED.md
- TECHNICAL-OVERVIEW.md
- VALIDATION.md
- TESTING.md
- MAINTENANCE.md
- CREDITS.md

The original upstream documentation remains available. The root `README.md`
contains an added reference to the enhanced documentation.

---

# Backups

Stable source archives should be stored separately from the Git repository.

Example location:

```text
~/Udvikling/Arkiv/Releases
```

---

# Good practice

Before creating a release:

- Verify Git status
- Verify documentation
- Verify tests
- Verify release tag
- Create a backup archive

Keeping these steps consistent makes future maintenance much easier.
