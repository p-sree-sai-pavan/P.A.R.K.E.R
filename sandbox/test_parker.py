import os
import sys

# Add root folder to sys.path so we can import computer packages
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from computer.telemetry import get_system_telemetry, format_telemetry_for_prompt
from computer.sandbox import write_sandbox_file, read_sandbox_file, run_sandbox_command, _resolve_path

def test_telemetry():
    print("=== Testing Telemetry ===")
    telemetry = get_system_telemetry()
    print("Aggregated Telemetry Dict:", telemetry)
    print("\nFormatted Telemetry Prompt:")
    print(format_telemetry_for_prompt(telemetry))
    print("=========================\n")

def test_sandbox_boundaries():
    print("=== Testing Sandbox Boundaries ===")
    # 1. Test valid write
    write_res = write_sandbox_file("inner_test.txt", "Hello from Sandbox!")
    print("Sandbox Write (inner_test.txt):", write_res)
    assert "Successfully wrote" in write_res, "Valid write failed!"
    
    # 2. Test valid read
    read_res = read_sandbox_file("inner_test.txt")
    print("Sandbox Read (inner_test.txt):", read_res)
    assert read_res == "Hello from Sandbox!", "Valid read failed!"
    
    # 3. Test invalid write (outside sandbox)
    print("Testing invalid write outside sandbox (should block):")
    try:
        invalid_path = "../outside_test.txt"
        resolved = _resolve_path(invalid_path)
        print("Error: Path resolved outside without throwing PermissionError:", resolved)
        sys.exit(1)
    except PermissionError as e:
        print("Success: Blocked path traversal attempt:", e)
        
    # 4. Test run command in sandbox
    print("Testing command execution in sandbox:")
    cmd_res = run_sandbox_command("echo 'Sandbox Power'")
    print("Command Result:")
    print(cmd_res)
    assert "Sandbox Power" in cmd_res, "Command execution failed!"
    print("==================================\n")

if __name__ == "__main__":
    test_telemetry()
    test_sandbox_boundaries()
    print("All tests passed successfully!")
