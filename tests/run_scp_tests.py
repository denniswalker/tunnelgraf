#!/usr/bin/env python3
"""
Test runner for comprehensive SCP integration tests.

This script demonstrates how to run the SCP integration tests that:
1. Start the Docker Compose stack
2. Run tunnelgraf connect
3. Create test files and directories
4. Copy files to/from containers
5. Verify transfers
6. Clean up everything

Usage:
    python tests/run_scp_tests.py
"""

import subprocess
import sys
import os
import signal
import atexit

# Global variable to track if cleanup has been done
_cleanup_done = False


def signal_handler(signum, frame):
    """Handle interrupt signals gracefully."""
    print(f"\n\n⚠️  Received signal {signum}, cleaning up...")
    cleanup_and_exit._called_from_signal = True
    cleanup_and_exit()


def cleanup_and_exit():
    """Clean up services and exit."""
    global _cleanup_done
    if not _cleanup_done:
        stop_services()
        _cleanup_done = True
    # Don't call sys.exit() in atexit handler to avoid the exception
    if hasattr(cleanup_and_exit, '_called_from_signal'):
        # Only exit if called from signal handler, not from atexit
        sys.exit(1)


# Register signal handlers and cleanup
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup_and_exit)


def check_services_running():
    """Check if Docker Compose services and tunnelgraf are already running."""
    # Check if Docker Compose services are running
    try:
        result = subprocess.run(
            ["docker-compose", "ps", "-q"], 
            capture_output=True, 
            text=True, 
            check=True
        )
        services_running = bool(result.stdout.strip())
    except subprocess.CalledProcessError:
        services_running = False
    
    # Check if tunnelgraf is running by testing tunnel port
    tunnel_running = False
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("localhost", 2224))
        tunnel_running = (result == 0)
        sock.close()
    except socket.error:
        tunnel_running = False
    
    return services_running, tunnel_running


def stop_services():
    """Stop tunnelgraf and Docker Compose stack."""
    print("\n🛑 Stopping services...")
    
    # Stop tunnelgraf using the stop command
    try:
        subprocess.run(
            ["hatch", "run", "test:python", "src/", "--profile",
             "tests/connections_profiles/four_in_a_row.yaml", "stop"],
            check=True, capture_output=True, timeout=10
        )
        print("✓ Stopped tunnelgraf")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        print("ℹ️  tunnelgraf was not running or stop command timed out")
    
    # Also try to kill any tunnelgraf processes directly
    try:
        result = subprocess.run(
            ["pkill", "-f", "tunnelgraf"], 
            capture_output=True, 
            timeout=5
        )
        if result.returncode == 0:
            print("✓ Killed tunnelgraf processes")
    except subprocess.TimeoutExpired:
        print("ℹ️  No tunnelgraf processes to kill")
    
    # Stop Docker Compose stack
    try:
        subprocess.run(["docker-compose", "down"], check=True, capture_output=True, timeout=30)
        print("✓ Stopped Docker Compose stack")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        print("ℹ️  Docker Compose stack was not running or stop command timed out")


def run_test_command(test_name, 
                    profile_path="tests/connections_profiles/four_in_a_row.yaml"):
    """Run a specific test with proper setup and teardown."""
    print("")
    print("=" * 60)
    print(f"Running test: {test_name}")
    print("=" * 60)
    
    # Setup test environment efficiently
    setup_test_environment(profile_path)
    
    # Run the test using pytest
    cmd = [
        "hatch", "run", "test:run", 
        "-x", "--tb=no", "-q", "--capture=no",  # Stop on first failure, no traceback, quiet, no capture
        f"tests/test_scp_integration.py::{test_name}",
        "--profile-path", profile_path
    ]
    
    print(f"Command: {' '.join(cmd)}")
    
    # Set environment variable to indicate we're running from test runner
    env = os.environ.copy()
    env['TUNNELGRAF_TEST_RUNNER'] = '1'
    
    # Run the command with direct output to console
    result = subprocess.run(cmd, env=env)
    
    # Display the result
    if result.returncode == 0:
        print(f"Test {test_name} PASSED")
    else:
        print(f"Test {test_name} FAILED")
    
    return result.returncode == 0


def setup_test_environment(profile_path):
    """Setup test environment with clean start."""
    print("")
    print("Setting up test environment...")
    
    # Always stop existing services first
    stop_services()
    
    # Start Docker Compose stack
    print("Starting Docker Compose stack...")
    subprocess.run(
        ["docker-compose", "up", "--force-recreate", "--build", "-d"], 
        check=True, capture_output=True
    )
    print("Docker Compose services started successfully.")
    
    # Wait for services to be ready
    import time
    import socket
    max_attempts = 60
    for port in [2222]:  # bastion port
        attempts = 0
        while attempts < max_attempts:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(("localhost", port))
                if result == 0:
                    print(f"Service bastion is ready on port {port}")
                    break
            except socket.error:
                pass
            finally:
                sock.close()
            
            attempts += 1
            time.sleep(1)
            if attempts == max_attempts:
                raise Exception(f"Service on port {port} did not become ready")
    
    # Start tunnelgraf
    print("Starting tunnelgraf...")
    subprocess.Popen(
        ["hatch", "run", "test:python", "src/", "--profile",
         profile_path, "connect", "-d"],
        preexec_fn=os.setsid,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    print("Started tunnelgraf with suppressed output")

    # Wait for tunnel to be ready
    import time
    import socket
    print("Waiting for tunnel on port 2224 to establish...")
    attempts = 0
    max_attempts = 30
    while attempts < max_attempts:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("localhost", 2224))
            if result == 0:
                print("Tunnel on port 2224 is ready")
                break
            print(f"Waiting for tunnel on port 2224... "
                  f"(attempt {attempts+1}/{max_attempts})")
        except socket.error:
            pass
        finally:
            sock.close()

        attempts += 1
        time.sleep(1)
        if attempts == max_attempts:
            raise Exception("Tunnel on port 2224 did not become ready")

    time.sleep(5)  # Give remaining tunnels time to establish
    print("Test environment ready!")


def run_all_scp_tests():
    """Run all SCP integration tests."""
    print("🚀 Starting comprehensive SCP integration tests...")
    print("This will:")
    print("1. Stop existing services (if running)")
    print("2. Start Docker Compose stack")
    print("3. Run tunnelgraf connect")
    print("4. Create test files and directories")
    print("5. Copy files to/from containers")
    print("6. Verify transfers")
    print("7. Clean up everything")
    
    # List of tests to run
    tests = [
        "TestSCPIntegration::test_upload_single_file",
        "TestSCPIntegration::test_upload_directory",
        "TestSCPIntegration::test_download_single_file",
        "TestSCPIntegration::test_download_directory",
        "TestSCPIntegration::test_binary_file_transfer",
        "TestSCPIntegration::test_large_file_transfer",
        "TestSCPIntegration::test_empty_file_transfer",
        "TestSCPIntegration::test_multiple_container_transfers",
        "TestSCPIntegration::test_concurrent_transfers",
    ]
    
    passed = 0
    failed = 0
    
    try:
        for i, test in enumerate(tests, 1):
            print(f"\n📊 Progress: {i}/{len(tests)} tests")
            if run_test_command(test):
                passed += 1
            else:
                failed += 1
        
        print(f"\n{'='*60}")
        print(f"📈 Test Results: {passed} passed, {failed} failed")
        print(f"{'='*60}")
        
        if failed == 0:
            print("🎉 All SCP integration tests passed!")
            return 0
        else:
            print(f"❌ {failed} test(s) failed")
            return 1
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Keyboard interrupt detected!")
        print("Stopping services...")
        stop_services()
        print("Tests interrupted by user")
        return 1
    finally:
        print("\n🧹 Final cleanup...")
        stop_services()
        print("✅ Cleanup complete")


def run_quick_test():
    """Run a quick test to verify basic functionality."""
    print("⚡ Running quick SCP test...")
    
    try:
        # Run just one test to verify the setup works
        success = run_test_command("TestSCPIntegration::test_upload_single_file")
        
        if success:
            print("✅ Quick test passed - SCP functionality is working")
        else:
            print("❌ Quick test failed - check your setup")
        
        return 0 if success else 1
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Keyboard interrupt detected!")
        print("Stopping services...")
        stop_services()
        print("Quick test interrupted by user")
        return 1
    finally:
        print("\n🧹 Final cleanup...")
        stop_services()
        print("✅ Cleanup complete")


def main():
    """Main function to run tests based on command line arguments."""
    if len(sys.argv) > 1:
        if sys.argv[1] == "quick":
            return run_quick_test()
        elif sys.argv[1] == "help":
            print(__doc__)
            return 0
        else:
            print(f"Unknown argument: {sys.argv[1]}")
            print("Usage: python tests/run_scp_tests.py "
                  "[quick|help]")
            return 1
    
    return run_all_scp_tests()


if __name__ == "__main__":
    sys.exit(main()) 