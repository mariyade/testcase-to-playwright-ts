from __future__ import annotations

from pathlib import Path

from agent.models import RepoContext


def tool_schemas() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "list_page_objects",
                "description": "List available TypeScript page objects and their methods.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_fixtures",
                "description": "List available Playwright fixtures.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a file under the Playwright project root.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        },
    ]


class ToolDispatcher:
    def __init__(self, context: RepoContext):
        self.context = context

    def dispatch(self, name: str, args: dict) -> str:
        if name == "list_page_objects":
            return self.context.page_api_summary()
        if name == "get_fixtures":
            return "\n".join(f"{f.name}: {f.source_file}" for f in self.context.fixtures)
        if name == "read_file":
            return self._read_file(args["path"])
        return f"Unknown tool: {name}"

    def _read_file(self, relative_path: str) -> str:
        root = self.context.playwright_root.resolve()
        target = (root / relative_path).resolve()
        if root not in target.parents and target != root:
            return "Refused: path is outside Playwright root"
        if not target.exists() or not target.is_file():
            return f"File not found: {relative_path}"
        return target.read_text(encoding="utf-8")[:12000]

