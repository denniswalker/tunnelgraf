# SCP Integration Tests

This directory contains comprehensive SCP (Secure Copy Protocol) integration tests for tunnelgraf. These tests perform end-to-end testing of the SCP functionality by:

1. **Starting the Docker Compose stack** - Sets up the test environment with multiple containers
2. **Running tunnelgraf connect** - Establishes SSH tunnels through the container chain
3. **Creating test files and directories** - Generates various types of test data
4. **Copying files to/from containers** - Tests upload and download operations
5. **Verifying transfers** - Ensures file integrity and completeness
6. **Cleaning up everything** - Properly shuts down all services and removes test files

## Test Files

### `test_scp_integration.py`
The main comprehensive integration test suite that includes:

- **Single file transfers** (upload/download)
- **Directory transfers** with nested files
- **Binary file transfers** 
- **Large file transfers** (~1MB)
- **Empty file transfers**
- **Multiple container transfers** (testing all containers in the tunnel chain)
- **Tunnel ID parameter testing**
- **Error handling** for invalid paths and tunnel IDs
- **Concurrent transfers** using multiple threads

### `test_scp_functionality.py`
Unit tests for the Transfer class and SCP command execution:

- **Transfer class initialization** and validation
- **SCP command generation** for uploads and downloads
- **Path validation** and error handling
- **Mock testing** of subprocess calls
- **Command syntax validation**

### `run_scp_tests.py`
A test runner script that demonstrates how to run the comprehensive tests:

```bash
# Run all SCP integration tests
python tests/run_scp_tests.py

# Run a quick test to verify basic functionality
python tests/run_scp_tests.py quick

# Show help
python tests/run_scp_tests.py help
```

## Test Environment

The tests use the Docker Compose setup defined in `docker-compose.yml`:

- **bastion** - First SSH server (port 2222)
- **sshd1** - Second SSH server in the chain
- **sshd2** - Third SSH server in the chain  
- **nginx** - Web server at the end of the chain

The tunnel chain: `localhost:2222 → bastion → sshd1 → sshd2 → nginx`

## Running the Tests

### Prerequisites

1. **Docker and Docker Compose** must be installed and running
2. **OpenSSH client** (scp command) must be available
3. **sshpass** must be installed for password authentication
4. **Python dependencies** must be installed via hatch

### Quick Start

```bash
# Run a single test to verify setup
python tests/run_scp_tests.py quick

# Run all integration tests
python tests/run_scp_tests.py

# Run specific tests with pytest
hatch run test:python src/ -xvs tests/test_scp_integration.py::TestSCPIntegration::test_upload_single_file
```

### Manual Testing

You can also test SCP functionality manually:

```bash
# Start the Docker Compose stack
docker-compose up -d

# Start tunnelgraf
hatch run test:python src/ --profile tests/connections_profiles/four_in_a_row.yaml connect

# In another terminal, test SCP
hatch run test:python src/ --profile tests/connections_profiles/four_in_a_row.yaml scp /path/to/local/file bastion:/tmp/remote/file

# Stop tunnelgraf
hatch run test:python src/ --profile tests/connections_profiles/four_in_a_row.yaml stop

# Stop Docker Compose
docker-compose down
```

## Test Coverage

The integration tests cover:

### File Types
- **Text files** with various content
- **Binary files** with random data
- **Empty files**
- **Large files** (~1MB) to test performance
- **Directories** with nested subdirectories

### Transfer Operations
- **Upload** (local → remote)
- **Download** (remote → local)
- **Directory transfers** with recursive copying
- **Multiple concurrent transfers**

### Error Scenarios
- **Non-existent local files**
- **Non-existent remote files**
- **Invalid tunnel IDs**
- **Permission errors**
- **Network connectivity issues**

### Container Testing
- **bastion** - Direct SSH access
- **sshd1** - Through one tunnel hop
- **sshd2** - Through two tunnel hops
- **nginx** - Through three tunnel hops

## Test Verification

Each test includes comprehensive verification:

1. **File existence** - Ensures files are created at destination
2. **Content comparison** - Verifies file contents match exactly
3. **Directory structure** - Checks all files and subdirectories are transferred
4. **Binary integrity** - Validates binary files are transferred correctly
5. **Large file handling** - Tests performance with substantial data

## Troubleshooting

### Common Issues

1. **Docker Compose not starting**
   ```bash
   # Check Docker is running
   docker ps
   
   # Rebuild containers
   docker-compose up --build -d
   ```

2. **SCP command not found**
   ```bash
   # Install OpenSSH client
   # On macOS: brew install openssh
   # On Ubuntu: sudo apt-get install openssh-client
   ```

3. **sshpass not found**
   ```bash
   # Install sshpass
   # On macOS: brew install sshpass
   # On Ubuntu: sudo apt-get install sshpass
   ```

4. **Permission denied errors**
   - Ensure test files have appropriate permissions
   - Check that containers are running with correct user permissions

### Debug Mode

Run tests with verbose output:

```bash
hatch run test:python src/ -xvs tests/test_scp_integration.py -k test_upload_single_file
```

### Manual Verification

After running tests, you can manually verify the setup:

```bash
# Check if tunnels are working
ssh -p 2222 root@localhost hostname  # Should return "bastion"
ssh -p 2224 root@localhost hostname  # Should return "sshd1"
ssh -p 2225 root@localhost hostname  # Should return "sshd2"

# Test SCP manually
scp -P 2222 -o StrictHostKeyChecking=no test_file.txt root@localhost:/tmp/
```

## Performance Considerations

- **Large file tests** create ~1MB files to test transfer performance
- **Concurrent tests** use ThreadPoolExecutor to test multiple simultaneous transfers
- **Binary files** test handling of non-text data
- **Directory transfers** test recursive copying with nested structures

## Cleanup

The tests automatically clean up:

- **Temporary test files** created during testing
- **Docker containers** started for testing
- **SSH tunnels** established by tunnelgraf
- **Test directories** created in temporary locations

If tests are interrupted, you may need to manually clean up:

```bash
# Stop tunnelgraf if running
hatch run test:python src/ --profile tests/connections_profiles/four_in_a_row.yaml stop

# Stop Docker Compose
docker-compose down

# Remove temporary test directories
find /tmp -name "tunnelgraf_scp_test_*" -type d -exec rm -rf {} +
``` 