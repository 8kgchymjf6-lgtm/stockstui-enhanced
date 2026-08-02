# Validation - StockSTUI Enhanced

This document records the validation performed for the enhanced edition of
StockSTUI based on upstream release `v0.1.0-b14`.

---

# Validation scope

The enhanced edition modifies the following source files:

- `stockstui/main.py`
- `stockstui/presentation/formatter.py`
- `stockstui/data_providers/market_provider.py`

Validation covered the modified source code, the local Git repository, the
installed pipx package, documentation and the released archive.

---

# Git repository validation

The following repository checks were completed successfully:

- Repository converted from a shallow clone to a complete Git repository.
- Complete commit history available.
- Upstream remote configured correctly.
- Upstream branches available.
- Upstream tags fetched.
- Local branch: `main`.
- Annotated release tag: `v1.0.0-enhanced`.
- Clean working tree before documentation updates.

---

# Source-code validation

The enhanced source code was validated by:

- Reviewing every modified source file.
- Reviewing every modified Git hunk.
- Verifying source-code consistency.
- Verifying formatter behaviour.
- Verifying sorting behaviour.
- Verifying data-provider behaviour.

Modified files:

- `stockstui/main.py`
- `stockstui/presentation/formatter.py`
- `stockstui/data_providers/market_provider.py`

---

# Python validation

The project successfully passed Python compilation.

Performed check:

```bash
python3 -m compileall stockstui
```

Result:

- No syntax errors.

---

# Module import validation

The installed pipx package was used to import every module.

Result:

- 42 modules imported successfully.
- No import failures.
- No runtime import exceptions.

---

# Installed package validation

The installed pipx package was compared against the local Git source.

Validation performed:

- Recursive directory comparison.
- Bytecode excluded.
- Cache files excluded.

Result:

- No differences detected.

This confirms that the installed application matches the validated source code.

---

# Release archive validation

The release archive was verified.

Checks performed:

- Archive exists.
- Archive contents listed successfully.
- Repository structure verified.
- Assets included.
- Source files included.

---

# Shell validation

The local shell configuration was verified.

Checks performed:

- `.profile` syntax verified.
- PATH entries verified.
- Duplicate PATH entries removed.
- pipx launcher available.
- Git available.
- Python available.
- VSCodium available.

---

# Runtime validation

The application was started and manually verified.

Validated functionality includes:

- Application startup.
- General navigation.
- Price table.
- History view.
- Sorting.
- Hidden-column handling.
- High sorting.
- Low sorting.
- Open sorting.
- Default Description sorting.
- Numeric sorting.
- Market Cap formatting.
- Volume formatting.
- Currency formatting.
- Dividend Yield formatting.
- PE Ratio formatting.
- Ticker alignment.
- FRED view.
- Options view.
- Debug view.
- Configuration views.

No known defects were identified within the validated functionality at the time of validation.

---

# Documentation validation

The enhanced documentation was reviewed for consistency.

Validated documents:

- README-ENHANCED.md
- CHANGELOG-ENHANCED.md
- TECHNICAL-OVERVIEW.md
- TESTING.md
- MAINTENANCE.md
- CREDITS.md
- VALIDATION.md

---

# Validation summary

The enhanced edition was successfully validated through:

- Git verification.
- Source-code review.
- Python compilation.
- Module import verification.
- Installed package comparison.
- Manual runtime verification.
- Documentation review.
- Release archive verification.

At the time of validation, no known defects remained within the modified
functionality.
