#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test raw file conversion between SPICE, LTspice, and QSPICE formats.
"""

import os
import tempfile
import numpy as np
import pytest

from pqwave.models.rawfile import RawFile
from pqwave.models.raw_converter import write_raw_file, FORMAT_CONFIG


@pytest.fixture
def transient_rawfile():
    """Load bridge.raw for transient data tests."""
    return RawFile('pqwave/tests/bridge.raw')


@pytest.fixture
def ac_rawfile():
    """Load cdg.raw for AC/complex data tests."""
    return RawFile('pqwave/tests/cdg.raw')


class TestRawConverter:
    """Test raw file conversion between formats."""

    @pytest.mark.parametrize('target_format', ['ltspice', 'ngspice', 'qspice'])
    def test_transient_conversion(self, transient_rawfile, target_format):
        """Test transient data conversion preserves all data."""
        dataset = transient_rawfile.datasets[0]
        variables = dataset['variables']
        data = dataset['data']

        ext = FORMAT_CONFIG[target_format]['extension']
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
            out_path = f.name

        try:
            write_raw_file(
                out_path, dataset['title'], dataset['date'],
                dataset['plotname'], dataset['flags'],
                variables, data, target_format,
                dataset.get('_is_ac_or_complex', False)
            )

            # Verify file was created
            assert os.path.exists(out_path)
            assert os.path.getsize(out_path) > 0

            # Verify file can be read back
            from spicelib import RawRead
            rr = RawRead(out_path)
            assert rr.dialect == target_format
            assert len(rr._plots) == 1
            assert rr._plots[0]._nVariables == len(variables)
            assert rr._plots[0]._nPoints == data.shape[0]

            # Verify data integrity
            for var in variables[:2]:  # Test first 2 variables
                var_name = var['name']
                orig = np.array(transient_rawfile.get_variable_data(var_name, 0))
                conv = np.array(rr.get_trace(var_name))
                assert np.allclose(orig, conv, rtol=1e-5), \
                    f"Data mismatch for {var_name} in {target_format}"
        finally:
            if os.path.exists(out_path):
                os.unlink(out_path)

    @pytest.mark.parametrize('target_format', ['ltspice', 'ngspice'])
    def test_ac_conversion(self, ac_rawfile, target_format):
        """Test AC/complex data conversion for ltspice and ngspice."""
        dataset = ac_rawfile.datasets[0]
        variables = dataset['variables']
        data = dataset['data']

        ext = FORMAT_CONFIG[target_format]['extension']
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
            out_path = f.name

        try:
            write_raw_file(
                out_path, dataset['title'], dataset['date'],
                dataset['plotname'], dataset['flags'],
                variables, data, target_format,
                dataset.get('_is_ac_or_complex', False)
            )

            from spicelib import RawRead
            rr = RawRead(out_path)
            assert rr.dialect == target_format

            # Verify complex data integrity
            for var in variables:
                var_name = var['name']
                orig = np.array(ac_rawfile.get_variable_data(var_name, 0))
                conv = np.array(rr.get_trace(var_name))
                assert np.iscomplexobj(conv), f"{var_name} should be complex in {target_format}"
                assert np.allclose(orig, conv, rtol=1e-5), \
                    f"Complex data mismatch for {var_name} in {target_format}"
        finally:
            if os.path.exists(out_path):
                os.unlink(out_path)

    def test_format_config_complete(self):
        """Verify all three formats have required config keys."""
        required_keys = [
            'encoding', 'command_line', 'real_dtype', 'time_dtype',
            'ac_dtype', 'freq_dtype', 'extension'
        ]
        for fmt in ['ltspice', 'ngspice', 'qspice']:
            assert fmt in FORMAT_CONFIG
            config = FORMAT_CONFIG[fmt]
            for key in required_keys:
                assert key in config, f"{fmt} missing {key}"

    def test_dialect_detection(self):
        """Verify converted files are correctly auto-detected by spicelib."""
        dataset = RawFile('pqwave/tests/bridge.raw').datasets[0]
        for fmt in ['ltspice', 'ngspice', 'qspice']:
            ext = FORMAT_CONFIG[fmt]['extension']
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
                out_path = f.name

            try:
                write_raw_file(
                    out_path, dataset['title'], dataset['date'],
                    dataset['plotname'], dataset['flags'],
                    dataset['variables'], dataset['data'], fmt, False
                )
                from spicelib import RawRead
                rr = RawRead(out_path)
                assert rr.dialect == fmt, \
                    f"Expected dialect {fmt} but got {rr.dialect}"
            finally:
                if os.path.exists(out_path):
                    os.unlink(out_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
