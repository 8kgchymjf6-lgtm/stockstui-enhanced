# stocksTUI Enhanced
> **Note**
>
> This repository contains an independently maintained enhanced edition of
> **stocksTUI**.
>
> Additional enhanced documentation is available in the
> [`docs/`](docs/) directory, including:
>
> - Project overview
> - Technical documentation
> - Validation
> - Testing
> - Maintenance
> - Credits
> - Enhanced changelog

## Version 1.0.4

[Release notes](docs/CHANGELOG-ENHANCED.md#v104-enhanced) ·
[Validation and recovery](docs/STABILITY.md) ·
[Download v1.0.4](https://github.com/8kgchymjf6-lgtm/stockstui-enhanced/releases/tag/v1.0.4-enhanced)

This release strengthens quote/cache integrity, watchlist and configuration
persistence, asynchronous refresh recovery, and handling of partial provider data.
It also fixes keyboard, FRED, options and chart edge cases while retaining the
compact `Last Refresh` status line.

Local Linux/Python 3.14 validation: **922 tests passed, 2 optional live checks
skipped; 92.31% combined statement/branch coverage**. Test coverage is not a
percentage guarantee of reliability. The [release CI](https://github.com/8kgchymjf6-lgtm/stockstui-enhanced/actions/runs/39138313029)
also passed on Python 3.10–3.14. See [release validation](docs/VALIDATION.md)
and the [documentation index](docs/README-ENHANCED.md#documentation).

---

A fast, minimalist terminal app for checking stock prices, crypto, news, and historical charts — without leaving your shell. Built with [Textual](https://github.com/textualize/textual), powered by [yfinance](https://github.com/ranaroussi/yfinance), and made for people who prefer the command line over CNBC.

![stocksTUI Screenshot - Main Interface](assets/com.png)
![stocksTUI Screenshot - CLI Mode](assets/cli.png)
![stocksTUI Screenshot - FRED Data](assets/fred.png)

---

## ✨ Features

*   **Live-ish Price Data**
    Watch your favorite tickers update in near real-time with configurable refresh intervals.

*   **Watchlists That Make Sense**
    Organize your assets into lists like "Tech", "Crypto", "Dividend Traps", or "Memes". Manage them entirely from the UI — no need to touch JSON unless you want to.

*   **Tag-Based Filtering**
    Assign tags (e.g., `growth`, `ev`, `semiconductor`) to your tickers and instantly filter any watchlist to see only what's relevant.

*   **Charts & Tables, Your Way**
    View historical performance from `1D` to `Max`, from a table or a chart.

*   **Options Chain Support**
    View detailed options chains with strike prices, bid/ask spreads, Greeks (Delta, Gamma, Theta, Vega), and open interest visualization. Track your positions with quantity and average cost.

*   **News That Matters**
    See the latest headlines per ticker or a combined feed — no ads, no autoplay videos, just info.

*   **Economic Data (FRED)**
    Monitor key economic indicators directly with integration for St. Louis Fed (FRED) data. Track GDP, Unemployment, CPI, and more with rolling averages and Z-score trend analysis.

*   **Deep Market Context**
    View comprehensive asset details including All Time High (ATH), % Off ATH, PE Ratio, Market Cap, and historical performance charts.

*   **Quick Actions & Open Mode**
    Instantly edit ticker aliases and notes with `e`. Use "Open Mode" (`o`) to quickly jump to external resources or switch between news, history, and options.

*   **Keyboard-Friendly, Mouse-Optional**
    Navigate everything with Vim-style keys or arrow keys. Bonus: lots of helpful keybindings, fully documented.

*   **Custom Themes & Settings**
    Tweak the look and feel with built-in themes or your own. Set your default tab, hide unused ones, and make it feel like *your* dashboard.

*   **Smart Caching**
    The app remembers what it can. Market-aware caching keeps startup fast and avoids pointless API calls on weekends or holidays.

> ⚠️ Note: All symbols follow [Yahoo Finance](https://finance.yahoo.com/) format — e.g., `AAPL` for Apple, `^GSPC` for S\&P 500, and `BTC-USD` for Bitcoin.

---

## 🛠 Requirements

*   **Python** 3.10 or newer
*   **OS Support:**

    *   **Linux** — Release CI covers Python 3.10–3.14.
    *   **macOS** — Use a modern terminal; not covered by this release’s CI.
    *   **Windows** — Use Windows Terminal with WSL2; not covered by this release’s CI.

---

## 🚀 Installation

The easiest way to install is with [`pipx`](https://pypa.github.io/pipx/):

### 1. Install pipx (if you don’t already have it):

```bash
# Debian/Ubuntu
sudo apt install pipx

# Arch Linux
sudo pacman -S python-pipx

# macOS
brew install pipx

# Or fallback to pip
python3 -m pip install --user pipx
python3 -m pipx ensurepath
```

### 2. Install stocksTUI:

```bash
pipx install "git+https://github.com/8kgchymjf6-lgtm/stockstui-enhanced.git@v1.0.4-enhanced"
```

The package version and `stockstui --version` are `1.0.4`. This installs the
enhanced fork explicitly from its release tag.

To replace an existing stocksTUI installation with this release:

```bash
pipx install --force "git+https://github.com/8kgchymjf6-lgtm/stockstui-enhanced.git@v1.0.4-enhanced"
```

Personal configuration is stored outside the package. Keep a backup and restart
running stocksTUI windows after upgrading. You can now run `stockstui` from anywhere.

---

## 🧭 Usage

Run the app like so:

```bash
stockstui
```

Need help?

```bash
stockstui -h          # Short help
stockstui --man       # Full user manual
```

---

### 💡 Command-Line Examples

Open on Tesla's History tab.
```bash
stockstui --history TSLA
```

Get combined news for NVIDIA and AMD.
```bash
stockstui --news "NVDA,AMD"
```

Open on Apple's Options tab to view the options chain.
```bash
stockstui --options AAPL
```

Create a temporary watchlist for this session only.
```bash
stockstui --session-list "EV Stocks=TSLA,RIVN,LCID"
```

Launch a 5-day chart for Tesla.
```bash
stockstui --history TSLA --period 5d --chart
```

Open the FRED tab with your configured economic series. Add series such as
`UNRATE` under **Configs > FRED Settings**; `--fred` takes no series argument.
```bash
stockstui --fred
```

CLI mode: Output "stocks" list, filtered by the "tech" tag.
```bash
stockstui -o stocks --tags tech
```

---

## 🔑 FRED API Key

To use the Economic Data (FRED) features, you must provide a free API key from the Federal Reserve Bank of St. Louis.

1.  Create a free account and request an API key at [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html).
2.  Once you have your key, enter it in the app under **Configs > FRED Settings**.
3.  Click **Save** to enable FRED data fetching.

## ⌨️ Keybindings

*   Press `?` inside the app for a quick keybinding cheat sheet
*   Run `stockstui --man` for the full breakdown

---

## 🧑‍💻 For Developers: Install from Source

Want to try the bleeding-edge version or contribute?

```bash
git clone https://github.com/8kgchymjf6-lgtm/stockstui-enhanced.git
cd stockstui-enhanced
./install.sh
```

This installs the checkout into a local virtual environment. Run
`.venv/bin/stockstui` (or `venv/bin/stockstui` if that environment already exists).
It preserves an existing pipx/global launcher. Use `./install.sh --dev` to include
test tools. The script can be called from any working directory.

To explicitly create a global command, use `./install.sh --link`. Replacing an
existing symlink additionally requires `--replace-launcher`; regular files are
never overwritten. `--venv PATH` and `--bin-dir PATH` select alternative locations.
For an already prepared environment, `--offline --no-deps` avoids network access
and dependency changes.

Run `./run_tests.sh` for the full suite and the 80% coverage gate with branch measurement enabled. It does
not install packages and uses isolated temporary configuration/cache directories.
Set `STOCKSTUI_PYTHON=/path/to/python` to choose an environment explicitly.
`--no-coverage` is an explicit diagnostic option, not the CI default. See
[local stability and validation](docs/STABILITY.md) for the enhanced build.

---

## ⚖️ License

Licensed under the **GNU GPL v3.0 or later**.
See [LICENSE](LICENSE) and [credits](docs/CREDITS.md).
