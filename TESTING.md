# Testing Guide for tvdatafeed

This document provides comprehensive information about the tvdatafeed test suite.

## 📋 Overview

The tvdatafeed package includes a comprehensive test suite with:
- **100+ test cases** covering all major functionality
- **Mock-based testing** to avoid external dependencies
- **Automated CI/CD** with GitHub Actions
- **Code coverage tracking** with pytest-cov
- **Multi-platform testing** (Linux, macOS, Windows)
- **Multi-version testing** (Python 3.10, 3.11, 3.12)

## 🚀 Quick Start

### Install Dependencies

```bash
# Install package in development mode
pip install -e .

# Install development dependencies
pip install -r requirements-dev.txt
```

### Run Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=tvDatafeed --cov-report=html

# Run specific test file
pytest tests/test_main.py

# Run with verbose output
pytest -v
```

## 📦 Test Structure

```
tests/
├── __init__.py              # Test package initialization
├── conftest.py              # Shared fixtures and configuration
├── test_intervals.py        # Interval enum tests (5 tests)
├── test_authentication.py   # Auth and token tests (15+ tests)
├── test_main.py             # TvDatafeed core tests (30+ tests)
└── test_datafeed.py         # Live data streaming tests (20+ tests)
```

## 🧪 Test Coverage

### Current Coverage

| Module | Statements | Covered | Coverage |
|--------|------------|---------|----------|
| __init__.py | 7 | 7 | 100% |
| intervals | Complete | Complete | 100% |
| authentication | High | High | ~85% |
| main.py | 385 | Variable | ~70%* |
| datafeed.py | 226 | Variable | ~60%* |

*Coverage varies based on mocked components

### Coverage Goals

- **Critical paths**: 100% coverage
- **Core functionality**: >80% coverage
- **Overall**: >70% coverage

## 📝 Test Categories

### 1. Unit Tests

Fast, isolated tests for individual components:
- Interval enum values and operations
- Token validation and JWT parsing
- Symbol formatting
- Message construction
- Session generation

### 2. Integration Tests

Tests for component interactions:
- Authentication flow
- WebSocket connection management
- Data fetching pipeline
- Live streaming architecture

### 3. Mock-Based Tests

Tests using mocked external dependencies:
- WebSocket connections (mock_websocket)
- HTTP requests (mock_requests_post, mock_requests_get)
- File system operations (tmp_path)

## 🔧 Available Fixtures

### Common Fixtures (from conftest.py)

| Fixture | Description |
|---------|-------------|
| `mock_token` | Valid JWT token for testing |
| `mock_expired_token` | Expired JWT token |
| `mock_token_cache_file` | Temporary token cache file |
| `sample_ohlcv_data` | Sample DataFrame with OHLCV data |
| `mock_websocket` | Mocked WebSocket connection |
| `mock_requests_response` | Mocked HTTP response |
| `mock_search_response` | Mocked symbol search results |
| `mock_create_connection` | Mocked WebSocket factory |
| `mock_requests_post` | Mocked POST request |
| `mock_requests_get` | Mocked GET request |

## 🎯 Test Markers

```python
@pytest.mark.unit          # Fast unit tests
@pytest.mark.integration   # Integration tests
@pytest.mark.slow          # Slow running tests
@pytest.mark.requires_auth # Requires authentication
```

Usage:
```bash
pytest -m unit              # Run only unit tests
pytest -m "not slow"        # Skip slow tests
pytest -m integration       # Run integration tests
```

## 🛠️ Makefile Commands

Convenient commands for common tasks:

```bash
make help          # Show all available commands
make install-dev   # Install with dev dependencies
make test          # Run tests with coverage
make test-cov      # Run tests and open coverage report
make test-quick    # Run tests without coverage
make lint          # Run all linters
make format        # Format code with black/isort
make clean         # Clean build artifacts
make build         # Build package
make ci            # Run CI checks locally
```

## 🔍 Test Examples

### Basic Test

```python
def test_tvdatafeed_init():
    """Test TvDatafeed initialization."""
    tv = TvDatafeed()
    assert tv.token is None
```

### Test with Fixture

```python
def test_with_mock_token(mock_token):
    """Test using a mock token."""
    assert len(mock_token) > 100
    assert mock_token.count('.') == 2  # JWT format
```

### Test with Mocking

```python
def test_get_hist(mock_create_connection):
    """Test historical data fetching."""
    tv = TvDatafeed()
    data = tv.get_hist("AAPL", "NASDAQ", n_bars=10)
    # Assertions...
```

### Test Exception Handling

```python
def test_invalid_n_bars():
    """Test that invalid n_bars raises ValueError."""
    tv = TvDatafeed()
    with pytest.raises(ValueError, match="n_bars must be between"):
        tv.get_hist("AAPL", "NASDAQ", n_bars=0)
```

## 🚨 Common Issues

### Import Errors

**Problem**: `ModuleNotFoundError: No module named 'tvDatafeed'`

**Solution**:
```bash
pip install -e .
```

### Fixture Not Found

**Problem**: `fixture 'mock_token' not found`

**Solution**: Ensure `conftest.py` is in the tests directory and pytest can discover it.

### Tests Pass Locally But Fail in CI

**Possible causes**:
- Platform-specific behavior
- Missing dependencies in CI
- Hardcoded paths
- Timezone differences

**Solution**: Run tests in Docker or use matrix testing locally.

## 📊 Continuous Integration

### GitHub Actions Workflow

Located at `.github/workflows/tests.yml`

**Triggers**:
- Push to main/develop
- Pull requests

**Matrix Testing**:
- Python: 3.10, 3.11, 3.12
- OS: Ubuntu, macOS, Windows

**Steps**:
1. Checkout code
2. Set up Python
3. Install dependencies
4. Run tests with coverage
5. Upload coverage to Codecov
6. Run linters (black, flake8, isort, mypy)

### Local CI Simulation

```bash
make ci
```

## 📈 Coverage Reports

### Generate HTML Report

```bash
pytest --cov=tvDatafeed --cov-report=html
open htmlcov/index.html
```

### Generate Terminal Report

```bash
pytest --cov=tvDatafeed --cov-report=term-missing
```

### Coverage Requirements

- All new code should include tests
- Aim for >80% coverage on new features
- Critical paths must have 100% coverage

## ✍️ Writing New Tests

### Checklist

- [ ] Clear, descriptive test name
- [ ] Docstring explaining what is tested
- [ ] Uses appropriate fixtures
- [ ] Mocks external dependencies
- [ ] Tests both success and failure cases
- [ ] Isolated from other tests
- [ ] Runs quickly (<1 second if possible)

### Example Template

```python
class TestNewFeature:
    """Tests for new feature."""

    def test_feature_success(self):
        """Test that feature works under normal conditions."""
        # Arrange
        tv = TvDatafeed()
        
        # Act
        result = tv.new_feature()
        
        # Assert
        assert result is not None

    def test_feature_error_handling(self):
        """Test that feature handles errors gracefully."""
        tv = TvDatafeed()
        
        with pytest.raises(ValueError):
            tv.new_feature(invalid_param=True)
```

## 🤝 Contributing Tests

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/my-tests`
3. **Write tests**: Add tests in `tests/` directory
4. **Run tests**: `make test` or `pytest`
5. **Check coverage**: Ensure >80% coverage
6. **Format code**: `make format`
7. **Commit**: `git commit -m "Add tests for feature X"`
8. **Push**: `git push origin feature/my-tests`
9. **Create PR**: Submit pull request

## 📚 Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-cov documentation](https://pytest-cov.readthedocs.io/)
- [unittest.mock documentation](https://docs.python.org/3/library/unittest.mock.html)
- [Testing Best Practices](https://docs.python-guide.org/writing/tests/)

## 💡 Tips

1. **Run tests frequently** during development
2. **Use `-v` flag** for verbose output when debugging
3. **Use `-k` filter** to run specific tests: `pytest -k "test_auth"`
4. **Use `--pdb`** to drop into debugger on failures
5. **Use `--lf`** to rerun only failed tests
6. **Keep tests fast** by mocking external dependencies
7. **Write tests first** (TDD) when possible

## 🎓 Testing Philosophy

Our testing approach follows these principles:

1. **Fast**: Tests should run quickly
2. **Isolated**: Tests should not depend on each other
3. **Repeatable**: Same results every time
4. **Self-validating**: Clear pass/fail
5. **Timely**: Written alongside code

## 📞 Support

If you have questions about testing:
1. Check this guide
2. Look at existing tests for examples
3. Review pytest documentation
4. Open an issue on GitHub

---

**Happy Testing!** 🎉

Remember: Good tests make confident code!
