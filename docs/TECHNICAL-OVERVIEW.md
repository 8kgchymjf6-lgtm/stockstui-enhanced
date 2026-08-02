# Technical Overview - StockSTUI Enhanced

## Overview

StockSTUI Enhanced is a locally maintained enhanced edition of the open-source
project **stocksTUI**.

The enhanced edition is based on upstream release **v0.1.0-b14** and introduces
carefully implemented improvements to usability, sorting behaviour, financial
data presentation and application robustness while preserving compatibility
with the upstream project.

---

# Repository

Repository type:

- Local Git repository
- Enhanced fork of `andriy-git/stocksTUI`

Repository location:

```text
~/Udvikling/Open-Source/Forks/stockstui-enhanced
```

Default branch:

- main

Base release:

- v0.1.0-b14

Enhanced release:

- v1.0.0-enhanced

Git remote:

- upstream → https://github.com/andriy-git/stocksTUI

Repository status:

- Complete Git history
- Annotated release tags
- Local enhancements isolated from upstream
- Clean working tree before release

---

# Source-code overview

The enhanced edition intentionally limits source-code modifications to three
Python files.

Modified source files:

- `stockstui/main.py`
- `stockstui/presentation/formatter.py`
- `stockstui/data_providers/market_provider.py`

This approach keeps maintenance simple while making future upstream merges and
comparisons significantly easier.

---

# stockstui/main.py

Primary responsibilities:

- Application behaviour
- Keyboard bindings
- Table sorting
- View management
- User interaction

Implemented improvements:

- Added keyboard shortcuts for High sorting.
- Added keyboard shortcuts for Low sorting.
- Corrected Open sorting behaviour.
- Improved History sorting.
- Improved default Description sorting.
- Improved numeric sorting behaviour.
- Protected sorting when required columns are hidden.
- Improved sort-direction handling.
- Improved overall robustness of sorting operations.
- Added additional defensive runtime checks.

---

# stockstui/presentation/formatter.py

Primary responsibilities:

- Financial value formatting
- Currency formatting
- Table rendering
- Display formatting
- Market-status presentation

Implemented improvements:

- Left-aligned ticker symbols.
- Improved currency formatting.
- Improved price formatting.
- Improved percentage formatting.
- Improved Market Cap formatting.
- Improved Volume formatting.
- Improved PE Ratio formatting.
- Improved Dividend Yield formatting.
- Improved market-status formatting.
- Improved formatting consistency across financial values.
- Improved numeric handling of compact values using K, M, B and T suffixes.
- Improved sorting compatibility for formatted values.

---

# stockstui/data_providers/market_provider.py

Primary responsibilities:

- Yahoo Finance data retrieval
- Financial data processing
- Data normalization
- Market information handling

Implemented improvements:

- Improved PE Ratio selection logic.
- Improved Dividend Yield normalization.
- Improved fallback handling for incomplete Yahoo Finance data.
- Improved defensive handling of missing and invalid values.

---

# Git integration

The repository has been prepared for long-term maintenance.

Configuration includes:

- Complete Git history.
- Configured upstream remote.
- Annotated release tags.
- Local enhanced version maintained on the `main` branch.
- Clean separation between upstream and local modifications.

The repository can therefore receive future upstream updates while preserving
the enhanced functionality.

---

# Installation

Recommended installation method:

```text
pipx
```

Application launcher:

```text
~/.local/bin/stockstui
```

pipx virtual environment:

```text
~/.local/share/pipx/venvs/stockstui
```

The installed pipx package has been compared with the local Git repository
and verified to contain identical application code.

---

# Documentation

The enhanced edition is documented through:

- README-ENHANCED.md
- CHANGELOG-ENHANCED.md
- TECHNICAL-OVERVIEW.md
- VALIDATION.md
- TESTING.md
- MAINTENANCE.md
- CREDITS.md

The original upstream documentation remains available and unchanged wherever
possible.

---

# Design principles

The enhanced edition follows these principles:

- Preserve upstream compatibility whenever practical.
- Keep source-code modifications focused and maintainable.
- Improve usability without unnecessary architectural changes.
- Improve consistency of financial-data presentation.
- Use defensive programming techniques where appropriate.
- Preserve the original project structure.
- Preserve licensing and attribution.
- Keep future maintenance straightforward.

---

# Summary

StockSTUI Enhanced is a carefully maintained enhancement of the original
stocksTUI project.

The enhanced edition focuses on improving usability, financial-data
presentation, sorting behaviour and application robustness while intentionally
keeping the number of modified source files small. This approach simplifies
future maintenance and helps preserve compatibility with future upstream
development.
