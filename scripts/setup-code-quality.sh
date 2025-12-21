#!/usr/bin/env bash
# Setup script for code quality tools

set -e

echo "🔧 Setting up code quality tools for XenRay..."

# Check if poetry is installed
if ! command -v poetry &> /dev/null; then
    echo "❌ Poetry is not installed. Please install it first."
    exit 1
fi

echo "📦 Installing dependencies..."
poetry install --with dev

echo "🪝 Installing pre-commit hooks..."
poetry run pre-commit install

echo "✅ Running initial code quality checks..."

echo "  → Checking code formatting with Black..."
poetry run black --check src tests || {
    echo "  ⚠️  Formatting issues found. Auto-fixing..."
    poetry run black src tests
}

echo "  → Checking import sorting with isort..."
poetry run isort --check-only src tests || {
    echo "  ⚠️  Import sorting issues found. Auto-fixing..."
    poetry run isort src tests
}

echo "  → Linting with Flake8..."
poetry run flake8 src tests --max-line-length=120 --count

echo ""
echo "✨ Setup complete!"
echo ""
echo "📝 Quick reference:"
echo "  • Format code:        poetry run black src tests"
echo "  • Sort imports:       poetry run isort src tests"
echo "  • Run linter:         poetry run flake8 src tests --max-line-length=120"
echo "  • Run all checks:     poetry run pre-commit run --all-files"
echo "  • Run tests:          poetry run pytest"
echo ""
echo "💡 Pre-commit hooks are now active and will run automatically on git commit."
