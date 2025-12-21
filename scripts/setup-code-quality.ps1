# Setup script for code quality tools (Windows PowerShell)

Write-Host "🔧 Setting up code quality tools for XenRay..." -ForegroundColor Cyan

# Check if poetry is installed
if (-not (Get-Command poetry -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Poetry is not installed. Please install it first." -ForegroundColor Red
    exit 1
}

Write-Host "📦 Installing dependencies..." -ForegroundColor Yellow
poetry install --with dev

Write-Host "🪝 Installing pre-commit hooks..." -ForegroundColor Yellow
poetry run pre-commit install

Write-Host "✅ Running initial code quality checks..." -ForegroundColor Green

Write-Host "  → Checking code formatting with Black..." -ForegroundColor White
$blackCheck = poetry run black --check src tests 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ⚠️  Formatting issues found. Auto-fixing..." -ForegroundColor Yellow
    poetry run black src tests
}

Write-Host "  → Checking import sorting with isort..." -ForegroundColor White
$isortCheck = poetry run isort --check-only src tests 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ⚠️  Import sorting issues found. Auto-fixing..." -ForegroundColor Yellow
    poetry run isort src tests
}

Write-Host "  → Linting with Flake8..." -ForegroundColor White
poetry run flake8 src tests --max-line-length=120 --count

Write-Host ""
Write-Host "✨ Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "📝 Quick reference:" -ForegroundColor Cyan
Write-Host "  • Format code:        poetry run black src tests"
Write-Host "  • Sort imports:       poetry run isort src tests"
Write-Host "  • Run linter:         poetry run flake8 src tests --max-line-length=120"
Write-Host "  • Run all checks:     poetry run pre-commit run --all-files"
Write-Host "  • Run tests:          poetry run pytest"
Write-Host ""
Write-Host "💡 Pre-commit hooks are now active and will run automatically on git commit." -ForegroundColor Blue
