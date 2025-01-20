import sys
from pathlib import Path
import pytest

# Add the src directory to PYTHONPATH
src_path = str(Path(__file__).parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

def pytest_addoption(parser):
    """Add custom command line options."""
    parser.addoption(
        "--profile-path",
        action="store",
        default="tests/connections_profiles/four_in_a_row.yaml",
        help="Path to the connection profile file"
    )

@pytest.fixture(scope="session")
def profile_path(request):
    """Fixture to provide the profile path to tests."""
    return request.config.getoption("--profile-path") 