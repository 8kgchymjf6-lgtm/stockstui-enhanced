# StockSTUI Enhanced

StockSTUI Enhanced is a locally maintained enhanced edition of the open-source
project **stocksTUI**.

The enhanced edition is based on upstream release **v0.1.0-b14** and contains a
carefully maintained collection of improvements to usability, sorting
behaviour, financial-data presentation and application robustness while
preserving compatibility with the upstream project.

---

# Base information

Upstream project:

- `andriy-git/stocksTUI`

Base release:

- `v0.1.0-b14`

Enhanced release:

- `v1.0.0-enhanced`

Current local stability build:

- `0.1.0b14+enhanced.20261018.4` (upstream b14; no public release published)
- Validation and recovery notes: [STABILITY.md](STABILITY.md)

Default branch:

- `main`

License:

- GNU General Public License v3.0 or later (`GPL-3.0-or-later`)

---

# Project purpose

The purpose of the enhanced edition is to improve the original application
without changing its overall architecture or moving away from the upstream
project.

The enhanced edition therefore focuses on carefully selected improvements while
keeping source-code modifications limited and maintainable.

---

# Main enhancements

The enhanced edition includes improvements in the following areas:

- Table sorting
- History sorting
- Financial-data formatting
- Numeric sorting
- Market-data handling
- User-interface behaviour
- Defensive programming
- Overall application robustness

The original enhancement touched the main application, formatter and market
provider. Subsequent stability work also covers configuration, SQLite persistence,
other providers and views. Current scope, validation and recovery are documented
in [STABILITY.md](STABILITY.md); the original three-file description is historical.

---

# Documentation

Additional documentation is available in:

- `CHANGELOG-ENHANCED.md`
- `TECHNICAL-OVERVIEW.md`
- `VALIDATION.md`
- `TESTING.md`
- `MAINTENANCE.md`
- `CREDITS.md`

---

# Attribution

The enhanced edition preserves:

- Original project attribution
- Original project structure
- Original licensing
- Compatibility with future upstream development wherever practical

The original upstream project remains available through its own repository and
documentation.
