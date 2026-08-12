from __future__ import annotations

import re
from pathlib import Path

from agent.models import (
    AssertionContract,
    FixtureInfo,
    PageObjectInfo,
    PageObjectMethodInfo,
    ParameterContract,
)

CLASS_RE = re.compile(r"export\s+class\s+([A-Z][A-Za-z0-9_]*)")
PROPERTY_RE = re.compile(r"\breadonly\s+([a-zA-Z_][A-Za-z0-9_]*)\s*:")
FIXTURE_RE = re.compile(r"\b([a-zA-Z_][A-Za-z0-9_]*)\s*:\s*async\s*\(")
METHOD_BLOCK_RE = re.compile(
    r"(?P<prefix>(?:(?P<access>public|private|protected)\s+)?(?:async\s+)?(?P<name>[a-zA-Z_][A-Za-z0-9_]*)\s*\((?P<params>[^)]*)\)\s*(?::\s*(?P<returns>[^{]+?))?\s*)\{"
)
CONTRACT_ANNOTATION_RE = re.compile(r"/\*\*[\s\S]*?@contract[\s\S]*?\*/\s*$")
INTERFACE_RE = re.compile(
    r"export\s+interface\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?:\s+extends\s+(?P<extends>[A-Za-z_][A-Za-z0-9_]*))?\s*\{(?P<body>[^}]*)\}",
    re.DOTALL,
)
TYPE_ALIAS_OBJECT_RE = re.compile(
    r"export\s+type\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*\{(?P<body>[^}]*)\}",
    re.DOTALL,
)
INTERFACE_FIELD_RE = re.compile(r"\b(?P<name>[A-Za-z_][A-Za-z0-9_]*)\??\s*:\s*(?P<type>[^;\n]+)")


# Convert one page-object TypeScript file into structured repository contracts.
# The planner/generator use this instead of asking the LLM to infer methods from raw code.
def read_page_objects(path: Path, type_shapes: dict[str, dict[str, str]]) -> list[PageObjectInfo]:
    source = path.read_text(encoding="utf-8")
    classes = CLASS_RE.findall(source)
    if not classes:
        return []

    properties = [
        name
        for name in PROPERTY_RE.findall(source)
        if name not in {"return", "const", "let", "var", "await"}
    ]

    return [
        PageObjectInfo(
            name=class_name,
            filepath=path,
            page=_page_name(class_name),
            fixture=_fixture_name(class_name),
            methods=_read_page_object_methods(source, class_name, type_shapes),
            properties=sorted(set(properties)),
        )
        for class_name in classes
    ]


# Extract public callable methods from a page-object class.
# If @contract annotations exist, only annotated methods are exposed to generation.
def _read_page_object_methods(
    source: str,
    class_name: str,
    type_shapes: dict[str, dict[str, str]],
) -> list[PageObjectMethodInfo]:
    methods: dict[str, PageObjectMethodInfo] = {}
    matches = [
        match
        for match in METHOD_BLOCK_RE.finditer(source)
        if match.group("name") not in {"if", "for", "while", "switch", "catch", "constructor"}
        and match.group("access") != "private"
    ]
    has_contract_annotations = any(
        _has_contract_annotation(source, match.start()) for match in matches
    )
    for match in matches:
        name = match.group("name")
        if has_contract_annotations and not _has_contract_annotation(source, match.start()):
            continue
        body = _balanced_block(source, match.end() - 1)
        methods[name] = PageObjectMethodInfo(
            name=name,
            intent=_method_intent(name),
            signature=" ".join(match.group("prefix").strip().split()),
            returns=_method_return_type(match.group("returns"), match.group("prefix")),
            parameters=_method_parameters(match.group("params"), type_shapes),
            navigates_to=_navigation_target(body),
        )

    for method in methods.values():
        if not method.navigates_to:
            method.stays_on = class_name

    return [methods[name] for name in sorted(methods)]


# Look just before a method declaration for an @contract docblock.
# This mirrors the chunker and keeps unannotated helper methods private to the agent.
def _has_contract_annotation(source: str, method_start: int) -> bool:
    prefix = source[max(0, method_start - 400) : method_start]
    return bool(CONTRACT_ANNOTATION_RE.search(prefix))


# Convert method names into simple intent labels used by the planner.
# For example, updateSearch becomes submit_search and openX becomes x.
def _method_intent(method_name: str) -> str:
    words = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", method_name).lower()
    if method_name == "goto":
        return "open_page"
    if words in {"search", "update_search"}:
        return "submit_search"
    if words.startswith("open_"):
        return words.removeprefix("open_")
    if words.startswith("expect_"):
        return words
    return words


# Return the declared TypeScript return type when present.
# Otherwise async methods are treated as Promise<void>, and sync methods as void.
def _method_return_type(returns_source: str | None, prefix: str) -> str:
    explicit_return = " ".join((returns_source or "").strip().split())
    if explicit_return:
        return explicit_return
    if re.search(r"\basync\b", prefix):
        return "Promise<void>"
    return "void"


# Parse method parameters into names, required/optional flags, and known object fields.
# These contracts let Stage 3 know the shape of valid method calls.
def _method_parameters(
    params_source: str,
    type_shapes: dict[str, dict[str, str]],
) -> list[ParameterContract]:
    parameters: list[ParameterContract] = []
    for raw_param in _split_parameters(params_source):
        match = re.match(
            r"\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?P<optional>\?)?\s*:\s*(?P<type>.+?)\s*$",
            raw_param,
        )
        if not match:
            continue
        param_type = match.group("type").strip()
        parameters.append(
            ParameterContract(
                name=match.group("name"),
                type=param_type,
                required=not bool(match.group("optional")),
                properties=type_shapes.get(param_type, {}),
            )
        )
    return parameters


# Split a parameter list on top-level commas only.
# This avoids breaking object types, generics, and function signatures.
def _split_parameters(params_source: str) -> list[str]:
    params: list[str] = []
    current: list[str] = []
    depth = 0
    for char in params_source:
        if char in "({[<":
            depth += 1
        elif char in ")}]>":
            depth = max(0, depth - 1)
        if char == "," and depth == 0:
            param = "".join(current).strip()
            if param:
                params.append(param)
            current = []
            continue
        current.append(char)
    param = "".join(current).strip()
    if param:
        params.append(param)
    return params


# Read exported interfaces/type aliases from page files so parameter objects have fields.
# For example, LoginUserData can expose required email/password properties.
def read_type_shapes(root: Path) -> dict[str, dict[str, str]]:
    if not root.exists():
        return {}

    raw_interfaces: dict[str, tuple[str | None, dict[str, str]]] = {}
    for path in sorted(root.rglob("*.ts")):
        source = path.read_text(encoding="utf-8")
        for match in INTERFACE_RE.finditer(source):
            fields = {
                field_match.group("name"): " ".join(field_match.group("type").strip().split())
                for field_match in INTERFACE_FIELD_RE.finditer(match.group("body"))
            }
            raw_interfaces[match.group("name")] = (match.group("extends"), fields)
        for match in TYPE_ALIAS_OBJECT_RE.finditer(source):
            fields = {
                field_match.group("name"): " ".join(field_match.group("type").strip().split())
                for field_match in INTERFACE_FIELD_RE.finditer(match.group("body"))
            }
            raw_interfaces[match.group("name")] = (None, fields)

    resolved: dict[str, dict[str, str]] = {}

    # Resolve inherited interface fields into one flat object shape.
    def resolve(name: str, seen: set[str] | None = None) -> dict[str, str]:
        if name in resolved:
            return resolved[name]
        if name not in raw_interfaces:
            return {}
        seen = seen or set()
        if name in seen:
            return {}
        parent, fields = raw_interfaces[name]
        shape = dict(resolve(parent, seen | {name})) if parent else {}
        shape.update(fields)
        resolved[name] = shape
        return shape

    for name in raw_interfaces:
        resolve(name)
    return resolved


# Infer where a page-object method navigates by reading common URL assertions/calls.
# The planner uses this to connect actions like registration clicks to destination pages.
def _navigation_target(method_body: str) -> str:
    if ".click(" not in method_body and ".goto(" not in method_body:
        return ""

    route_matches = [
        *re.findall(r"waitForURL\(\s*/\\/(?:\\)?([a-z0-9-]+)", method_body),
        *re.findall(r"toHaveURL\(\s*/\\/(?:\\)?([a-z0-9-]+)", method_body),
        *re.findall(r"goto\(\s*['\"]/(.*?)['\"]", method_body),
    ]
    for route in route_matches:
        route = route.strip().strip("/")
        if route:
            return _page_object_name(route)
    return ""


# Convert a class name such as HomePage into the affected_pages style home_page.
def _page_name(class_name: str) -> str:
    name = class_name.removesuffix("Page")
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower() + "_page"


# Convert a page-object class name into the fixture name generated by fixtures/test.ts.
def _fixture_name(class_name: str) -> str:
    return class_name[:1].lower() + class_name[1:]


# Convert a URL route into the page-object name the repo would normally use.
# The root route maps to HomePage for the Restful Booker demo.
def _page_object_name(route: str) -> str:
    if route in {"", "/"}:
        return "HomePage"
    return "".join(part.capitalize() for part in re.split(r"[^a-zA-Z0-9]+", route) if part) + "Page"


# Return a complete method body by balancing braces from the opening brace.
# This gives navigation detection enough source to inspect.
def _balanced_block(source: str, open_brace: int) -> str:
    depth = 0
    for index in range(open_brace, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[open_brace : index + 1]
    return source[open_brace:]


# Extract fixture names available to generated Playwright tests.
# The built-in page fixture is added when the file extends Playwright test.
def read_fixtures(path: Path) -> list[FixtureInfo]:
    source = path.read_text(encoding="utf-8")
    names = set(FIXTURE_RE.findall(source))
    if "test.extend" in source:
        names.add("page")
    return [FixtureInfo(name=name, source_file=path) for name in sorted(names)]


# Collect page-object methods whose names start with expect.
# Stage 3 uses this as the repository's known assertion-helper catalog.
def assertion_contracts(page_objects: list[PageObjectInfo]) -> list[AssertionContract]:
    assertions: list[AssertionContract] = []
    for page_object in page_objects:
        for method in page_object.methods:
            if not method.name.startswith("expect"):
                continue
            assertions.append(
                AssertionContract(
                    name=method.name,
                    page_object=page_object.name,
                    fixture=page_object.fixture,
                    source_file=page_object.filepath,
                )
            )
    return assertions
