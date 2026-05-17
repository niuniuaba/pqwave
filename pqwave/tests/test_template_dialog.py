import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
import pytest


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_template_manager_dialog_creation(qapp):
    from pqwave.ui.template_manager_dialog import TemplateManagerDialog

    dlg = TemplateManagerDialog(parent=None)
    assert dlg is not None
    assert dlg.windowTitle() == "Template Manager"
    dlg.close()
