"""
WindowsHarness Configuration System

Pydantic-based settings with validation, serialization, and secure key storage.
Compatible with both pydantic v1 and v2.
"""

from __future__ import annotations

import json
import os
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import keyring

# Handle pydantic v1 vs v2 compatibility
try:
    from pydantic import BaseModel, Field, field_validator
    from pydantic import VERSION as PYDANTIC_VERSION
    PYDANTIC_V2 = PYDANTIC_VERSION.startswith("2.")
except ImportError:
    # pydantic v1
    from pydantic import BaseModel, Field, validator as field_validator
    PYDANTIC_V2 = False

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ImportError:
    # pydantic v1
    from pydantic import BaseSettings
    SettingsConfigDict = dict


class PermissionMode(str, Enum):
    """Permission modes for agent tool execution."""

    CONFIRM_ALL = "confirm_all"  # Ask before every tool
    ALLOW_LIST = "allow_list"  # Auto-allow listed tools, confirm others
    FULL_AUTO = "full_auto"  # Never ask (use with caution)


class ThemeMode(str, Enum):
    """UI theme modes."""

    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


class LogLevel(str, Enum):
    """Logging levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class ProviderType(str, Enum):
    """Supported LLM provider types."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OPENAI_COMPAT = "openai_compat"  # Ollama, LM Studio, etc.
    LOCAL = "local"  # llama.cpp, etc.


class ProviderConfig(BaseModel):
    """Configuration for a single LLM provider."""

    name: str
    type: ProviderType
    api_key: Optional[str] = None  # Stored in keyring, not here
    base_url: Optional[str] = None
    organization: Optional[str] = None
    default_model: Optional[str] = None
    models: list[str] = Field(default_factory=list)
    enabled: bool = True
    extra_headers: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int = 120
    max_retries: int = 3

    def get_api_key(self) -> Optional[str]:
        """Retrieve API key from system keyring."""
        if not self.api_key:
            return None
        return keyring.get_password("windows-harness", f"provider:{self.name}")

    def set_api_key(self, key: str) -> None:
        """Store API key in system keyring."""
        keyring.set_password("windows-harness", f"provider:{self.name}", key)


class AgentSettings(BaseModel):
    """Agent behavior settings."""

    permission_mode: PermissionMode = PermissionMode.CONFIRM_ALL
    max_turns: int = 50
    max_context_tokens: int = 128000
    auto_compact_threshold: float = 0.85  # Compact when 85% full
    show_thinking: bool = True
    stream_tool_calls: bool = True
    default_workspace: Optional[str] = None
    allowed_tools: list[str] = Field(default_factory=list)  # For ALLOW_LIST mode
    denied_tools: list[str] = Field(default_factory=list)


class UISettings(BaseModel):
    """UI appearance and behavior settings."""

    theme: ThemeMode = ThemeMode.SYSTEM
    font_family: str = "Consolas"
    font_size: int = 11
    editor_font_size: int = 12
    terminal_font_size: int = 11
    show_line_numbers: bool = True
    word_wrap: bool = False
    minimap: bool = False
    animate_streaming: bool = True
    compact_mode: bool = False
    language: str = "en"


class TerminalSettings(BaseModel):
    """Terminal emulator settings."""

    shell: str = ""  # Auto-detect: powershell, cmd, pwsh, bash (WSL)
    cursor_blink: bool = True
    cursor_shape: str = "block"  # block, underline, bar
    scrollback_lines: int = 10000
    bell: bool = False
    copy_on_select: bool = True


class BrowserSettings(BaseModel):
    """Browser automation settings."""

    headless: bool = False
    viewport_width: int = 1280
    viewport_height: int = 720
    user_agent: str = ""
    download_path: str = ""
    enable_javascript: bool = True
    enable_webgl: bool = True


class ShellSettings(BaseModel):
    """Shell execution settings."""

    default_shell: str = ""  # Auto-detect
    env_vars: dict[str, str] = Field(default_factory=dict)
    working_dir: str = ""
    timeout_seconds: int = 300
    max_output_lines: int = 5000


class LoggingSettings(BaseModel):
    """Logging configuration."""

    level: LogLevel = LogLevel.INFO
    file_enabled: bool = True
    file_path: str = "logs/harness.log"
    max_file_size_mb: int = 10
    max_files: int = 5
    console_enabled: bool = True


class GitHubSettings(BaseModel):
    """GitHub integration settings."""

    token: Optional[str] = None  # Stored in keyring
    default_owner: str = ""
    default_repo: str = ""

    def get_token(self) -> Optional[str]:
        if not self.token:
            return None
        return keyring.get_password("windows-harness", "github:token")

    def set_token(self, token: str) -> None:
        keyring.set_password("windows-harness", "github:token", token)


class SkillsSettings(BaseModel):
    """Skills system settings."""

    enabled: bool = True
    custom_skills_dir: str = "skills/custom"
    auto_update_builtin: bool = True


# Pydantic v1/v2 compatible config
if PYDANTIC_V2:
    class AppSettings(BaseSettings):
        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            env_nested_delimiter="__",
            extra="ignore",
        )

        # Version for migration
        version: int = 1

        # Core settings
        agent: AgentSettings = Field(default_factory=AgentSettings)
        ui: UISettings = Field(default_factory=UISettings)
        terminal: TerminalSettings = Field(default_factory=TerminalSettings)
        browser: BrowserSettings = Field(default_factory=BrowserSettings)
        shell: ShellSettings = Field(default_factory=ShellSettings)
        logging: LoggingSettings = Field(default_factory=LoggingSettings)
        github: GitHubSettings = Field(default_factory=GitHubSettings)
        skills: SkillsSettings = Field(default_factory=SkillsSettings)

        # Provider configs (keys in keyring)
        providers: list[ProviderConfig] = Field(default_factory=list)

        # Runtime state (not persisted)
        _config_path: Optional[Path] = None

        @field_validator("providers", mode="before")
        @classmethod
        def _validate_providers(cls, v: Any) -> list[ProviderConfig]:
            if isinstance(v, list):
                return [ProviderConfig(**p) if isinstance(p, dict) else p for p in v]
            return v

        def get_provider(self, name: str) -> Optional[ProviderConfig]:
            """Get provider config by name."""
            for p in self.providers:
                if p.name == name:
                    return p
            return None

        def add_provider(self, config: ProviderConfig) -> None:
            """Add or update a provider config."""
            self.providers = [p for p in self.providers if p.name != config.name]
            self.providers.append(config)

        def remove_provider(self, name: str) -> bool:
            """Remove a provider config."""
            before = len(self.providers)
            self.providers = [p for p in self.providers if p.name != name]
            return len(self.providers) < before

else:
    # Pydantic v1
    class AppSettings(BaseSettings):
        class Config:
            env_file = ".env"
            env_file_encoding = "utf-8"
            env_nested_delimiter = "__"
            extra = "ignore"

        # Version for migration
        version: int = 1

        # Core settings
        agent: AgentSettings = Field(default_factory=AgentSettings)
        ui: UISettings = Field(default_factory=UISettings)
        terminal: TerminalSettings = Field(default_factory=TerminalSettings)
        browser: BrowserSettings = Field(default_factory=BrowserSettings)
        shell: ShellSettings = Field(default_factory=ShellSettings)
        logging: LoggingSettings = Field(default_factory=LoggingSettings)
        github: GitHubSettings = Field(default_factory=GitHubSettings)
        skills: SkillsSettings = Field(default_factory=SkillsSettings)

        # Provider configs (keys in keyring)
        providers: list[ProviderConfig] = Field(default_factory=list)

        # Runtime state (not persisted)
        _config_path: Optional[Path] = None

        @field_validator("providers")
        def _validate_providers(cls, v: Any) -> list[ProviderConfig]:
            if isinstance(v, list):
                return [ProviderConfig(**p) if isinstance(p, dict) else p for p in v]
            return v

        def get_provider(self, name: str) -> Optional[ProviderConfig]:
            """Get provider config by name."""
            for p in self.providers:
                if p.name == name:
                    return p
            return None

        def add_provider(self, config: ProviderConfig) -> None:
            """Add or update a provider config."""
            self.providers = [p for p in self.providers if p.name != config.name]
            self.providers.append(config)

        def remove_provider(self, name: str) -> bool:
            """Remove a provider config."""
            before = len(self.providers)
            self.providers = [p for p in self.providers if p.name != name]
            return len(self.providers) < before


# --- Settings Manager ---


class SettingsManager:
    """Manages loading, saving, and migration of settings."""

    DEFAULT_CONFIG_NAME = "settings.json"

    def __init__(self, config_dir: Optional[Path] = None):
        if config_dir is None:
            config_dir = Path(os.getenv("APPDATA", Path.home())) / "windows-harness"
        self.config_dir = config_dir
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.config_dir / self.DEFAULT_CONFIG_NAME
        self._settings: Optional[AppSettings] = None

    @property
    def settings(self) -> AppSettings:
        if self._settings is None:
            self._settings = self.load()
        return self._settings

    def load(self) -> AppSettings:
        """Load settings from JSON file."""
        if self.config_path.exists():
            try:
                data = json.loads(self.config_path.read_text(encoding="utf-8"))
                settings = AppSettings(**data)
                settings._config_path = self.config_path
                return settings
            except Exception as e:
                # Backup corrupted config and start fresh
                backup = self.config_path.with_suffix(".json.bak")
                self.config_path.rename(backup)
                print(f"[Settings] Corrupted config backed up to {backup}: {e}")

        # Return defaults
        settings = AppSettings()
        settings._config_path = self.config_path
        return settings

    def save(self, settings: Optional[AppSettings] = None) -> None:
        """Save settings to JSON file."""
        if settings is None:
            settings = self._settings
        if settings is None:
            return

        # Don't persist runtime fields
        if PYDANTIC_V2:
            data = settings.model_dump(exclude={"_config_path"})
        else:
            data = settings.dict(exclude={"_config_path"})

        # Atomic write
        tmp_path = self.config_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(self.config_path)

    def reset_to_defaults(self) -> AppSettings:
        """Reset to default settings."""
        self._settings = AppSettings()
        self._settings._config_path = self.config_path
        self.save()
        return self._settings


# Global instance
_settings_manager: Optional[SettingsManager] = None


def get_settings_manager(config_dir: Optional[Path] = None) -> SettingsManager:
    """Get global settings manager instance."""
    global _settings_manager
    if _settings_manager is None:
        _settings_manager = SettingsManager(config_dir)
    return _settings_manager


def get_settings() -> AppSettings:
    """Get current settings."""
    return get_settings_manager().settings


def save_settings() -> None:
    """Save current settings."""
    get_settings_manager().save()
