# Code Quality Setup Guide

## Overview

This project uses automated code quality checks to maintain consistent code style and catch common issues early.

## Tools Used

- **Black**: Automatic code formatter
- **isort**: Import statement organizer
- **Flake8**: Linter for PEP8 compliance and code quality

## CI/CD Pipeline

The GitHub Actions workflow (`.github/workflows/code-quality.yml`) runs automatically on:
- Push to `main` or `develop` branches
- Pull requests to `main` or `develop` branches

### What the CI Checks

1. **Black** (`--check` mode): Verifies code formatting
2. **isort** (`--check-only` mode): Verifies import sorting
3. **Flake8**: Detects linting issues (max line length: 120)

**Important**: The CI pipeline does NOT auto-fix issues. It only reports them and fails the build if problems are found.

## Local Development

### Quick Fix Commands

If CI fails, run these commands locally to fix issues:

```bash
# Fix formatting with Black
poetry run black src tests

# Fix import sorting with isort
poetry run isort src tests

# Check for linting issues (manual fixes required)
poetry run flake8 src tests --max-line-length=120
```

### Pre-commit Hooks (Recommended)

Pre-commit hooks run automatically before each commit, catching issues before they reach CI.

#### Installation

```bash
# Install pre-commit package
poetry add --group dev pre-commit

# Install the git hooks
poetry run pre-commit install
```

#### Usage

Once installed, hooks run automatically on `git commit`. To run manually:

```bash
# Run on all files
poetry run pre-commit run --all-files

# Run on staged files only
poetry run pre-commit run
```

#### Bypassing Hooks (Not Recommended)

If you need to commit without running hooks:

```bash
git commit --no-verify -m "your message"
```

## Configuration Files

- `.github/workflows/code-quality.yml`: CI/CD pipeline configuration
- `.pre-commit-config.yaml`: Pre-commit hooks configuration
- `pyproject.toml`: Black and isort settings (if customized)

## Flake8 Configuration

Current settings:
- Max line length: 120 characters
- Ignored errors: E203 (whitespace before ':'), W503 (line break before binary operator)

To customize, create a `.flake8` file in the project root.

## Troubleshooting

### CI Fails But Local Checks Pass

1. Ensure you're using the same Python version (3.13)
2. Run `poetry install` to sync dependencies
3. Clear any cached files: `find . -type d -name __pycache__ -exec rm -rf {} +`

### Pre-commit Hooks Not Running

1. Verify installation: `poetry run pre-commit --version`
2. Reinstall hooks: `poetry run pre-commit install`
3. Check git hooks: `ls -la .git/hooks/`

### Flake8 Errors You Can't Fix

Some Flake8 errors may be false positives or intentional. You can:
1. Add `# noqa: <error-code>` comment to the line
2. Update `.flake8` to ignore specific errors project-wide

## Best Practices

1. **Run checks before committing**: Use pre-commit hooks or run commands manually
2. **Fix issues locally**: Don't rely on CI to catch formatting issues
3. **Keep line length under 120**: Break long lines for readability
4. **Organize imports**: Let isort handle import ordering automatically
5. **Review Flake8 warnings**: They often catch real bugs or code smells

## Integration with IDEs

### VS Code

Install extensions:
- Python (Microsoft)
- Black Formatter
- isort

Add to `.vscode/settings.json`:
```json
{
  "python.formatting.provider": "black",
  "python.linting.flake8Enabled": true,
  "python.linting.enabled": true,
  "editor.formatOnSave": true,
  "[python]": {
    "editor.codeActionsOnSave": {
      "source.organizeImports": true
    }
  }
}
```

### PyCharm

1. Install Black plugin
2. Enable Black formatter in Settings → Tools → Black
3. Enable isort in Settings → Tools → isort
4. Configure Flake8 in Settings → Tools → External Tools
