# Linting Guide

This codebase includes comprehensive linting for code quality and consistency.

## Linting Tools

### Python (Lambda Functions)
- **ruff**: Fast Python linter (recommended)
- **flake8**: PEP 8 style checking
- **black**: Code formatter
- **pylint**: Comprehensive static analysis

### JavaScript/JSX (UI)
- **ESLint**: JavaScript/React linting
- **React Hooks Plugin**: React Hooks rules

### Infrastructure
- **tofu fmt**: Terraform/OpenTofu formatter
- **tflint**: Terraform linter (optional)

### Shell Scripts
- **shellcheck**: Shell script linting

## Quick Start

### Run All Linting

```bash
./scripts/lint.sh
```

This will:
1. Lint all Python files
2. Lint all JavaScript/JSX files
3. Check Terraform formatting
4. Lint shell scripts

### Install Linting Tools

**Python:**
```bash
pip install -r requirements-dev.txt
# or
pip install ruff flake8 black pylint
```

**JavaScript:**
```bash
cd ui
npm install
```

**Terraform:**
```bash
# OpenTofu includes fmt command
tofu fmt -recursive infrastructure/

# Optional: tflint
brew install tflint  # macOS
```

**Shell:**
```bash
brew install shellcheck  # macOS
```

## Individual Linting Commands

### Python

```bash
# Ruff (fastest, recommended)
ruff check lambdas/

# Flake8
flake8 lambdas/

# Black (format check)
black --check lambdas/

# Black (auto-format)
black lambdas/

# Pylint
pylint lambdas/
```

### JavaScript/JSX

```bash
cd ui

# Lint
npm run lint

# Lint and auto-fix
npm run lint:fix

# Or directly
npx eslint src/ --ext .js,.jsx
```

### Terraform/OpenTofu

```bash
cd infrastructure

# Format check
tofu fmt -check -recursive .

# Auto-format
tofu fmt -recursive .

# Lint (if tflint installed)
tflint .
```

### Shell Scripts

```bash
shellcheck scripts/*.sh
```

## Configuration Files

- `.flake8` - Flake8 configuration
- `.pylintrc` - Pylint configuration
- `pyproject.toml` - Ruff and Black configuration
- `.eslintrc.js` - ESLint configuration
- `.eslintignore` - ESLint ignore patterns

## Pre-commit Hooks (Optional)

Create `.git/hooks/pre-commit`:

```bash
#!/bin/bash
./scripts/lint.sh
```

Or use [pre-commit](https://pre-commit.com/):

```bash
pip install pre-commit
pre-commit install
```

## CI/CD Integration

Add to your CI/CD pipeline:

```yaml
# GitHub Actions example
- name: Lint codebase
  run: ./scripts/lint.sh
```

## Common Issues and Fixes

### Python: Bare except clause

**Issue:**
```python
except:
    pass
```

**Fix:**
```python
except Exception:
    pass
```

### JavaScript: Missing dependency in useEffect

**Issue:**
```javascript
useEffect(() => {
  fetchData()
}, [])  // Missing fetchData dependency
```

**Fix:**
```javascript
useEffect(() => {
  fetchData()
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, [])  // Intentionally empty
```

### Terraform: Formatting issues

**Fix:**
```bash
tofu fmt -recursive infrastructure/
```

## Linting Rules

### Python
- Max line length: 120 characters
- Follow PEP 8 style guide
- No bare except clauses
- Type hints encouraged

### JavaScript
- Max line length: 120 characters
- React Hooks rules enforced
- No console.log in production
- Unused variables warned

### Terraform
- Consistent formatting
- Proper indentation
- No trailing whitespace

## Suppressing Warnings

### Python

```python
# ruff: noqa: E501  # Ignore line too long
# pylint: disable=too-many-arguments
```

### JavaScript

```javascript
// eslint-disable-next-line no-console
console.log('Debug message')

/* eslint-disable react-hooks/exhaustive-deps */
useEffect(() => {
  // ...
}, [])
```

## Best Practices

1. **Run linting before commits**
2. **Fix warnings, not just errors**
3. **Use auto-formatting tools** (black, prettier)
4. **Keep linting configs in version control**
5. **Update dependencies regularly**

## Troubleshooting

### Linter not found

Install missing tools:
```bash
# Python
pip install ruff flake8 black

# JavaScript
cd ui && npm install

# Terraform
# OpenTofu includes fmt, or install tflint
```

### False positives

Update configuration files or add suppressions:
- Python: Add to `.flake8` or `pyproject.toml`
- JavaScript: Update `.eslintrc.js`
- Terraform: Update `.tflint.hcl`

### Slow linting

Use faster tools:
- Python: Use `ruff` instead of `pylint`
- JavaScript: ESLint is already fast
- Run linting in parallel if possible

## Summary

- ✅ Run `./scripts/lint.sh` before deployment
- ✅ Fix all errors before committing
- ✅ Use auto-formatters (black, tofu fmt)
- ✅ Keep linting configs updated
- ✅ Integrate into CI/CD pipeline


