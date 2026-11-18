# SortSense — Installation & Testing Instructions

## Quick Install (Windows 10/11 x64)

### Option A: Installer (recommended)
1. Download `SortSense-Setup.exe` from the [GitHub Actions artifact](https://github.com/Minnolter12/SortSense/actions)
2. Double-click to install (no admin rights needed; installs to `%LOCALAPPDATA%\Programs\SortSense`)
3. Launch from **Start Menu → SortSense** or the Desktop shortcut

### Option B: Portable ZIP
1. Download `SortSense-Portable.zip`
2. Extract anywhere (e.g. `D:\Tools\SortSense\`)
3. Run `SortSense.exe` — no installation step

---

## First Run

1. SortSense opens the Dashboard. If running for the first time, a welcome dialog appears.
2. Go to **Settings** → set your watch folder (default: `Downloads`).
3. Set your sorted output folder (default: `Documents\SortSense-Sorted`).
4. Click **Save**.
5. Drop or save a file in the watched folder — it appears in the **Review Queue** within a few seconds.

---

## User Data Location

All user data lives in `%USERPROFILE%\.sortsense\`:

```
~\.sortsense\
  config.json      — watched dirs, output dir, Ollama settings
  rules.json       — your saved organization rules
  history.json     — move history (for Undo)
  first_run        — marker file (delete to re-trigger welcome dialog)
```

**Uninstalling does NOT delete this folder.** Your rules and history survive uninstall/reinstall.

---

## Enable Optional AI (Ollama + Gemma)

> **SortSense works fully offline without this.** Only do this if you want AI-powered suggestions.

```powershell
# 1. Download and install Ollama
#    https://ollama.com/download/windows  (~80 MB installer)

# 2. Pull the Gemma model (~6.6 GB — only needed once)
ollama pull gemma4:e4b

# 3. (optional) verify it works
ollama run gemma4:e4b "Hello"

# 4. Restart SortSense — it detects Ollama automatically
#    Dashboard badge changes to "Gemma AI Active"
```

To stop using Ollama: just stop/uninstall Ollama. SortSense falls back to deterministic mode.

---

## Multi-PC Testing Checklist

For each test machine, verify:

- [ ] Installer runs without admin rights
- [ ] App launches from Start Menu shortcut
- [ ] App launches from Desktop shortcut
- [ ] Deterministic mode: drop a PDF/TXT into watched folder → Review Queue shows proposal within 5 s
- [ ] Proposal has a content-based filename (not the opaque original name)
- [ ] Approve + Execute moves the file and shows it in History
- [ ] Undo restores the file to its original path with its original name
- [ ] Reject leaves the file untouched
- [ ] Uninstall → `~\.sortsense\` survives → Reinstall → rules/history intact
- [ ] (If Ollama installed) Dashboard shows "Gemma AI Active" after `ollama pull gemma4:e4b`
- [ ] (If Ollama not installed) Dashboard shows "Deterministic Mode"

---

## Reporting Issues

Please include:
- Windows version (`winver`)
- SortSense version (title bar or Settings page)
- Whether Ollama is installed and which model
- Steps to reproduce
- Screenshot of the Review Queue or error dialog

Open an issue at: https://github.com/Minnolter12/SortSense/issues
