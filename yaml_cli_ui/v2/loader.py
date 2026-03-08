"""YAML loading and import-resolution for YAML CLI UI v2."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

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
from .validator import validate_v2_document


def load_yaml_file(path: str | Path) -> dict[str, Any]:
    """Load a YAML file and return mapping root object."""

    yaml_path = Path(path).expanduser().resolve()
    try:
        with yaml_path.open("r", encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh)
    except FileNotFoundError as exc:
        raise V2LoadError(f"v2 document file not found: {yaml_path}") from exc
    except OSError as exc:
        raise V2LoadError(f"failed to read v2 document file: {yaml_path}") from exc
    except yaml.YAMLError as exc:
        raise V2LoadError(f"failed to parse YAML document: {yaml_path}") from exc

    if loaded is None:
        loaded = {}
    if not isinstance(loaded, dict):
        raise V2LoadError(f"v2 document root must be a mapping: {yaml_path}")
    return loaded


def _expect_mapping(value: Any, *, field: str, path: Path) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise V2LoadError(f"field '{field}' must be a mapping in {path}")
    return value


def _build_on_error(raw: Any, *, path: Path, owner: str) -> OnErrorSpec | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise V2LoadError(f"field '{owner}.on_error' must be a mapping in {path}")
    steps = raw.get("steps", [])
    if not isinstance(steps, list):
        raise V2LoadError(f"field '{owner}.on_error.steps' must be a list in {path}")
    return OnErrorSpec(steps=[_build_step(item, path=path, owner=f"{owner}.on_error") for item in steps])


def _build_foreach(raw: Any, *, path: Path, owner: str) -> ForeachSpec:
    if not isinstance(raw, dict):
        raise V2LoadError(f"field '{owner}.foreach' must be a mapping in {path}")
    steps = raw.get("steps", [])
    if not isinstance(steps, list):
        raise V2LoadError(f"field '{owner}.foreach.steps' must be a list in {path}")
    return ForeachSpec(
        in_expr=raw.get("in"),
        as_name=raw.get("as") if isinstance(raw.get("as"), str) else "",
        steps=[_build_step(item, path=path, owner=f"{owner}.foreach") for item in steps],
    )


def _build_step(raw: Any, *, path: Path, owner: str) -> StepSpec | str:
    if isinstance(raw, str):
        return raw
    if not isinstance(raw, dict):
        raise V2LoadError(f"step in '{owner}' must be string or mapping in {path}")

    foreach_raw = raw.get("foreach")
    foreach = _build_foreach(foreach_raw, path=path, owner=owner) if foreach_raw is not None else None

    with_values = raw.get("with", {})
    if with_values is None:
        with_values = {}
    if not isinstance(with_values, dict):
        raise V2LoadError(f"field '{owner}.with' must be a mapping in {path}")

    try:
        return StepSpec(
            step=raw.get("step") if isinstance(raw.get("step"), str) else None,
            when=raw.get("when"),
            continue_on_error=bool(raw.get("continue_on_error", False)),
            use=raw.get("use") if isinstance(raw.get("use"), str) else None,
            with_values=with_values,
            foreach=foreach,
        )
    except ValueError as exc:
        raise V2LoadError(f"invalid step in '{owner}' at {path}: {exc}") from exc


def _build_document(raw_doc: dict[str, Any], *, source_path: Path) -> V2Document:
    version = raw_doc.get("version", 0)
    if not isinstance(version, int):
        raise V2LoadError(f"field 'version' must be an integer in {source_path}")

    imports = _expect_mapping(raw_doc.get("imports"), field="imports", path=source_path)

    profiles_raw = _expect_mapping(raw_doc.get("profiles"), field="profiles", path=source_path)
    profiles = {
        name: ProfileDef(
            workdir=entry.get("workdir") if isinstance(entry, dict) else None,
            env=entry.get("env", {}) if isinstance(entry, dict) and isinstance(entry.get("env", {}), dict) else {},
            runtimes=entry.get("runtimes", {}) if isinstance(entry, dict) and isinstance(entry.get("runtimes", {}), dict) else {},
        )
        for name, entry in profiles_raw.items()
        if isinstance(name, str) and isinstance(entry, dict)
    }

    params_raw = _expect_mapping(raw_doc.get("params"), field="params", path=source_path)
    params: dict[str, ParamDef] = {}
    for name, entry in params_raw.items():
        if not isinstance(name, str) or not isinstance(entry, dict):
            continue
        type_value = entry.get("type", "string")
        if not isinstance(type_value, str):
            raise V2LoadError(f"param '{name}' field 'type' must be string in {source_path}")
        try:
            param_type = ParamType(type_value)
        except ValueError as exc:
            raise V2LoadError(f"param '{name}' has unsupported type '{type_value}' in {source_path}") from exc

        source_raw = entry.get("source")
        secret_source = None
        if isinstance(source_raw, str):
            try:
                secret_source = SecretSource(source_raw)
            except ValueError:
                secret_source = None

        params[name] = ParamDef(
            type=param_type,
            title=entry.get("title") if isinstance(entry.get("title"), str) else None,
            required=bool(entry.get("required", False)),
            default=entry.get("default"),
            options=entry.get("options") if isinstance(entry.get("options"), list) else None,
            min=entry.get("min"),
            max=entry.get("max"),
            step=entry.get("step"),
            must_exist=entry.get("must_exist") if isinstance(entry.get("must_exist"), bool) else None,
            source=secret_source,
            env=entry.get("env") if isinstance(entry.get("env"), str) else None,
            key=entry.get("key") if isinstance(entry.get("key"), str) else None,
            item_schema=None,
        )

    locals_raw = _expect_mapping(raw_doc.get("locals"), field="locals", path=source_path)

    commands_raw = _expect_mapping(raw_doc.get("commands"), field="commands", path=source_path)
    commands: dict[str, CommandDef] = {}
    for name, entry in commands_raw.items():
        if not isinstance(name, str) or not isinstance(entry, dict):
            continue
        run_raw = entry.get("run", {})
        if not isinstance(run_raw, dict):
            raise V2LoadError(f"field 'commands.{name}.run' must be a mapping in {source_path}")
        argv = run_raw.get("argv", [])
        if not isinstance(argv, list):
            raise V2LoadError(f"field 'commands.{name}.run.argv' must be a list in {source_path}")
        try:
            run = RunSpec(
                program=run_raw.get("program") if isinstance(run_raw.get("program"), str) else "",
                argv=argv,
                workdir=run_raw.get("workdir"),
                env=run_raw.get("env", {}) if isinstance(run_raw.get("env", {}), dict) else {},
                timeout_ms=run_raw.get("timeout_ms") if isinstance(run_raw.get("timeout_ms"), int) else None,
                stdout=run_raw.get("stdout") if isinstance(run_raw.get("stdout"), str) else None,
                stderr=run_raw.get("stderr") if isinstance(run_raw.get("stderr"), str) else None,
            )
            commands[name] = CommandDef(
                title=entry.get("title") if isinstance(entry.get("title"), str) else None,
                info=entry.get("info") if isinstance(entry.get("info"), str) else None,
                when=entry.get("when"),
                continue_on_error=bool(entry.get("continue_on_error", False)),
                run=run,
                on_error=_build_on_error(entry.get("on_error"), path=source_path, owner=f"commands.{name}"),
            )
        except ValueError as exc:
            raise V2LoadError(f"invalid command 'commands.{name}' in {source_path}: {exc}") from exc

    pipelines_raw = _expect_mapping(raw_doc.get("pipelines"), field="pipelines", path=source_path)
    pipelines: dict[str, PipelineDef] = {}
    for name, entry in pipelines_raw.items():
        if not isinstance(name, str) or not isinstance(entry, dict):
            continue
        steps_raw = entry.get("steps", [])
        if not isinstance(steps_raw, list):
            raise V2LoadError(f"field 'pipelines.{name}.steps' must be a list in {source_path}")
        try:
            pipelines[name] = PipelineDef(
                title=entry.get("title") if isinstance(entry.get("title"), str) else None,
                info=entry.get("info") if isinstance(entry.get("info"), str) else None,
                when=entry.get("when"),
                continue_on_error=bool(entry.get("continue_on_error", False)),
                steps=[_build_step(item, path=source_path, owner=f"pipelines.{name}") for item in steps_raw],
                on_error=_build_on_error(entry.get("on_error"), path=source_path, owner=f"pipelines.{name}"),
            )
        except ValueError as exc:
            raise V2LoadError(f"invalid pipeline 'pipelines.{name}' in {source_path}: {exc}") from exc

    launchers_raw = _expect_mapping(raw_doc.get("launchers"), field="launchers", path=source_path)
    launchers: dict[str, LauncherDef] = {}
    for name, entry in launchers_raw.items():
        if not isinstance(name, str) or not isinstance(entry, dict):
            continue
        with_values = entry.get("with", {})
        if with_values is None:
            with_values = {}
        if not isinstance(with_values, dict):
            raise V2LoadError(f"field 'launchers.{name}.with' must be a mapping in {source_path}")
        try:
            launchers[name] = LauncherDef(
                title=entry.get("title") if isinstance(entry.get("title"), str) else "",
                use=entry.get("use") if isinstance(entry.get("use"), str) else "",
                info=entry.get("info") if isinstance(entry.get("info"), str) else None,
                with_values=with_values,
            )
        except ValueError as exc:
            raise V2LoadError(f"invalid launcher 'launchers.{name}' in {source_path}: {exc}") from exc

    import_defs: dict[str, ImportDef] = {}
    for alias, import_path in imports.items():
        if not isinstance(alias, str) or not alias.strip():
            raise V2LoadError(f"import alias must be a non-empty string in {source_path}")
        if not isinstance(import_path, str):
            raise V2LoadError(f"import path for alias '{alias}' must be a string in {source_path}")
        import_defs[alias] = ImportDef(alias=alias, path=import_path)

    return V2Document(
        version=version,
        imports=import_defs,
        profiles=profiles,
        params=params,
        locals=locals_raw,
        commands=commands,
        pipelines=pipelines,
        launchers=launchers,
        source_path=source_path,
        base_dir=source_path.parent,
        raw=raw_doc,
    )


def resolve_imports(path: str | Path, *, _stack: tuple[Path, ...] = ()) -> V2Document:
    """Recursively load document and resolve imports graph."""

    source_path = Path(path).expanduser().resolve()
    if source_path in _stack:
        chain = " -> ".join(str(item) for item in (*_stack, source_path))
        raise V2LoadError(f"detected v2 import cycle: {chain}")

    raw_doc = load_yaml_file(source_path)
    document = _build_document(raw_doc, source_path=source_path)

    loaded_imports: dict[str, V2Document] = {}
    for alias, import_def in document.imports.items():
        target_path = (source_path.parent / import_def.path).resolve()
        if not target_path.exists():
            raise V2LoadError(
                f"import '{alias}' points to missing file '{target_path}' from {source_path}"
            )
        import_def.resolved_path = target_path
        loaded_imports[alias] = resolve_imports(target_path, _stack=(*_stack, source_path))

    document.imported_documents = loaded_imports
    return document


def load_v2_document(path: str | Path) -> V2Document:
    """Load, resolve imports and validate root v2 document."""

    doc = resolve_imports(path)
    validate_v2_document(doc)
    return doc
