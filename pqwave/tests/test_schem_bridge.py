"""Tests for the abstract schematic bridge layer."""

from pqwave.bridge.schem_bridge import SchematicBridge, NetlistFix


class FakeFix(NetlistFix):
    name = "fake-suffix"

    def __init__(self, suffix: str):
        self.suffix = suffix

    def apply(self, netlist: str, context=None) -> str:
        lines = netlist.split("\n")
        return "\n".join(f"{line}{self.suffix}" for line in lines)

    def info(self, netlist: str) -> list[dict]:
        return [{"fix": self.name, "detail": f"added '{self.suffix}' to {len(netlist.split(chr(10)))} lines"}]


class FakeCountingFix(NetlistFix):
    name = "fake-line-numbers"

    def apply(self, netlist: str, context=None) -> str:
        lines = netlist.split("\n")
        return "\n".join(f"{i}:{line}" for i, line in enumerate(lines, 1))

    def info(self, netlist: str) -> list[dict]:
        count = netlist.count("\n") + 1
        return [{"fix": self.name, "detail": f"numbered {count} lines"}]


class TestSchematicBridgeABC:
    def test_cannot_instantiate_abstract(self):
        import pytest
        with pytest.raises(TypeError):
            SchematicBridge()


class TestNetlistFix:
    def test_apply_appends_suffix(self):
        netlist = "line1\nline2\nline3"
        fix = FakeFix("!")
        result = fix.apply(netlist)
        assert result == "line1!\nline2!\nline3!"

    def test_info_returns_details(self):
        netlist = "line1\nline2\nline3"
        fix = FakeFix("!")
        results = fix.info(netlist)
        assert len(results) == 1
        assert results[0]["fix"] == "fake-suffix"
        assert "3" in results[0]["detail"]


class TestNetlistPostProcessor:
    def test_process_runs_fixes_in_order(self):
        from pqwave.bridge.netlist_postprocessor import NetlistPostProcessor
        netlist = "a\nb\nc"
        processor = NetlistPostProcessor([FakeFix("!"), FakeCountingFix()])
        result = processor.process(netlist)
        assert result == "1:a!\n2:b!\n3:c!"

    def test_dry_run_reports_all_fixes(self):
        from pqwave.bridge.netlist_postprocessor import NetlistPostProcessor
        netlist = "a\nb"
        processor = NetlistPostProcessor([FakeFix("!"), FakeCountingFix()])
        results = processor.dry_run(netlist)
        assert len(results) == 2
        assert results[0]["fix"] == "fake-suffix"
        assert results[1]["fix"] == "fake-line-numbers"
