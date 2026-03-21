"""Validate services.yaml stays in sync with __init__.py service registrations."""

from __future__ import annotations

import ast
from pathlib import Path

from ruamel.yaml import YAML

INTEGRATION = Path("custom_components/lumagen")


def _extract_schema_fields(node: ast.expr) -> set[str] | None:
    """Extract field name strings from a vol.Schema({...}) call."""
    if not isinstance(node, ast.Call):
        return None
    if len(node.args) != 1 or not isinstance(node.args[0], ast.Dict):
        return None
    fields: set[str] = set()
    for key in node.args[0].keys:
        # vol.Required("foo") or vol.Optional("foo", ...)
        if (
            isinstance(key, ast.Call)
            and len(key.args) >= 1
            and isinstance(key.args[0], ast.Constant)
            and isinstance(key.args[0].value, str)
        ):
            fields.add(key.args[0].value)
    return fields


def _extract_registered_services(init_path: Path) -> dict[str, set[str]]:
    """Parse __init__.py AST to find service schemas and their field names."""
    tree = ast.parse(init_path.read_text())

    schemas: dict[str, set[str]] = {}
    service_constants: dict[str, str] = {}

    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        name = node.targets[0].id

        if (
            name.startswith("SERVICE_")
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            service_constants[name] = node.value.value
            continue

        if not name.endswith("_SCHEMA"):
            continue
        fields = _extract_schema_fields(node.value)
        if fields is not None:
            schemas[name] = fields

    services: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "async_register"
        ):
            continue
        if len(node.args) < 4:
            continue
        service_arg = node.args[1]
        schema_arg = node.args[3]
        if isinstance(service_arg, ast.Name) and service_arg.id in service_constants:
            svc_name = service_constants[service_arg.id]
        elif isinstance(service_arg, ast.Constant) and isinstance(
            service_arg.value, str
        ):
            svc_name = service_arg.value
        else:
            continue
        if isinstance(schema_arg, ast.Name) and schema_arg.id in schemas:
            services[svc_name] = schemas[schema_arg.id]

    return services


def test_service_names_match() -> None:
    """Every registered service must appear in services.yaml and vice versa."""
    registered = _extract_registered_services(INTEGRATION / "__init__.py")
    services_yaml = YAML(typ="safe").load(INTEGRATION / "services.yaml") or {}

    yaml_names = set(services_yaml.keys())
    code_names = set(registered.keys())

    extra_in_yaml = yaml_names - code_names
    extra_in_code = code_names - yaml_names

    errors: list[str] = []
    errors.extend(
        f"services.yaml defines '{n}' but not registered in __init__.py"
        for n in sorted(extra_in_yaml)
    )
    errors.extend(
        f"__init__.py registers '{n}' but missing from services.yaml"
        for n in sorted(extra_in_code)
    )
    assert not errors, "\n".join(errors)


def test_service_fields_match() -> None:
    """Every service's fields in services.yaml must match its schema in code."""
    registered = _extract_registered_services(INTEGRATION / "__init__.py")
    services_yaml = YAML(typ="safe").load(INTEGRATION / "services.yaml") or {}

    common = set(services_yaml.keys()) & set(registered.keys())
    errors: list[str] = []

    for name in sorted(common):
        yaml_fields = set(services_yaml[name].get("fields", {}).keys())
        code_fields = registered[name]
        errors.extend(
            f"services.yaml '{name}' has field '{f}' not in schema"
            for f in sorted(yaml_fields - code_fields)
        )
        errors.extend(
            f"services.yaml '{name}' missing field '{f}' from schema"
            for f in sorted(code_fields - yaml_fields)
        )

    assert not errors, "\n".join(errors)
