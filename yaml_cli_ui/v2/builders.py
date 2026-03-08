"""Raw YAML-to-model builders for v2 document loading."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import V2LoadError
from .models import (
    CommandDef,
    ForeachSpec,
    ImportDef,
    LauncherDef,
    OnErrorSpec,
    ParamDef,
    ParamType,
    PipelineDef,
    ProfileDef,
    RunSpec,
    SecretSource,
    StepSpec,
    V2Document,
)


def build_v2_document(
    *, raw_doc: dict[str, Any], source_path: Path, imported_documents: dict[str, V2Document]
) -> V2Document:
    raw_imports = raw_doc.get("imports", {}) if isinstance(raw_doc.get("imports", {}), dict) else {}
    imports = {
        alias: ImportDef(alias=alias, path=raw_imports.get(alias, ""), resolved_path=doc.source_path)
        for alias, doc in imported_documents.items()
    }

    return V2Document(
        version=raw_doc.get("version", 0),
        imports=imports,
        profiles=_build_profiles(raw_doc, source_path),
        params=_build_params(raw_doc, source_path),
        locals=_require_mapping(raw_doc.get("locals", {}), "locals", source_path),
        commands=_build_commands(raw_doc, source_path),
        pipelines=_build_pipelines(raw_doc, source_path),
        launchers=_build_launchers(raw_doc, source_path),
        imported_documents=imported_documents,
        source_path=source_path,
        base_dir=source_path.parent,
        raw=raw_doc,
    )


def _require_mapping(value: Any, field_name: str, source_path: Path) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise V2LoadError(f"field '{field_name}' must be a mapping in file: {source_path}")
    return value


def _build_profiles(raw_doc: dict[str, Any], source_path: Path) -> dict[str, ProfileDef]:
    raw_profiles = _require_mapping(raw_doc.get("profiles", {}), "profiles", source_path)
    profiles: dict[str, ProfileDef] = {}
    for name, entry in raw_profiles.items():
        if not isinstance(entry, dict):
            raise V2LoadError(f"profile '{name}' must be a mapping in file: {source_path}")
        profiles[name] = ProfileDef(
            workdir=entry.get("workdir"),
            env=entry.get("env", {}) if isinstance(entry.get("env"), dict) else {},
            runtimes=entry.get("runtimes", {}) if isinstance(entry.get("runtimes"), dict) else {},
        )
    return profiles


def _build_params(raw_doc: dict[str, Any], source_path: Path) -> dict[str, ParamDef]:
    raw_params = _require_mapping(raw_doc.get("params", {}), "params", source_path)
    params: dict[str, ParamDef] = {}
    for name, entry in raw_params.items():
        if not isinstance(entry, dict):
            raise V2LoadError(f"param '{name}' must be a mapping in file: {source_path}")
        param_type = entry.get("type", ParamType.STRING)
        if isinstance(param_type, str):
            try:
                param_type = ParamType(param_type)
            except ValueError:
                param_type = ParamType.STRING
        params[name] = ParamDef(
            type=param_type,
            title=entry.get("title"),
            required=bool(entry.get("required", False)),
            default=entry.get("default"),
            options=entry.get("options") if isinstance(entry.get("options"), list) else None,
            min=entry.get("min"),
            max=entry.get("max"),
            step=entry.get("step"),
            must_exist=entry.get("must_exist"),
            source=SecretSource(entry["source"]) if entry.get("source") in {"env", "vault"} else None,
            env=entry.get("env"),
            key=entry.get("key"),
        )
    return params


def _build_commands(raw_doc: dict[str, Any], source_path: Path) -> dict[str, CommandDef]:
    raw_commands = _require_mapping(raw_doc.get("commands", {}), "commands", source_path)
    commands: dict[str, CommandDef] = {}
    for name, entry in raw_commands.items():
        if not isinstance(entry, dict):
            raise V2LoadError(f"command '{name}' must be a mapping in file: {source_path}")
        run_raw = entry.get("run")
        if isinstance(run_raw, dict):
            run = RunSpec(
                program=run_raw.get("program") or "__missing_program__",
                argv=run_raw.get("argv", []),
                workdir=run_raw.get("workdir"),
                env=run_raw.get("env") if isinstance(run_raw.get("env"), dict) else {},
                timeout_ms=run_raw.get("timeout_ms"),
                stdout=run_raw.get("stdout"),
                stderr=run_raw.get("stderr"),
            )
        else:
            run = RunSpec(program="__missing_program__", argv=[])

        commands[name] = CommandDef(
            title=entry.get("title"),
            info=entry.get("info"),
            when=entry.get("when"),
            continue_on_error=bool(entry.get("continue_on_error", False)),
            run=run,
            on_error=_build_on_error(entry.get("on_error"), source_path),
        )
    return commands


def _build_pipelines(raw_doc: dict[str, Any], source_path: Path) -> dict[str, PipelineDef]:
    raw_pipelines = _require_mapping(raw_doc.get("pipelines", {}), "pipelines", source_path)
    pipelines: dict[str, PipelineDef] = {}
    for name, entry in raw_pipelines.items():
        if not isinstance(entry, dict):
            raise V2LoadError(f"pipeline '{name}' must be a mapping in file: {source_path}")
        steps = _build_steps(entry.get("steps"), source_path)
        pipelines[name] = PipelineDef(
            title=entry.get("title"),
            info=entry.get("info"),
            when=entry.get("when"),
            continue_on_error=bool(entry.get("continue_on_error", False)),
            steps=steps,
            on_error=_build_on_error(entry.get("on_error"), source_path),
        )
    return pipelines


def _build_launchers(raw_doc: dict[str, Any], source_path: Path) -> dict[str, LauncherDef]:
    raw_launchers = _require_mapping(raw_doc.get("launchers", {}), "launchers", source_path)
    launchers: dict[str, LauncherDef] = {}
    for name, entry in raw_launchers.items():
        if not isinstance(entry, dict):
            raise V2LoadError(f"launcher '{name}' must be a mapping in file: {source_path}")
        launchers[name] = LauncherDef(
            title=entry.get("title") or "",
            use=entry.get("use") or "",
            info=entry.get("info"),
            with_values=entry.get("with") if isinstance(entry.get("with"), dict) else {},
        )
    return launchers


def _build_on_error(raw: Any, source_path: Path) -> OnErrorSpec | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise V2LoadError(f"field 'on_error' must be mapping in file: {source_path}")
    return OnErrorSpec(steps=_build_steps(raw.get("steps"), source_path))


def _build_steps(raw_steps: Any, source_path: Path) -> list[StepSpec | str]:
    if raw_steps is None:
        return []
    if not isinstance(raw_steps, list):
        raise V2LoadError(f"field 'steps' must be list in file: {source_path}")

    steps: list[StepSpec | str] = []
    for item in raw_steps:
        if isinstance(item, str):
            steps.append(item)
            continue
        if not isinstance(item, dict):
            raise V2LoadError(f"step item must be string or mapping in file: {source_path}")

        foreach = None
        if "foreach" in item and isinstance(item["foreach"], dict):
            foreach_raw = item["foreach"]
            foreach = ForeachSpec(
                in_expr=foreach_raw.get("in"),
                as_name=foreach_raw.get("as") or "",
                steps=_build_steps(foreach_raw.get("steps"), source_path),
            )
        steps.append(
            StepSpec(
                step=item.get("step"),
                when=item.get("when"),
                continue_on_error=bool(item.get("continue_on_error", False)),
                use=item.get("use"),
                with_values=item.get("with") if isinstance(item.get("with"), dict) else {},
                foreach=foreach,
            )
        )
    return steps
