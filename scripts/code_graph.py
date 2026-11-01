"""Generate/check the code graph (modules, symbols, routes, web assets, engine processes) from source.

Static and deterministic: Python is parsed with ``ast`` and the web UI is scanned for literal ``api/`` paths,
including relative paths joined to a bare ``/api/<area>`` base in the same script.
Dynamic dispatch, computed URLs and runtime-only behaviour are not represented.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

PACKAGE = "naturalvoice"
OUTPUT = Path("library/knowledge/private/codebase-graph/meta")
ENGINE_SCRIPTS = (
    "engines/chatterbox/worker.py",
    "engines/media/worker.py",
    "engines/media/download.py",
)
HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete"})
_PARAM = re.compile(r"\{[^}]*\}")
_TEMPLATE = re.compile(r"\$\{[^{}]*\}")
_API_LITERAL = re.compile(r"""['"`](/?api/[^'"`?#\s]*)""")
# A bare area prefix such as '/api/studio', joined at run time to relative paths like json('/projects').
_API_BASE = re.compile(r"""['"`](/?api/[a-z]+)['"`]""")
# `import ... from '#lib/studio/api.ts'`: a page joins its relative paths to the area base its lib module names.
_LIB_IMPORT = re.compile(r"""from\s+['"]#lib/([^'"]+)['"]""")
_RELATIVE = re.compile(r"""['"`](/(?!api/)[A-Za-z0-9_${}./-]*)""")


@dataclass
class Graph:
    nodes: dict[str, dict[str, str | int]] = field(default_factory=dict)
    edges: set[tuple[str, str, str]] = field(default_factory=set)

    def node(self, ident: str, kind: str, file: str, line: int = 1) -> str:
        self.nodes.setdefault(ident, {"id": ident, "kind": kind, "file": file, "line": line})
        return ident

    def edge(self, source: str, target: str, kind: str) -> None:
        self.edges.add((source, target, kind))


def module_name(path: Path, root: Path) -> str:
    relative = path.relative_to(root).with_suffix("")
    parts = relative.parts[1:] if relative.parts[0] == "src" else relative.parts
    return ".".join(parts).removesuffix(".__init__")


def route_key(path: str) -> str:
    """Normalize ``/api/x/{id}`` and ``api/x/${id}`` to the same comparable key."""
    return _PARAM.sub("{}", _TEMPLATE.sub("{}", "/" + path.lstrip("/"))).rstrip("/") or "/"


def string_constants(tree: ast.AST) -> set[str]:
    return {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def internal_imports(tree: ast.Module, module: str, known: set[str]) -> dict[str, str]:
    """Map local alias to imported internal module (only ``naturalvoice`` modules)."""
    package = module.rsplit(".", 1)[0] if "." in module else module
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                base = f"{package}.{base}".rstrip(".") if base else package
            for name in node.names:
                full = f"{base}.{name.name}"
                if full in known:
                    aliases[name.asname or name.name] = full
                elif base in known:
                    aliases[name.asname or name.name] = base
        elif isinstance(node, ast.Import):
            for name in node.names:
                if name.name in known:
                    aliases[name.asname or name.name.rsplit(".", 1)[-1]] = name.name
    return aliases


def router_prefix(tree: ast.Module) -> str:
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            func = node.value.func
            if isinstance(func, ast.Name) and func.id == "APIRouter":
                for keyword in node.value.keywords:
                    if keyword.arg == "prefix" and isinstance(keyword.value, ast.Constant):
                        return str(keyword.value.value)
    return ""


def add_python(graph: Graph, root: Path, files: list[Path]) -> dict[str, set[str]]:
    """Add Python modules, symbols, imports, calls, routes and engine spawns. Returns route key -> nodes."""
    parsed = {module_name(p, root): (p, ast.parse(p.read_text(), filename=str(p))) for p in files}
    known = set(parsed)
    routes: dict[str, set[str]] = {}
    for module, (path, tree) in sorted(parsed.items()):
        rel = path.relative_to(root).as_posix()
        mod_id = graph.node(f"module:{module}", "module", rel)
        aliases = internal_imports(tree, module, known)
        for target in sorted(set(aliases.values())):
            if target != module:
                graph.edge(mod_id, f"module:{target}", "imports")
        prefix = router_prefix(tree)
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                continue
            kind = "class" if isinstance(node, ast.ClassDef) else "function"
            sym = graph.node(f"symbol:{module}.{node.name}", kind, rel, node.lineno)
            graph.edge(mod_id, sym, "defines")
            for deco in node.decorator_list:
                call = deco if isinstance(deco, ast.Call) else None
                func = call.func if call else None
                if (
                    call
                    and isinstance(func, ast.Attribute)
                    and func.attr in HTTP_METHODS
                    and call.args
                    and isinstance(call.args[0], ast.Constant)
                ):
                    path_text = prefix + str(call.args[0].value)
                    route = graph.node(f"route:{func.attr.upper()} {path_text}", "route", rel, node.lineno)
                    graph.edge(sym, route, "serves")
                    routes.setdefault(route_key(path_text), set()).add(route)
            for inner in ast.walk(node):
                if (
                    isinstance(inner, ast.Call)
                    and isinstance(inner.func, ast.Attribute)
                    and isinstance(inner.func.value, ast.Name)
                    and inner.func.value.id in aliases
                ):
                    target_module = aliases[inner.func.value.id]
                    if target_module in known:
                        graph.edge(sym, f"symbol:{target_module}.{inner.func.attr}", "calls")
        constants = string_constants(tree)
        if "engines" in constants:
            for script in ENGINE_SCRIPTS:
                engine, name = script.split("/")[1:]
                if engine in constants and name in constants:
                    graph.edge(mod_id, f"process:{script}", "spawns")
    # Drop call edges to names that are not top-level symbols (attributes, constants, re-exports).
    graph.edges = {e for e in graph.edges if e[2] != "calls" or e[1] in graph.nodes}
    return routes


def add_engines(graph: Graph, root: Path) -> None:
    for script in ENGINE_SCRIPTS:
        path = root / script
        if path.exists():
            graph.node(f"process:{script}", "process", script)


def _web_sources(root: Path) -> list[tuple[Path, str]]:
    """(file, kind): SvelteKit route components are pages, lib modules are scripts, plus the service worker."""
    front = root / "frontend" / "src"
    found = [(p, "page") for p in sorted((front / "routes").rglob("*.svelte"))]
    found += [(p, "script") for p in sorted((front / "routes").rglob("*.ts"))]
    found += [(p, "script") for p in sorted((front / "lib").rglob("*.ts"))]
    found += [(p, "script") for p in sorted((root / "src" / PACKAGE / "web").glob("*.js"))]
    return found


def add_web(graph: Graph, root: Path, routes: dict[str, set[str]]) -> None:
    lib = root / "frontend" / "src" / "lib"
    for path, kind in _web_sources(root):
        rel = path.relative_to(root).as_posix()
        # Collapse template substitutions first so quotes inside `${...}` cannot end a literal early.
        text = _TEMPLATE.sub("{}", path.read_text())
        ident = graph.node(f"web:{rel.removeprefix('frontend/src/')}", kind, rel)
        candidates = set(_API_LITERAL.findall(text))
        bases = set(_API_BASE.findall(text))
        for module in sorted(set(_LIB_IMPORT.findall(text))):
            if (lib / module).is_file():
                bases |= set(_API_BASE.findall((lib / module).read_text()))
        for base in bases:
            candidates |= {base + relative for relative in _RELATIVE.findall(text)}
        for literal in sorted(candidates):
            key = route_key(literal)
            # Literals that end where a template appends a variable (e.g. `api/x/${id}`) are prefixes.
            # Matching is by path only: every HTTP method served at that path gets the edge.
            for match in routes.get(key) or routes.get(key + "/{}") or set():
                graph.edge(ident, match, "requests")


def build(root: Path) -> Graph:
    graph = Graph()
    files = sorted((root / "src" / PACKAGE).glob("*.py")) + [root / s for s in ENGINE_SCRIPTS if (root / s).exists()]
    add_engines(graph, root)
    routes = add_python(graph, root, files)
    # Engine scripts are both parsed modules and spawned processes; link the two views.
    for script in ENGINE_SCRIPTS:
        module = f"module:{script.removesuffix('.py').replace('/', '.')}"
        if module in graph.nodes:
            graph.edge(f"process:{script}", module, "runs")
    add_web(graph, root, routes)
    return graph


def render_json(graph: Graph) -> str:
    data = {
        "generator": "scripts/code_graph.py",
        "note": "Static source graph. Regenerate with: uv run python scripts/code_graph.py --write",
        "nodes": [graph.nodes[k] for k in sorted(graph.nodes)],
        "edges": [{"source": s, "target": t, "kind": k} for s, t, k in sorted(graph.edges)],
    }
    return json.dumps(data, indent=1, sort_keys=True) + "\n"


def render_markdown(graph: Graph) -> str:
    counts: dict[str, int] = {}
    for node in graph.nodes.values():
        counts[str(node["kind"])] = counts.get(str(node["kind"]), 0) + 1
    edge_counts: dict[str, int] = {}
    for _, _, kind in graph.edges:
        edge_counts[kind] = edge_counts.get(kind, 0) + 1

    def short(ident: str) -> str:
        return re.sub(r"\W", "_", ident.split(":", 1)[1].removeprefix(f"{PACKAGE}."))

    lines = [
        "---",
        "title: Code graph overview",
        "generator: scripts/code_graph.py",
        "---",
        "",
        "# Code graph overview",
        "",
        "Generated by `scripts/code_graph.py` from source; do not edit by hand. Full node and edge list:",
        "[code-graph.json](code-graph.json). Regenerate with `uv run python scripts/code_graph.py --write`;",
        "run it without `--write` to check that the files are current.",
        "",
        "This is a static view: Python is parsed with `ast`, and web scripts are scanned for literal `api/`",
        "paths (including relative paths joined to a bare `/api/<area>` base). Computed URLs, dynamic",
        "dispatch and runtime behaviour are not shown, so a route with no `requests` edge may still be used.",
        "`requests` edges match by path, not HTTP method: a script that calls a path links to every method",
        "served there.",
        "",
        "| Nodes | Count |",
        "|---|---|",
        *[f"| {k} | {v} |" for k, v in sorted(counts.items())],
        "",
        "| Edges | Count |",
        "|---|---|",
        *[f"| {k} | {v} |" for k, v in sorted(edge_counts.items())],
        "",
        "## Modules, engine processes and web assets",
        "",
        "Module imports, process spawns and page script loads. Symbol, route and call edges are in the JSON.",
        "",
        "```mermaid",
        "flowchart LR",
    ]
    shown = {"imports": "-->", "spawns": "==>|spawns|", "runs": "-.->", "loads": "-->"}
    for source, target, kind in sorted(graph.edges):
        if kind in shown:
            lines.append(f"  {short(source)} {shown[kind]} {short(target)}")
    lines += ["```", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Regenerate the checked-in code graph")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    graph = build(root)
    expected = {
        root / OUTPUT / "code-graph.json": render_json(graph),
        root / OUTPUT / "code-graph.md": render_markdown(graph),
    }
    if args.write:
        for target, text in expected.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
        print(f"Wrote code graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges.")
    elif any(not t.exists() or t.read_text() != text for t, text in expected.items()):
        raise SystemExit("Code graph is stale. Run uv run python scripts/code_graph.py --write")
    else:
        print("Code graph matches the source.")


if __name__ == "__main__":
    main()
