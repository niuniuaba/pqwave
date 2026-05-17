import os
import pytest
from pqwave.templates.manager import TemplateManager


@pytest.fixture
def templates_dir(tmp_path):
    d = str(tmp_path / "templates")
    os.makedirs(d, exist_ok=True)
    yield d


def test_save_and_load_template(templates_dir):
    mgr = TemplateManager(templates_dir)
    config = {
        "axis_configs": {
            "X": {"label": "frequency", "log_mode": True, "range": [1, 100000]},
            "Y1": {"label": "Gain (dB)", "log_mode": False, "range": [-40, 20]},
        },
        "trace_expressions": [
            {"expr": "v(out)_db", "axis": "Y1", "color": "#ff0000"},
        ],
        "display": {"grid": True, "title": "Bode Plot"},
    }
    mgr.save("bode-template", config)
    loaded = mgr.load("bode-template")
    assert loaded == config


def test_list_templates(templates_dir):
    mgr = TemplateManager(templates_dir)
    mgr.save("a", {})
    mgr.save("b", {})
    names = mgr.list()
    assert "a" in names
    assert "b" in names


def test_delete_template(templates_dir):
    mgr = TemplateManager(templates_dir)
    mgr.save("x", {})
    mgr.delete("x")
    assert "x" not in mgr.list()


def test_load_missing_raises(templates_dir):
    mgr = TemplateManager(templates_dir)
    with pytest.raises(FileNotFoundError):
        mgr.load("nonexistent")
