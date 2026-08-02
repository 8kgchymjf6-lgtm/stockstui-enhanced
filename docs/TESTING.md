# Testing - StockSTUI Enhanced

This document records the automated and manual checks performed for the
enhanced edition.

## Automated verification checks

The following checks were completed successfully:

- Full Python compilation of the StockSTUI package
- Import of all 42 StockSTUI modules
- Import checks of central classes and functions
- `git diff --check`
- Comparison of the Git source with the installed pipx source
- Validation of the release archive

## Manual checks

The following areas were tested manually:

- Visible tabs
- Price-table sorting
- History sorting
- Sorting with hidden columns
- Ticker alignment
- Configuration views
- Options view
- FRED view
- Debug view
- General startup and navigation

## Result

No known defects were identified within the tested areas at the time of
validation.

## Limitation

These checks do not prove that every possible runtime path, external API
response, network condition, or future dependency update will be error-free.
