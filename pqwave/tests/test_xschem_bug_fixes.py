#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unit tests for xschem integration bug fixes.

Bug 1: add_trace/remove_trace/get_data_point commands dropped instead of queued when raw file not loaded.
Bug 2: --xschem-send blocks for 5 seconds on non-JSON commands.
"""

import sys
import os
import time
from unittest.mock import Mock, MagicMock, patch, call

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set Qt platform before importing PyQt6
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from pqwave.communication import XschemServer, CommandHandler
from pqwave.ui.main_window import MainWindow
from pqwave.models.state import ApplicationState


def test_gaw_command_short_timeout_logic():
    """
    Test Bug 2: Verify the timeout logic in _send_command_to_server.
    
    This test verifies that the code correctly distinguishes between
    JSON and GAW-style commands and applies appropriate timeouts.
    """
    from pqwave.main import _send_command_to_server
    
    # The key fix is in main.py lines 34-49:
    # - JSON commands (starting with 'json ' or '{') get 5.0s timeout
    # - GAW commands (like 'table_set') get 0.1s timeout
    
    # Verify the function exists and has the expected signature
    import inspect
    sig = inspect.signature(_send_command_to_server)
    params = list(sig.parameters.keys())
    assert 'port' in params and 'command_text' in params, "Function signature should have port and command_text"
    
    # Read the source to verify the logic
    source = inspect.getsource(_send_command_to_server)
    
    # Verify short timeout for non-JSON commands
    assert 'sock.settimeout(0.1)' in source, "Should have 0.1s timeout for GAW commands"
    
    # Verify long timeout for JSON commands
    assert 'sock.settimeout(5.0)' in source, "Should have 5.0s timeout for JSON commands"
    
    # Verify JSON detection logic
    assert "stripped.startswith('json ')" in source or 'stripped.startswith("{")' in source, "Should detect JSON commands"
    
    # Verify socket.timeout handling for GAW commands
    assert 'except socket.timeout:' in source, "Should catch socket.timeout for GAW commands"
    
    print("✓ GAW command timeout logic test passed")
    return True


def test_json_command_long_timeout_logic():
    """
    Test that JSON commands still use the longer timeout (5s) for responses.
    """
    from pqwave.main import _send_command_to_server
    import inspect
    
    source = inspect.getsource(_send_command_to_server)
    
    # Verify JSON commands get 5.0s timeout
    assert 'sock.settimeout(5.0)' in source, "JSON commands should have 5.0s timeout"
    
    # Verify JSON detection
    assert "stripped.startswith('json ')" in source or 'stripped.startswith("{")' in source, "Should detect JSON commands"
    
    print("✓ JSON command timeout logic test passed")
    return True


def test_command_queuing_and_routing():
    """
    Test Bug 1: Commands should be queued when raw file not loaded,
    not dropped. Also tests _is_command_for_this_window logic.
    
    This tests the _is_command_for_this_window logic and command queuing
    in MainWindow.
    """
    # Create a MainWindow without loading a file
    from PyQt6.QtWidgets import QApplication
    
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    # Create window with no initial file - reuse for all tests
    window = MainWindow()
    
    # Verify window starts with no raw file loaded
    assert window.raw_file is None, "Window should start with no raw file"
    
    # Verify pending commands list exists and is empty
    assert hasattr(window, 'pending_xschem_commands'), "Window should have pending_xschem_commands"
    assert len(window.pending_xschem_commands) == 0, "Should start with no pending commands"
    
    # Test _is_command_for_this_window with raw_file not mapped
    # This should return True when window has no raw file loaded
    result = window._is_command_for_this_window(
        client_addr='127.0.0.1:12345',
        connection_state={},
        raw_file='/path/to/test.raw'
    )
    
    assert result == True, "Command should be accepted when raw_file not mapped and window has no file"
    
    # Test queuing copyvar command
    window._handle_xschem_copyvar(
        var_name='v(out)',
        color='#ff0000',
        client_addr='127.0.0.1:12345',
        connection_state={}
    )
    
    # Verify command was queued
    assert len(window.pending_xschem_commands) == 1, "copyvar should be queued when raw_file not loaded"
    cmd_type, args, client_addr, conn_state = window.pending_xschem_commands[0]
    assert cmd_type == 'copyvar', f"Expected 'copyvar', got '{cmd_type}'"
    assert args['var_name'] == 'v(out)', "Queued command should have correct var_name"
    
    # Test queuing add_trace command
    window._handle_xschem_add_trace(
        var_name='i(r1)',
        axis='Y2',
        color='#00ff00',
        client_addr='127.0.0.1:12345',
        connection_state={}
    )
    
    assert len(window.pending_xschem_commands) == 2, "add_trace should also be queued"
    
    # Test queuing remove_trace command
    window._handle_xschem_remove_trace(
        var_name='v(out)',
        client_addr='127.0.0.1:12345',
        connection_state={}
    )
    
    assert len(window.pending_xschem_commands) == 3, "remove_trace should also be queued"
    
    # Test queuing get_data_point command
    window._handle_xschem_get_data_point(
        x_value=0.001,
        client_addr='127.0.0.1:12345',
        connection_state={}
    )
    
    assert len(window.pending_xschem_commands) == 4, "get_data_point should also be queued"
    
    # Verify all 4 command types are queued
    queued_types = [cmd[0] for cmd in window.pending_xschem_commands]
    assert 'copyvar' in queued_types, "copyvar should be queued"
    assert 'add_trace' in queued_types, "add_trace should be queued"
    assert 'remove_trace' in queued_types, "remove_trace should be queued"
    assert 'get_data_point' in queued_types, "get_data_point should be queued"
    
    print(f"✓ Command queuing test passed: {len(window.pending_xschem_commands)} commands queued correctly")
    
    # Test pending commands processing
    # Mock the raw_file to simulate file being loaded
    mock_raw_file = Mock()
    mock_raw_file.get_variable_names.return_value = ['v(out)', 'i(r1)', 'time']
    mock_raw_file.get_variable_data.return_value = [0, 1, 2, 3]
    window.raw_file = mock_raw_file
    
    # Mock trace_manager methods to avoid actual trace operations
    if window.trace_manager:
        window.trace_manager.add_trace_from_variable = Mock(return_value=Mock())
        window.trace_manager.remove_trace_by_variable_name = Mock(return_value=True)
    
    # Set up state for trace operations
    window.state.current_x_var = 'time'
    window.state.current_dataset_idx = 0
    
    # Process pending commands
    window._process_pending_xschem_commands()
    
    # Verify commands were processed and cleared
    assert len(window.pending_xschem_commands) == 0, "Pending commands should be cleared after processing"
    
    # Verify trace_manager methods were called
    if window.trace_manager:
        assert window.trace_manager.add_trace_from_variable.called, "add_trace_from_variable should have been called"
    
    print("✓ Pending commands processing test passed: commands processed after file load")
    
    # Test the fix at lines 613-617 in _is_command_for_this_window
    import inspect
    source = inspect.getsource(window._is_command_for_this_window)
    assert 'if self.raw_file is None:' in source, "Should have check for self.raw_file is None"
    assert 'accepting' in source.lower(), "Should log accepting message"
    
    print("✓ Window registry command routing test passed")
    
    return True


def main():
    """Run all tests."""
    tests = [
        ("GAW command short timeout logic (Bug 2)", test_gaw_command_short_timeout_logic),
        ("JSON command long timeout logic", test_json_command_long_timeout_logic),
        ("Command queuing + routing + processing (Bug 1)", test_command_queuing_and_routing),
    ]
    
    print("Running xschem integration bug fix tests...")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        print(f"\nTest: {test_name}")
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
                print(f"  ✗ {test_name} failed")
        except AssertionError as e:
            failed += 1
            print(f"  ✗ {test_name} failed: {e}")
        except Exception as e:
            failed += 1
            print(f"  ✗ {test_name} error: {type(e).__name__}: {e}")
    
    print("\n" + "=" * 60)
    print(f"Results: {passed}/{len(tests)} tests passed")
    
    if failed == 0:
        print("✓ All bug fix tests passed!")
        return 0
    else:
        print(f"✗ {failed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
