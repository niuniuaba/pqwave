"""Runs a sequence of NetlistFix instances against a netlist."""

from typing import Optional


class NetlistPostProcessor:
    def __init__(self, fixes: list):
        self._fixes = fixes

    def process(self, netlist: str, context: Optional[dict] = None) -> str:
        for fix in self._fixes:
            netlist = fix.apply(netlist, context)
        return netlist

    def dry_run(self, netlist: str, context: Optional[dict] = None) -> list[dict]:
        results = []
        current = netlist
        for fix in self._fixes:
            results.extend(fix.info(current, context))
            current = fix.apply(current, context)
        return results
