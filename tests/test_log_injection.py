"""Verify scanner analyzer logger calls don't use f-strings with user-controlled data."""
import inspect
import re


def test_mcp_analyzer_no_fstring_in_logger_calls():
    """MCP analyzer must use %s positional args, not f-strings, in logger calls."""
    from pearl.scanning.analyzers.mcp import analyzer as mcp_module

    source = inspect.getsource(mcp_module)
    log_calls = re.findall(r'logger\.(error|exception|warning|info|debug)\(f"', source)
    assert log_calls == [], (
        f"Found f-string in logger call(s): {log_calls}. Use %s positional args instead."
    )


def test_model_file_scanner_no_fstring_in_logger_calls():
    """Model file scanner must use %s positional args, not f-strings, in logger calls."""
    from pearl.scanning.analyzers.model_file import scanner as scanner_module

    source = inspect.getsource(scanner_module)
    log_calls = re.findall(r'logger\.(error|exception|warning|info|debug)\(f"', source)
    assert log_calls == [], (
        f"Found f-string in logger call(s): {log_calls}. Use %s positional args instead."
    )
