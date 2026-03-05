# cc-anti — Claude Code ↔ Antigravity Conversation Export Tool

[中文说明](./README.md)

Bidirectional conversion between Claude Code and Antigravity conversation histories, with a built-in visual web management interface.

![Python 3](https://img.shields.io/badge/Python-3.8+-blue?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Linux-lightgrey)

## ✨ Features

| Feature | Description |
|---------|-------------|
| **CC → Project Dir** | Export Claude Code conversations as `.cc_history.md` to your project root |
| **AG → CC** | Convert Antigravity brain artifacts into CC-readable JSONL sessions |
| **AG ♻️ Recover** | Export Antigravity brain artifacts to project root (`ag_brain/`) |
| **Web UI** | Built-in visual interface with dual-pane browsing, preview, and one-click actions |

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) and/or [Antigravity (Gemini)](https://gemini.google.com/) installed

### Run

```bash
python3 cc-anti.py
```

The tool starts a web interface at `http://localhost:8766` and opens it in your default browser automatically.

## 📖 Usage

### Web Interface

1. **Left Panel** — Browse all Claude Code projects and sessions
2. **Right Panel** — Browse all Antigravity conversations
3. **Center Buttons**:
   - 📤 **Export to Project** — Select a CC session, export as Markdown to project root
   - ⬅ **Import to CC** — Select an AG conversation, generate artifacts as a CC session
   - ♻️ **Recover to Project** — Select an AG conversation, copy artifact files to project directory
4. **Preview Panel** — Click any session/conversation to preview content on the right

### Data Paths

| Source | Default Path |
|--------|-------------|
| Claude Code Projects | `~/.claude/projects/` |
| Antigravity Conversations | `~/.gemini/antigravity/conversations/` |
| Antigravity Brain | `~/.gemini/antigravity/brain/` |

## 🏗️ Project Structure

```
cc-ag/
├── cc-anti.py      # Main program (single file with backend + embedded frontend)
├── exports/        # Export output directory
├── README.md       # 中文说明 (Chinese)
└── README_EN.md    # English README
```

## ⚠️ Limitations

- **Antigravity `.pb` files** — The Protobuf format is proprietary, so full conversation content cannot be parsed directly. Only brain artifacts (Markdown/text) can be exported.
- **Import to CC** — Generated sessions can be viewed via `/resume`, but original tool calls and thinking processes are not included.
- **Local only** — The tool reads from the local filesystem and does not make any network requests.

## 📄 License

MIT
