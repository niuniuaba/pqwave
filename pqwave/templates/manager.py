import json
import os


class TemplateManager:
    """Manages named view templates persisted as JSON files."""

    def __init__(self, templates_dir: str):
        self._dir = templates_dir
        os.makedirs(self._dir, exist_ok=True)

    def _path(self, name: str) -> str:
        return os.path.join(self._dir, f"{name}.json")

    def save(self, name: str, config: dict) -> None:
        """Save a view template."""
        with open(self._path(name), "w") as f:
            json.dump(config, f, indent=2)

    def load(self, name: str) -> dict:
        """Load a view template."""
        with open(self._path(name), "r") as f:
            return json.load(f)

    def list(self) -> list[str]:
        """List all saved template names."""
        if not os.path.exists(self._dir):
            return []
        return [
            os.path.splitext(f)[0]
            for f in os.listdir(self._dir)
            if f.endswith(".json")
        ]

    def delete(self, name: str) -> None:
        """Delete a view template."""
        os.remove(self._path(name))
