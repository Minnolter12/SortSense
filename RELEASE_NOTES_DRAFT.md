# SortSense v0.1-beta — Release Notes Draft

> **DRAFT — Awaiting author approval before publishing.**
> This is a pre-release for multi-PC testing. Do NOT publish until explicitly approved.

---

## What is SortSense?

SortSense is a **privacy-first, offline-capable** Windows desktop file organizer.
It watches your Downloads folder (or any folder you choose), analyzes each new file, and
*suggests* where it should go — without ever moving anything until *you* approve it.

**Ollama + Gemma is entirely optional.** The app is fully useful the moment you install it,
using a built-in deterministic topic engine that recognizes 12 academic and business subjects
(DBMS, DSA, OOPS, Discrete Mathematics, NLP, Machine Learning, Operating Systems, Computer
Networks, Python, Mathematics, Physics, Chemistry) plus general document types (invoices,
assignments, research papers, certificates, etc.).

---

## Features (v0.1-beta)

### Core — Available Offline, No Setup Required
- **Automatic detection** — watches a folder; new files appear in the Review Queue instantly
- **Subject classification** — weighted evidence engine; never invents a category on thin evidence
- **Content-based filenames** — proposed names come from the document itself (headings, first line)
- **Preview before anything moves** — every proposal is shown with editable name, category, destination
- **Approval-first** — files are *never* moved until you click Approve + Execute
- **Reject** — leaves the file exactly where it is
- **Partial-download protection** — `.crdownload`, `.part`, `.tmp` files are ignored until complete
- **Collision safety** — a file named the same as one already at the destination gets a numbered copy, never an overwrite
- **History & Undo** — every move is logged; Undo restores the original path and filename
- **Saved rules** — tell SortSense "invoices always go to Finance/Invoices"; rules are matched on future files

### Organization Modes
| Mode | Description |
|------|-------------|
| **AI-Directed** | Deterministic (offline) or Gemma (if Ollama installed) suggests category + folder |
| **Manual Destination** | You pick the folder; app suggests the filename |
| **Hybrid** | You set a root folder; app suggests the subfolder based on content |

### Optional: Local AI with Ollama + Gemma
- Install [Ollama](https://ollama.com) and run `ollama pull gemma4:e4b`
- SortSense detects it automatically; the status badge on the dashboard shows the honest state
- If Ollama is unavailable or the model isn't pulled, the app falls back to deterministic mode silently — no crash, no hang
- The dashboard never shows "Gemma AI Active" unless a model is truly reachable and responding

---

## Installation

### Standard Installer (Recommended)
1. Download `SortSense-Setup.exe` from the GitHub release artifacts
2. Run it — no administrator rights required (installs to `%LOCALAPPDATA%\Programs\SortSense`)
3. Launch from Start Menu or Desktop shortcut
4. On first run, choose the folder to watch (default: `%USERPROFILE%\Downloads`)

### Portable ZIP
1. Download `SortSense-Portable.zip`
2. Extract anywhere
3. Run `SortSense.exe` — no installation needed
4. Config and history are stored in `%USERPROFILE%\.sortsense` (same as the installer)

### Enable Optional AI (after installing SortSense)
```
# 1. Install Ollama from https://ollama.com/download/windows
# 2. Pull the model (6.6 GB download):
ollama pull gemma4:e4b
# 3. Restart SortSense — it detects Ollama automatically
```

---

## Known Limitations

| Limitation | Detail |
|------------|--------|
| **No OCR** | Image-only PDFs (scanned docs with no text layer) are marked as "empty" and sent to the Review Queue with the original filename. The user must categorize them manually. |
| **Unsigned executable** | Windows SmartScreen may warn "unrecognized app". Click "More info → Run anyway". This will be resolved with code signing in a future release. |
| **No clean-machine test** | The exe was built and smoke-tested on the development machine. A fresh Windows install without Python has not been tested in this release. |
| **Ollama timeout** | On slow machines, the first Gemma response may time out (default: 120 s). Increase with `SORTSENSE_OLLAMA_TIMEOUT=300` in the environment. |
| **Windows only** | The packaging (PyInstaller exe, Inno Setup installer) targets Windows 10/11 x64. Linux/macOS: run from source. |

---

## What's New Since Last Release

This is the first public pre-release. The complete change log is in [FIXES.md](FIXES.md).

**Key additions:**
- Approval-first workflow (`app/proposals.py`) — nothing moves without your click
- Weighted topic engine (`app/topics.py`) — 12 subjects, evidence-backed confidence
- pypdf fallback for PDF extraction
- 31 new automated regression tests
- 12-file opaque-name scenario (WhatsApp downloads, scan files, etc.) verified
- 5-state honest Ollama status (Deterministic / Ollama Unavailable / Model Missing / Gemma AI Active / Request Failed)
- CI: GitHub Actions builds exe on `windows-latest` and uploads as artifact

---

*Document version: draft — awaiting approval*
*Branch: `fix/sortsense-regression-restoration`*
