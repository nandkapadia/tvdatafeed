# Test Suite for tvdatafeed

This directory contains the comprehensive test suite for the tvdatafeed package.

## Test Structure

```
tests/
├── __init__.py              # Test package init
├── conftest.py              # Pytest fixtures and configuration
├── test_intervals.py        # Tests for Interval enum
├── test_authentication.py   # Tests for authentication and token handling
├── test_main.py             # Tests for TvDatafeed class
└── test_datafeed.py         # Tests for TvDatafeedLive, Seis, and Consumer
```

## Running Tests

### Install Test Dependencies

```bash
pip install -r requirements-dev.txt
```

### Run All Tests

```bash
pytest
```

### Run with Coverage

```bash
pytest --cov=tvDatafeed --cov-report=html --cov-report=term-missing
```

### Run Specific Test File

```bash
pytest tests/test_main.py
```

### Run Specific Test Class or Method

```bash
pytest tests/test_main.py::TestTvDatafeedInit
pytest tests/test_main.py::TestTvDatafeedInit::test_init_anonymous
```

### Run Tests with Markers

```bash
# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Skip slow tests
pytest -m "not slow"
```

## Test Coverage

To generate an HTML coverage report:

```bash
pytest --cov=tvDatafeed --cov-report=html
open htmlcov/index.html  # View the report
```

## Test Markers

- `unit`: Unit tests (fast, isolated)
- `integration`: Integration tests (may require network)
- `slow`: Slow running tests
- `requires_auth`: Tests that require authentication

## Continuous Integration

Tests run automatically on:
- Push to main or develop branches
- Pull requests

The CI pipeline runs tests on:
- Python 3.10, 3.11, 3.12
- Ubuntu, macOS, and Windows

See `.github/workflows/tests.yml` for details.

## Writing New Tests

### Test Naming Convention

- Test files: `test_*.py`
- Test classes: `Test*`
- Test methods: `test_*`

### Example Test

```python
import pytest
from tvDatafeed import TvDatafeed, Interval


class TestMyFeature:
    """Test my new feature."""

    def test_feature_works(self):
        """Test that feature works as expected."""
        tv = TvDatafeed()
        result = tv.some_method()
        assert result is not None

    def test_feature_with_mock(self, mock_websocket):
        """Test feature with mocked dependencies."""
        tv = TvDatafeed()
        # Use mocked websocket
        result = tv.some_method()
        assert result == expected_value
```

### Using Fixtures

Common fixtures available in `conftest.py`:
- `mock_token`: Valid JWT token
- `mock_expired_token`: Expired JWT token
- `mock_websocket`: Mocked WebSocket connection
- `sample_ohlcv_data`: Sample DataFrame with OHLCV data
- `tmp_path`: Temporary directory for file operations

## Troubleshooting

### Tests Failing Locally

1. Ensure all dependencies are installed:
   ```bash
   pip install -r requirements.txt -r requirements-dev.txt
   ```

2. Clear pytest cache:
   ```bash
   pytest --cache-clear
   ```

3. Run tests in verbose mode:
   ```bash
   pytest -vv
   ```

### Import Errors

Make sure the package is installed in development mode:
```bash
pip install -e .
```

## Code Quality

### Run Black (formatter)

```bash
black tvDatafeed tests
```

### Run Flake8 (linter)

```bash
flake8 tvDatafeed tests --max-line-length=100
```

### Run isort (import sorter)

```bash
isort tvDatafeed tests --profile black
```

### Run mypy (type checker)

```bash
mypy tvDatafeed --ignore-missing-imports
```

## Contributing

When contributing tests:
1. Write clear, descriptive test names
2. Include docstrings explaining what is being tested
3. Use appropriate fixtures to avoid code duplication
4. Mock external dependencies (WebSocket, HTTP requests)
5. Ensure tests are isolated and can run independently
6. Aim for high code coverage (>80%)

For more details, see the main [CONTRIBUTING.md](../CONTRIBUTING.md) file.
