#!/usr/bin/env python3
"""Generate API documentation for the sidestage package in Markdown format.

Usage:
    python scripts/generate_api_docs.py

Generates Markdown docs into docs/api/ and writes a source hash
file for staleness detection by tests/meta/test_api_docs.py.
"""

import hashlib
import importlib
import inspect
import pkgutil
import sys
import textwrap
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src" / "sidestage"
OUTPUT_DIR = PROJECT_ROOT / "docs" / "api"
HASH_FILE = OUTPUT_DIR / ".source_hash"

# Ensure src is importable
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def collect_source_files(src_dir: Path) -> list[Path]:
    """Collect all .py files under src/sidestage/, sorted for deterministic hashing."""
    return sorted(
        p for p in src_dir.rglob("*.py")
        if "__pycache__" not in p.parts
    )


def compute_source_hash(files: list[Path]) -> str:
    """Compute a single SHA-256 hash over all source file paths and contents."""
    hasher = hashlib.sha256()
    for filepath in files:
        rel = filepath.relative_to(SRC_DIR)
        hasher.update(str(rel).encode())
        hasher.update(filepath.read_bytes())
    return hasher.hexdigest()


def _is_public(name: str) -> bool:
    return not name.startswith("_")


def _is_from_module(obj: object, module_name: str) -> bool:
    """Check if an object was defined in the given module (not imported)."""
    return getattr(obj, "__module__", None) == module_name


def _format_signature(obj: object) -> str:
    """Get a clean signature string for a callable."""
    try:
        sig = inspect.signature(obj)
        params = []
        for name, param in sig.parameters.items():
            if name == "self":
                continue
            if param.default is inspect.Parameter.empty:
                if param.annotation is inspect.Parameter.empty:
                    params.append(name)
                else:
                    params.append(f"{name}: {_format_annotation(param.annotation)}")
            else:
                default = repr(param.default)
                if len(default) > 40:
                    default = "..."
                if param.annotation is inspect.Parameter.empty:
                    params.append(f"{name}={default}")
                else:
                    params.append(f"{name}: {_format_annotation(param.annotation)} = {default}")
        ret = ""
        if sig.return_annotation is not inspect.Signature.empty:
            ret = f" -> {_format_annotation(sig.return_annotation)}"
        return f"({', '.join(params)}){ret}"
    except (ValueError, TypeError):
        return "(...)"


def _format_annotation(annotation: object) -> str:
    """Format a type annotation to a readable string."""
    import typing
    if annotation is inspect.Parameter.empty:
        return ""
    if isinstance(annotation, str):
        return annotation
    # Handle Optional[X] -> X | None
    origin = getattr(annotation, "__origin__", None)
    args = getattr(annotation, "__args__", ())
    if origin is typing.Union and len(args) == 2 and type(None) in args:
        inner = [a for a in args if a is not type(None)][0]
        return f"{_format_annotation(inner)} | None"
    if origin is typing.Union:
        return " | ".join(_format_annotation(a) for a in args)
    if origin is not None and args:
        origin_name = getattr(origin, "__name__", str(origin))
        inner = ", ".join(_format_annotation(a) for a in args)
        return f"{origin_name}[{inner}]"
    if hasattr(annotation, "__name__"):
        return annotation.__name__  # type: ignore[union-attr]
    return str(annotation).replace("typing.", "").replace("collections.abc.", "")


_GENERIC_INIT_PREFIXES = (
    "Initialize self.",
    "Create a new model by parsing and validating input data",
)


def _get_docstring(obj: object, own_only: bool = False) -> str:
    """Get a cleaned docstring.

    If own_only=True, only return the docstring if it's defined directly
    on the object (not inherited from a parent class).
    """
    if own_only and inspect.isclass(obj):
        doc = obj.__dict__.get("__doc__")
        return inspect.cleandoc(doc) if doc else ""
    doc = inspect.getdoc(obj)
    if not doc:
        return ""
    # Suppress generic __init__ docstrings
    if any(doc.startswith(prefix) for prefix in _GENERIC_INIT_PREFIXES):
        return ""
    return doc


def _is_pydantic_model(cls: type) -> bool:
    try:
        from pydantic import BaseModel
        return issubclass(cls, BaseModel)
    except ImportError:
        return False


def _is_enum(cls: type) -> bool:
    import enum
    return issubclass(cls, enum.Enum)


def _get_enum_values(cls: type) -> list[str]:
    return [f"`{m.name}` = `{m.value!r}`" for m in cls]  # type: ignore[var-type]


def _get_pydantic_fields(cls: type) -> list[tuple[str, str, str]]:
    """Return (name, type_str, default_str) for each pydantic field."""
    fields = []
    for name, field_info in cls.model_fields.items():  # type: ignore[attr-defined]
        ann = field_info.annotation
        type_str = _format_annotation(ann) if ann else "Any"
        if field_info.default is not None and not repr(field_info.default).startswith("PydanticUndefined"):
            default_str = repr(field_info.default)
        elif field_info.default_factory:
            default_str = "*factory*"
        else:
            default_str = ""
        fields.append((name, type_str, default_str))
    return fields


def _get_bases(cls: type) -> str:
    bases = [b.__name__ for b in cls.__bases__ if b.__name__ != "object"]
    return f"({', '.join(bases)})" if bases else ""


def document_module(module_name: str, module: object) -> str:
    """Generate markdown documentation for a single module."""
    lines: list[str] = []
    doc = _get_docstring(module)

    lines.append(f"# `{module_name}`\n")
    if doc:
        lines.append(doc)
        lines.append("")

    # Collect classes and functions defined in this module
    classes = []
    functions = []
    constants = []

    for name, obj in inspect.getmembers(module):
        if not _is_public(name):
            continue
        if not _is_from_module(obj, module_name):
            continue

        if inspect.isclass(obj):
            classes.append((name, obj))
        elif inspect.isfunction(obj):
            functions.append((name, obj))

    # Methods to skip for Pydantic models (inherited boilerplate)
    _PYDANTIC_SKIP = {
        "__init__", "model_extra", "model_fields_set", "model_computed_fields",
        "model_config", "model_fields", "model_post_init",
    }

    # Classes
    if classes:
        lines.append("## Classes\n")
        for name, cls in classes:
            bases = _get_bases(cls)
            lines.append(f"### `{name}{bases}`\n")

            cls_doc = _get_docstring(cls, own_only=True)
            if cls_doc:
                lines.append(cls_doc)
                lines.append("")

            # Enum values
            if _is_enum(cls):
                lines.append("**Values:**\n")
                for val in _get_enum_values(cls):
                    lines.append(f"- {val}")
                lines.append("")
                continue  # Enums don't need method docs

            # Pydantic model fields
            is_pydantic = _is_pydantic_model(cls)
            if is_pydantic:
                fields = _get_pydantic_fields(cls)
                if fields:
                    lines.append("| Field | Type | Default |")
                    lines.append("|-------|------|---------|")
                    for fname, ftype, fdefault in fields:
                        lines.append(f"| `{fname}` | `{ftype}` | {fdefault or '—'} |")
                    lines.append("")

            # Methods
            methods = []
            for mname, mobj in inspect.getmembers(cls):
                if not _is_public(mname) and mname != "__init__":
                    continue
                # Skip inherited Pydantic boilerplate
                if is_pydantic and mname in _PYDANTIC_SKIP:
                    continue
                if mname == "__init__":
                    if isinstance(mobj, type):
                        continue
                    # Only document __init__ if it has own docstring or non-trivial signature
                    sig = _format_signature(mobj)
                    own_doc = _get_docstring(mobj)
                    if sig == "()" and not own_doc:
                        continue
                    methods.insert(0, (mname, mobj))
                elif inspect.isfunction(mobj) or inspect.ismethod(mobj):
                    # Only include methods defined on this class (not inherited)
                    if mname in cls.__dict__:
                        methods.append((mname, mobj))
                elif isinstance(inspect.getattr_static(cls, mname, None), property):
                    # Only include properties defined on this class
                    if mname in cls.__dict__:
                        methods.append((mname, mobj))

            for mname, mobj in methods:
                prop = isinstance(inspect.getattr_static(cls, mname, None), property)
                is_async = inspect.iscoroutinefunction(mobj)

                if prop:
                    fget = inspect.getattr_static(cls, mname).fget
                    try:
                        sig = inspect.signature(fget)
                        ret = ""
                        if sig.return_annotation is not inspect.Signature.empty:
                            ret = f" -> {_format_annotation(sig.return_annotation)}"
                        label = f"`{mname}{ret}` *property*"
                    except (ValueError, TypeError):
                        label = f"`{mname}` *property*"
                else:
                    sig_str = _format_signature(mobj)
                    async_tag = " *async*" if is_async else ""
                    label = f"`{mname}{sig_str}`{async_tag}"

                lines.append(f"#### {label}\n")
                mdoc = _get_docstring(mobj)
                if mdoc:
                    lines.append(mdoc)
                    lines.append("")

    # Module-level functions
    if functions:
        lines.append("## Functions\n")
        for name, func in functions:
            is_async = inspect.iscoroutinefunction(func)
            sig_str = _format_signature(func)
            async_tag = " *async*" if is_async else ""
            lines.append(f"### `{name}{sig_str}`{async_tag}\n")
            fdoc = _get_docstring(func)
            if fdoc:
                lines.append(fdoc)
                lines.append("")

    return "\n".join(lines)


def discover_modules(package_name: str) -> list[str]:
    """Discover all submodules in a package."""
    package = importlib.import_module(package_name)
    modules = [package_name]

    if hasattr(package, "__path__"):
        for importer, modname, ispkg in pkgutil.walk_packages(
            package.__path__, prefix=package_name + "."
        ):
            modules.append(modname)

    return sorted(modules)


def generate_docs() -> None:
    """Generate markdown documentation for all modules."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Clean old generated files (html and md, but not .source_hash)
    for old in OUTPUT_DIR.rglob("*"):
        if old.is_file() and old.name != ".source_hash":
            old.unlink()
    for old in sorted(OUTPUT_DIR.rglob("*"), reverse=True):
        if old.is_dir() and old != OUTPUT_DIR:
            try:
                old.rmdir()
            except OSError:
                pass

    module_names = discover_modules("sidestage")
    generated: list[tuple[str, str]] = []  # (module_name, relative_path)

    for module_name in module_names:
        try:
            module = importlib.import_module(module_name)
        except Exception as e:
            print(f"  Warning: could not import {module_name}: {e}")
            continue

        md = document_module(module_name, module)

        # Only write if there's content beyond just the header
        content_lines = [l for l in md.strip().split("\n") if l.strip()]
        if len(content_lines) <= 1:
            continue

        # Use dot-separated filenames for flat structure
        filename = f"{module_name}.md"
        outpath = OUTPUT_DIR / filename
        outpath.write_text(md)
        generated.append((module_name, filename))

    # Write index
    index_lines = ["# Sidestage API Reference\n"]
    index_lines.append("Auto-generated from source. Run `python scripts/generate_api_docs.py` to regenerate.\n")
    index_lines.append("## Modules\n")
    for module_name, filename in generated:
        index_lines.append(f"- [{module_name}]({filename})")
    index_lines.append("")

    (OUTPUT_DIR / "index.md").write_text("\n".join(index_lines))

    print(f"API docs generated in {OUTPUT_DIR}")
    print(f"  {len(generated)} modules documented")


def write_hash(source_hash: str) -> None:
    """Write the source hash to the hash file."""
    HASH_FILE.write_text(source_hash + "\n")
    print(f"Source hash written to {HASH_FILE}")


def main() -> None:
    files = collect_source_files(SRC_DIR)
    source_hash = compute_source_hash(files)

    generate_docs()
    write_hash(source_hash)

    print(f"Done. {len(files)} source files, hash: {source_hash[:16]}...")


if __name__ == "__main__":
    main()
