import json
import os


class TemplateManager:
    """Persist named view templates as JSON files in a configurable directory."""

    def __init__(self, templates_dir: str):
        self._dir = templates_dir
        os.makedirs(self._dir, exist_ok=True)

    def _path(self, name: str) -> str:
        if not name or "/" in name or "\\" in name or ".." in name:
            raise ValueError(f"Invalid template name: {name!r}")
        return os.path.join(self._dir, f"{name}.json")

    def save(self, name: str, config: dict) -> None:
        with open(self._path(name), "w") as f:
            json.dump(config, f, indent=2)

    def load(self, name: str) -> dict:
        with open(self._path(name), "r") as f:
            return json.load(f)

    def list(self) -> list[str]:
        if not os.path.exists(self._dir):
            return []
        return [
            os.path.splitext(f)[0]
            for f in os.listdir(self._dir)
            if f.endswith(".json")
        ]

    def delete(self, name: str) -> None:
        os.remove(self._path(name))
