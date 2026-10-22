# WindowsHarness - Architecture Document

Port of AndroidHarness (AI Coding Agent) to native Windows using **Python 3.11+ / PyQt6**.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        PyQt6 Application                        │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │   Main      │  │   Chat      │  │   File      │   UI Layer   │
│  │   Window    │  │   Panel     │  │   Editor    │              │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘              │
│         │                │                │                      │
│  ┌──────┴────────────────┴────────────────┴──────┐             │
│  │              Agent Controller                  │  ← Orchestrates runs
│  │  (asyncio event loop + Qt integration)         │             │
│  └────────────────────┬──────────────────────────┘             │
│                       │                                        │
│  ┌────────────────────┼──────────────────────────┐             │
│  │                    ▼                          │             │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐     │  Core Services│
│  │  │  LLM     │ │  Tool    │ │ Workspace│     │               │
│  │  │ Client   │ │ Registry │ │   FS     │     │               │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘     │               │
│  │       │            │            │            │               │
│  │  ┌────┴─────┐ ┌────┴─────┐ ┌────┴─────┐     │               │
│  │  │  Shell   │ │  Git     │ │ Browser  │     │  Tools        │
│  │  │ Executor │ │  Client  │ │Automation│     │               │
│  │  └──────────┘ └──────────┘ └──────────┘     │               │
│  └──────────────────────────────────────────────┘               │
│                       │                                        │
│  ┌────────────────────┴──────────────────────────┐             │
│  │              Skills System                      │             │
│  │  (YAML/JSON skill definitions + Python hooks)   │             │
│  └────────────────────────────────────────────────┘             │
└─────────────────────────────────────────────────────────────────┘
```

## Module Breakdown

### 1. Core (`core/`)
| Module | Responsibility | AndroidHarness Equivalent |
|--------|---------------|--------------------------|
| `agent_engine.py` | Main agent loop, tool execution, streaming | `AgentEngine.kt`, `RunManager.kt` |
| `agent_events.py` | Event definitions (Text, ToolCall, Approval, etc.) | `AgentEvent` sealed class |
| `permission_mode.py` | Permission modes (CONFIRM_ALL, FULL_AUTO, etc.) | `PermissionMode` enum |
| `context_hygiene.py` | Context compaction, tool result shrinking | `ContextHygiene.kt` |
| `history_compactor.py` | Summarize history when context grows | `HistoryCompactor.kt` |
| `token_counter.py` | Token estimation for context budgeting | `estimateContext()` |

### 2. LLM (`llm/`)
| Module | Responsibility | AndroidHarness Equivalent |
|--------|---------------|--------------------------|
| `providers/base.py` | Abstract provider interface | `LlmProvider` interface |
| `providers/openai.py` | OpenAI API (Chat Completions + Responses) | `OpenAiCompatProvider`, `OpenAiResponsesProvider` |
| `providers/anthropic.py` | Anthropic API | `AnthropicProvider` |
| `providers/gemini.py` | Google Gemini API | `GeminiProvider` |
| `providers/openai_compat.py` | OpenAI-compatible (Ollama, LM Studio, etc.) | `OpenAiCompatProvider` |
| `providers/local.py` | Local models (llama.cpp, etc.) | `LocalModelCatalog` |
| `model_catalog.py` | Model discovery, capabilities, pricing | `ModelCatalog`, `ModelsDev` |
| `streaming.py` | Stream event parsing (text, tool_calls, thinking) | `StreamEvent` |

### 3. Tools (`tools/`)
| Module | Responsibility | AndroidHarness Equivalent |
|--------|---------------|--------------------------|
| `registry.py` | Tool registration, schema generation | `ToolRegistry` |
| `base.py` | Tool base class, context, result types | `Tool`, `ToolContext`, `ToolResult` |
| `file_tools.py` | Read, write, edit, list, glob, grep | `FileTools.kt` |
| `shell_tools.py` | Shell execution, background processes | `BgShell.kt`, `ShellTool` |
| `git_tools.py` | Git operations (status, diff, commit, push) | `GitTools.kt` |
| `patch_tools.py` | Apply unified diffs, fuzzy edits | `PatchTools.kt`, `FuzzyEdit.kt` |
| `browser_tools.py` | Navigate, click, type, screenshot, eval | `BrowserTools.kt` |
| `net_tools.py` | HTTP requests, WebSocket, TLS | `NetTools.kt`, `NetTls.kt` |
| `github_tools.py` | GitHub API (issues, PRs, repo ops) | GitHub integration in agent |
| `doctor_tools.py` | Environment diagnostics | `DoctorTool.kt`, `EnvStatusTool.kt` |
| `memory_tools.py` | Read/write memory notes | `MemoryTools.kt` |
| `codegraph_tools.py` | Code graph queries | `CodeGraphTools.kt` |

### 4. Workspace (`workspace/`)
| Module | Responsibility | AndroidHarness Equivalent |
|--------|---------------|--------------------------|
| `fs.py` | Abstract filesystem interface | `WorkspaceFs` interface |
| `local_fs.py` | Local filesystem implementation | `ChatWorkspaceFs`, `UnboundedFileFs` |
| `git_fs.py` | Git-aware workspace (diff base) | Git integration in workspace |

### 5. Shell (`shell/`)
| Module | Responsibility | AndroidHarness Equivalent |
|--------|---------------|--------------------------|
| `executor.py` | Async subprocess with PTY, streaming output | Shell in `BgShell.kt` |
| `pty.py` | Pseudoterminal management (Windows: winpty/conpty) | Android PTY |
| `env_manager.py` | Toolchain detection (git, python, node, npm) | `LinuxEnvironmentManager` |

### 6. Browser (`browser/`)
| Module | Responsibility | AndroidHarness Equivalent |
|--------|---------------|--------------------------|
| `automation.py` | High-level browser automation API | `BrowserTools.kt` |
| `webengine.py` | Qt WebEngine wrapper | WebView in Android |
| `dom.py` | DOM inspection, element selection | DOM indexing in BrowserTools |

### 7. Skills (`skills/`)
| Module | Responsibility | AndroidHarness Equivalent |
|--------|---------------|--------------------------|
| `store.py` | Skill discovery, loading, validation | `SkillStore` |
| `loader.py` | YAML/JSON → Python module loading | Skill loading in Android |
| `builtin/` | Built-in skills (caveman, tdd, etc.) | Bundled skills |

### 8. GitHub (`github/`)
| Module | Responsibility | AndroidHarness Equivalent |
|--------|---------------|--------------------------|
| `client.py` | GitHub REST/GraphQL API wrapper | GitHub integration |
| `auth.py` | Token management (GH_TOKEN, gh CLI) | GitHub auth in Android |

### 9. UI (`ui/`)
| Module | Responsibility | AndroidHarness Equivalent |
|--------|---------------|--------------------------|
| `main_window.py` | Main application window | `MainActivity` + Compose |
| `chat_panel.py` | Chat message list, streaming render | Chat Compose UI |
| `file_editor.py` | Syntax-highlighted editor (QScintilla) | Editor Compose |
| `terminal_widget.py` | PTY-backed terminal | Terminal in Android |
| `browser_widget.py` | WebEngine browser preview | WebView |
| `diff_viewer.py` | Side-by-side/inline diff | Diff viewer Compose |
| `settings_dialog.py` | Settings, providers, skills | Settings Compose |
| `components/` | Reusable Qt widgets | Compose components |

### 10. Config (`config/`)
| Module | Responsibility |
|--------|---------------|
| `settings.py` | App settings (JSON + Pydantic) |
| `providers.py` | Provider configurations |
| `keyring.py` | Secure API key storage (keyring) |

## Data Flow

```
User Input → Chat Panel → Agent Controller → Agent Engine
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    ▼                         ▼                         ▼
              LLM Provider              Tool Registry              Workspace
              (streaming)               (executes)                 (files)
                    │                         │                         │
                    └─────────────────────────┼─────────────────────────┘
                                              ▼
                                        Agent Events
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    ▼                         ▼                         ▼
              Chat Panel                File Editor                Terminal
              (text, thinking)          (diffs, edits)             (shell output)
```

## Async/Qt Integration

- **Main thread**: Qt event loop (GUI)
- **Agent runs**: `asyncio` tasks on a dedicated thread pool
- **Bridge**: `asyncqt` or `qasync` for async/await in Qt slots
- **Streaming**: LLM tokens → Qt signals → Chat panel updates

## Configuration Files

```
windows-harness/
├── config/
│   ├── settings.json          # User settings
│   ├── providers.json         # LLM provider configs
│   ├── skills/                # Skill definitions (YAML)
│   └── keyring/               # Encrypted API keys (OS keyring)
├── data/
│   ├── workspace/             # Default workspace
│   └── checkpoints/           # Agent checkpoints
├── logs/
└── temp/
```

## Key Design Decisions

1. **Python over C#**: Better AI/LLM ecosystem, easier shell/PTY, faster prototyping
2. **PyQt6 over Tkinter**: WebEngine for browser, QScintilla for editor, mature
3. **asyncio + qasync**: Native async/await with Qt signal/slot integration
4. **Pydantic v2**: Settings validation, serialization, type safety
5. **keyring**: Cross-platform secure credential storage
6. **Modular tools**: Each tool = independent class, easy to extend
7. **Skill system**: YAML-defined + Python hooks, matches AndroidHarness
8. **No Android-specific**: Shizuku, SAF, notifications → native Windows equivalents

## Porting Priority

| Phase | Modules | Est. Effort |
|-------|---------|-------------|
| 1. Foundation | Config, FS, Shell, Settings | 1-2 days |
| 2. LLM Core | Providers, streaming, model catalog | 2-3 days |
| 3. Agent Loop | AgentEngine, events, context hygiene | 3-4 days |
| 4. Tools | File, Shell, Git, Patch, Browser | 3-4 days |
| 5. UI - Chat | Main window, chat panel, streaming | 2-3 days |
| 6. UI - Editor | File editor, diff viewer, tabs | 2-3 days |
| 7. UI - Terminal | PTY terminal widget | 1-2 days |
| 8. UI - Browser | WebEngine automation | 1-2 days |
| 9. Skills | Store, loader, built-in skills | 1-2 days |
| 10. GitHub | API client, auth, tools | 1-2 days |
| 11. Polish | Settings, shortcuts, themes, packaging | 2-3 days |

**Total: ~3-4 weeks for MVP**
