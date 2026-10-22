"""
Skills System for WindowsHarness.

Manages skill discovery, loading, validation, and execution.
Skills are defined in YAML/JSON with optional Python hooks.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import yaml
from pydantic import BaseModel, Field

from core.types import ToolResult, ToolCallData
from tools.registry import Tool, ToolContext, register_tool, ToolRegistry


class SkillParameter(BaseModel):
    """Skill parameter definition."""

    name: str
    type: str = "string"
    description: str = ""
    required: bool = True
    default: Any = None
    enum: list[Any] = Field(default_factory=list)


class SkillStep(BaseModel):
    """A step in a skill workflow."""

    name: str
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    description: str = ""
    condition: Optional[str] = None  # Python expression to evaluate
    loop: Optional[str] = None  # For loops: "item in items"


class SkillManifest(BaseModel):
    """Skill manifest/metadata."""

    id: str
    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    category: str = "general"
    tags: list[str] = Field(default_factory=list)
    parameters: list[SkillParameter] = Field(default_factory=list)
    steps: list[SkillStep] = Field(default_factory=list)
    # Python hook file (optional)
    python_file: Optional[str] = None
    # Entry point function in python_file
    entry_point: str = "run"
    # Requirements
    requires_approval: bool = False
    # UI hints
    icon: str = "🔧"
    color: str = "#003087"


class SkillContext:
    """Context provided to skill execution."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        workspace_fs: Any,
        session_id: str,
        parameters: dict[str, Any],
        metadata: Optional[dict[str, Any]] = None,
    ):
        self.tool_registry = tool_registry
        self.workspace_fs = workspace_fs
        self.session_id = session_id
        self.parameters = parameters
        self.metadata = metadata or {}
        self._state: dict[str, Any] = {}  # For passing data between steps

    def get_state(self, key: str, default: Any = None) -> Any:
        return self._state.get(key, default)

    def set_state(self, key: str, value: Any) -> None:
        self._state[key] = value


class Skill(ABC):
    """Base class for skills."""

    def __init__(self, manifest: SkillManifest):
        self.manifest = manifest
        self._python_module = None
        self._entry_func = None

    @property
    def id(self) -> str:
        return self.manifest.id

    @property
    def name(self) -> str:
        return self.manifest.name

    def load_python_hook(self, skill_dir: Path) -> bool:
        """Load Python hook module if specified."""
        if not self.manifest.python_file:
            return False

        py_path = skill_dir / self.manifest.python_file
        if not py_path.exists():
            return False

        try:
            spec = importlib.util.spec_from_file_location(f"skill_{self.manifest.id}", py_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[f"skill_{self.manifest.id}"] = module
                spec.loader.exec_module(module)

                if hasattr(module, self.manifest.entry_point):
                    self._entry_func = getattr(module, self.manifest.entry_point)
                    self._python_module = module
                    return True
        except Exception as e:
            print(f"[Skill] Failed to load Python hook for {self.manifest.id}: {e}")
        return False

    async def execute(self, context: SkillContext) -> ToolResult:
        """Execute the skill."""
        # Try Python hook first
        if self._entry_func:
            try:
                result = self._entry_func(context)
                if hasattr(result, "__await__"):
                    result = await result
                if isinstance(result, ToolResult):
                    return result
                return ToolResult.ok(output=result, display=str(result))
            except Exception as e:
                return ToolResult.err(f"Python hook error: {e}", display=f"❌ Skill {self.manifest.name} failed: {e}")

        # Fall back to step-based execution
        return await self._execute_steps(context)

    async def _execute_steps(self, context: SkillContext) -> ToolResult:
        """Execute skill steps sequentially."""
        results = []

        for step in self.manifest.steps:
            # Check condition
            if step.condition:
                try:
                    # Simple eval - in production, use a safe evaluator
                    if not eval(step.condition, {"context": context, "params": context.parameters}):
                        continue
                except Exception:
                    continue

            # Handle loops
            if step.loop:
                # Parse loop expression: "item in items"
                parts = step.loop.split(" in ")
                if len(parts) == 2:
                    var_name = parts[0].strip()
                    iter_expr = parts[1].strip()
                    try:
                        items = eval(iter_expr, {"context": context, "params": context.parameters})
                        for item in items:
                            context.set_state(var_name, item)
                            step_result = await self._execute_single_step(step, context)
                            results.append(step_result)
                            if not step_result.success and step_result.error:
                                return step_result
                        continue  # Skip single execution below
                    except Exception as e:
                        return ToolResult.err(f"Loop error: {e}")

            # Single execution
            step_result = await self._execute_single_step(step, context)
            results.append(step_result)

            if not step_result.success and step_result.error:
                return step_result

        # Return last result
        return results[-1] if results else ToolResult.ok(output="No steps executed")

    async def _execute_single_step(self, step: SkillStep, context: SkillContext) -> ToolResult:
        """Execute a single step."""
        # Resolve arguments with context
        resolved_args = {}
        for key, value in step.arguments.items():
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                # Variable reference: ${params.x} or ${state.x}
                var_path = value[2:-1]
                if var_path.startswith("params."):
                    resolved_args[key] = context.parameters.get(var_path[7:])
                elif var_path.startswith("state."):
                    resolved_args[key] = context.get_state(var_path[6:])
                else:
                    resolved_args[key] = value
            else:
                resolved_args[key] = value

        # Execute tool
        tool_call = ToolCallData(
            id=f"skill_{uuid.uuid4().hex[:8]}",
            name=step.tool,
            arguments=resolved_args,
        )

        return await context.tool_registry.execute(tool_call, context=context)


class SkillStore:
    """Manages skill discovery, loading, and registry."""

    def __init__(self, skills_dir: Path, tool_registry: ToolRegistry, workspace_fs: Any):
        self.skills_dir = skills_dir
        self.tool_registry = tool_registry
        self.workspace_fs = workspace_fs
        self._skills: dict[str, Skill] = {}
        self._manifests: dict[str, SkillManifest] = {}

    def discover_skills(self) -> list[SkillManifest]:
        """Discover all skills in the skills directory."""
        manifests = []

        for skill_dir in self.skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue

            # Look for manifest file
            manifest_path = skill_dir / "skill.yaml"
            if not manifest_path.exists():
                manifest_path = skill_dir / "skill.json"

            if not manifest_path.exists():
                continue

            try:
                if manifest_path.suffix == ".yaml":
                    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
                else:
                    data = json.loads(manifest_path.read_text(encoding="utf-8"))

                manifest = SkillManifest(**data)
                manifests.append(manifest)
            except Exception as e:
                print(f"[SkillStore] Failed to load skill from {skill_dir}: {e}")

        return manifests

    def load_skill(self, manifest: SkillManifest) -> Skill:
        """Load a skill from its manifest."""
        if manifest.id in self._skills:
            return self._skills[manifest.id]

        skill = Skill(manifest)
        skill_dir = self.skills_dir / manifest.id

        # Load Python hook if present
        skill.load_python_hook(skill_dir)

        self._skills[manifest.id] = skill
        self._manifests[manifest.id] = manifest
        return skill

    def get_skill(self, skill_id: str) -> Optional[Skill]:
        """Get a loaded skill by ID."""
        if skill_id in self._skills:
            return self._skills[skill_id]

        # Try to load
        manifest = self._manifests.get(skill_id)
        if manifest:
            return self.load_skill(manifest)
        return None

    def get_manifest(self, skill_id: str) -> Optional[SkillManifest]:
        """Get skill manifest by ID."""
        return self._manifests.get(skill_id)

    def list_skills(self, category: Optional[str] = None) -> list[SkillManifest]:
        """List all loaded skills."""
        skills = list(self._manifests.values())
        if category:
            skills = [s for s in skills if s.category == category]
        return skills

    def get_categories(self) -> list[str]:
        """Get all skill categories."""
        return list(set(s.category for s in self._manifests.values()))

    async def execute_skill(
        self,
        skill_id: str,
        session_id: str,
        parameters: dict[str, Any],
        metadata: Optional[dict[str, Any]] = None,
    ) -> ToolResult:
        """Execute a skill by ID."""
        skill = self.get_skill(skill_id)
        if not skill:
            return ToolResult.err(f"Skill not found: {skill_id}")

        context = SkillContext(
            tool_registry=self.tool_registry,
            workspace_fs=self.workspace_fs,
            session_id=session_id,
            parameters=parameters,
            metadata=metadata,
        )

        return await skill.execute(context)

    def reload_all(self) -> int:
        """Reload all skills from disk."""
        self._skills.clear()
        self._manifests.clear()
        manifests = self.discover_skills()
        for manifest in manifests:
            self.load_skill(manifest)
        return len(manifests)


# Global skill store
_skill_store: Optional[SkillStore] = None


def get_skill_store(
    skills_dir: Optional[Path] = None,
    tool_registry: Optional[ToolRegistry] = None,
    workspace_fs: Any = None,
) -> SkillStore:
    global _skill_store
    if _skill_store is None:
        if skills_dir is None:
            skills_dir = Path("skills")
        if tool_registry is None:
            from tools.registry import get_tool_registry
            tool_registry = get_tool_registry()
        _skill_store = SkillStore(skills_dir, tool_registry, workspace_fs)
    return _skill_store


def register_builtin_skills():
    """Register built-in skills."""
    # This would register the caveman, tdd, etc. skills
    pass
