# WindowsHarness

**AI Coding Agent for Windows** - A native port of [AndroidHarness](https://github.com/Sanuu7/AndroidHarness) to Windows using Python 3.11+ and PyQt6.

## Features

- 🤖 **AI Agent Loop** - Autonomous code editing with LLM integration
- 🔧 **Tool System** - File ops, shell, git, browser automation, patching
- 🧠 **Multiple LLM Providers** - OpenAI, Anthropic, Gemini, Ollama, local models
- 💻 **Native Windows UI** - PyQt6 with syntax-highlighted editor, terminal, browser
- 🔐 **Secure Credentials** - API keys stored in Windows Credential Manager
- 📦 **Skills System** - Extensible workflows (caveman, TDD, code review, etc.)
- 🌳 **Git Integration** - Full git workflow (status, diff, commit, push, PR)
- 🌐 **Browser Automation** - Navigate, click, type, screenshot, DOM inspection
- 🎨 **Theming** - Light/dark/system themes with customizable fonts

## Architecture

```
windows-harness/
├── main.py                 # Entry point
├── requirements.txt        # Dependencies
├── ARCHITECTURE.md         # Detailed architecture doc
├── config/                 # Configuration system
│   └── settings.py         # Pydantic settings with keyring
├── core/                   # Core agent logic
│   ├── types.py           # Core data types
│   ├── agent_engine.py    # Main agent loop
│   └── context.py         # Context hygiene & compaction
├── llm/                    # LLM providers
│   ├── base.py            # Provider abstraction
│   ├── openai_provider.py # OpenAI, Responses API, compat
│   ├── anthropic_provider.py
│   └── gemini_provider.py
├── tools/                  # Tool implementations
│   ├── registry.py        # Tool registry
│   ├── file_tools.py      # Read, write, edit, list, glob, grep
│   ├── shell_tools.py     # Shell execution
│   ├── git_tools.py       # Git operations
│   └── patch_tools.py     # Diff/patch/fuzzy edit
├── workspace/              # Filesystem abstraction
│   └── fs.py              # Local, chat-scoped, unbounded FS
├── skills/                 # Skills system
│   └── store.py           # Skill discovery & execution
├── shell/                  # Shell execution
│   └── executor.py        # Async subprocess with PTY
└── ui/                     # PyQt6 UI
    ├── main_window.py     # Main window
    ├── chat_panel.py      # Chat with streaming
    ├── file_editor.py     # QScintilla editor
    ├── terminal_widget.py # PTY terminal
    ├── browser_widget.py  # WebEngine browser
    └── settings_dialog.py # Settings UI
```

## Installation

```bash
# Clone and enter directory
cd windows-harness

# Create virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install PyQt6 WebEngine (required for browser)
pip install PyQt6-WebEngine

# Run
python main.py
```

## Requirements

- Python 3.11+
- Windows 10/11
- PyQt6 with WebEngine
- qasync for async/Qt integration

## Configuration

Settings are stored in `%APPDATA%\windows-harness\settings.json`
API keys are stored securely in Windows Credential Manager.

## LLM Providers

Configure in Settings → Providers:

| Provider | Models | Setup |
|----------|--------|-------|
| OpenAI | GPT-4o, GPT-4o-mini, GPT-4-turbo | API key |
| Anthropic | Claude 3.5 Sonnet, Haiku, Opus | API key |
| Google | Gemini 1.5 Pro, Flash | API key |
| Ollama | Local models (llama3, codellama, etc.) | localhost:11434 |
| LM Studio | Local models | localhost:1234 |

## Skills

Skills are defined in `skills/` directory as YAML files:

```yaml
id: my-skill
name: My Skill
version: "1.0.0"
description: Does something useful
category: custom
parameters:
  - name: target
    type: string
    required: true
steps:
  - name: read_file
    tool: read
    arguments:
      path: ${params.target}
```

Built-in skills: caveman-commit, caveman-investigate, tdd-workflow, code-review, etc.

## Development

```bash
# Run tests
pytest tests/

# Type check
mypy windows-harness/

# Format
ruff format windows-harness/
```

## Building Standalone Executable

### Quick Build (Windows)

```cmd
# Run the build script (installs deps, builds .exe)
build.bat
```

Output: `dist/WindowsHarness.exe` (~100-150 MB)

### Manual Build

```cmd
# 1. Install dependencies
pip install -r requirements.txt
pip install PyQt6-WebEngine PyQt6-Qscintilla pyinstaller

# 2. Convert icon (requires ImageMagick)
magick assets/icon.svg assets/icon.ico

# 3. Build with PyInstaller
pyinstaller windows-harness.spec --clean
```

### GitHub Actions (Automated)

Push a version tag to trigger automated build:

```bash
git tag v0.1.0
git push origin v0.1.0
```

The workflow will:
1. Build on Windows runner
2. Create `WindowsHarness-v0.1.0-windows-x64.zip`
3. Attach to GitHub Release

Download from: https://github.com/mrmakrider/WindowsHarness/releases

## License

MIT License - See LICENSE file.

## Credits

Based on [AndroidHarness](https://github.com/Sanuu7/AndroidHarness) by Sanuu7.
Ported to Windows with Python/PyQt6.
