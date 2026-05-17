import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from pqwave.session.api import SessionAPI
from pqwave.models.state import ApplicationState


@pytest.fixture
def session():
    ApplicationState._instance = None
    return SessionAPI()


def test_save_and_load_template_commands(session, monkeypatch, tmp_path):
    tmpl_dir = str(tmp_path / "templates")
    monkeypatch.setattr("pqwave.session.api.get_template_dir", lambda: tmpl_dir)

    session.save_template("my-tmpl")
    result = session.list_templates()
    assert "my-tmpl" in result.get("templates", [])

    result = session.load_template("my-tmpl")
    assert result["success"] is True
