# Test Coverage Badge Setup

This document explains how to set up dynamic test coverage badges for XenRay.

## Option 1: Codecov (Recommended)

Codecov provides automatic coverage badges and detailed reports.

### Setup Steps

1. **Sign up for Codecov**:
   - Go to [codecov.io](https://codecov.io/)
   - Sign in with your GitHub account
   - Add the XenRay repository

2. **Update README Badge**:
   Replace the static coverage badge in `README.md` with:
   ```markdown
   ![Coverage](https://codecov.io/gh/xenups/xenray/branch/main/graph/badge.svg)
   ```

3. **That's it!** The `.github/workflows/tests.yml` workflow already uploads coverage to Codecov.

## Option 2: Dynamic Gist Badge

For more control, use a GitHub Gist to store the badge data.

### Setup Steps

1. **Create a Gist**:
   - Go to [gist.github.com](https://gist.github.com/)
   - Create a new **public** gist named `xenray-coverage.json`
   - Content: `{}`

2. **Create GitHub Token**:
   - Go to GitHub Settings → Developer settings → Personal access tokens
   - Generate new token (classic)
   - Select scope: `gist`
   - Copy the token

3. **Add Secret to Repository**:
   - Go to repository Settings → Secrets and variables → Actions
   - Add new secret: `GIST_SECRET` with your token

4. **Update Workflow**:
   - Edit `.github/workflows/tests.yml`
   - Replace `YOUR_GIST_ID_HERE` with your gist ID (from the URL)

5. **Update README Badge**:
   ```markdown
   ![Coverage](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/YOUR_USERNAME/YOUR_GIST_ID/raw/xenray-coverage.json)
   ```

## Option 3: Static Badge (Current)

The current static badge in README.md:
```markdown
![Coverage](https://img.shields.io/badge/coverage-80%25-yellowgreen.svg)
```

**Pros**: No setup required, works immediately
**Cons**: Must be manually updated

### Updating Static Badge

After running tests locally:
```bash
poetry run pytest --cov=src --cov-report=term

# Note the coverage percentage, then update README.md badge:
# - 90%+: brightgreen
# - 80-89%: green  
# - 70-79%: yellowgreen
# - 60-69%: yellow
# - <60%: red
```

## Recommended Approach

For public repositories: **Use Codecov** (Option 1)
- Free for open source
- Automatic updates
- Detailed coverage reports
- Pull request comments

For private repositories or more control: **Use Gist Badge** (Option 2)
- More customization
- No third-party service dependency
- Requires initial setup

## Current Coverage

As of the latest test run:
- **Overall**: 58%
- **LinkParser**: 88%
- **SingboxService**: 83%
- **ConfigManager**: 73%

Target: >85% for all core modules
