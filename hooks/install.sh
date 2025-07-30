#!/bin/bash
# Install all Git hooks for the bibliography repository
# This script ensures comprehensive quality enforcement

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
GIT_HOOKS_DIR="${REPO_ROOT}/.git/hooks"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

error() {
    echo -e "${RED}ERROR: $1${NC}" >&2
    exit 1
}

warning() {
    echo -e "${YELLOW}WARNING: $1${NC}" >&2
}

success() {
    echo -e "${GREEN}✓ $1${NC}"
}

info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Ensure we're in a git repository
if [ ! -d "${GIT_HOOKS_DIR}" ]; then
    error "Not in a git repository or .git/hooks directory not found"
fi

# List of hooks to install
HOOKS=(
    "pre-commit"
    "commit-msg"
    "pre-push"
    "prepare-commit-msg"
    "post-commit"
)

echo "====================================="
echo "📋 Installing Git Hooks"
echo "====================================="
echo

# Backup existing hooks
backup_existing_hooks() {
    local hook_name="$1"
    local hook_path="${GIT_HOOKS_DIR}/${hook_name}"
    
    if [ -f "${hook_path}" ]; then
        local backup_path="${hook_path}.backup.$(date +%Y%m%d_%H%M%S)"
        mv "${hook_path}" "${backup_path}"
        warning "Existing ${hook_name} hook backed up to: $(basename "${backup_path}")"
    fi
}

# Install hook
install_hook() {
    local hook_name="$1"
    local source_path="${SCRIPT_DIR}/${hook_name}"
    local dest_path="${GIT_HOOKS_DIR}/${hook_name}"
    
    if [ ! -f "${source_path}" ]; then
        error "Hook file not found: ${source_path}"
    fi
    
    # Backup existing hook
    backup_existing_hooks "${hook_name}"
    
    # Copy hook
    cp "${source_path}" "${dest_path}"
    chmod +x "${dest_path}"
    
    success "Installed ${hook_name} hook"
}

# Install all hooks
info "Installing hooks..."
for hook in "${HOOKS[@]}"; do
    install_hook "${hook}"
done

echo
echo "====================================="
echo "📚 Hook Descriptions"
echo "====================================="
echo
echo "• pre-commit: Enforces code quality, linting, type checking, and validation"
echo "  - Checks Python code with ruff and pyright"
echo "  - Validates all BibTeX entries"
echo "  - Scans for secrets and common issues"
echo "  - Ensures proper file permissions"
echo
echo "• commit-msg: Enforces conventional commit format"
echo "  - Format: type(scope): description"
echo "  - Prevents WIP and temporary commits"
echo "  - Ensures meaningful commit messages"
echo
echo "• pre-push: Final validation before pushing"
echo "  - Runs full test suite"
echo "  - Verifies bibliography integrity"
echo "  - Checks documentation and changelog"
echo "  - Security scan"
echo
echo "• prepare-commit-msg: Helps with commit message creation"
echo "  - Adds commit template"
echo "  - Suggests scope based on changes"
echo "  - Adds issue references from branch names"
echo
echo "• post-commit: Maintenance and notifications"
echo "  - Updates statistics"
echo "  - Provides follow-up reminders"
echo "  - Checks repository health"

echo
echo "====================================="
echo "🔧 Configuration"
echo "====================================="
echo
echo "To temporarily bypass hooks (emergency only):"
echo "  • Skip pre-commit: git commit --no-verify"
echo "  • Skip pre-push: SKIP_PRE_PUSH=1 git push"
echo
echo "To uninstall hooks:"
echo "  • Remove individual: rm .git/hooks/HOOK_NAME"
echo "  • Remove all: rm .git/hooks/{pre-commit,commit-msg,pre-push,prepare-commit-msg,post-commit}"
echo
echo "To update hooks:"
echo "  • Run this script again: ./hooks/install.sh"

# Check environment
echo
echo "====================================="
echo "🔍 Environment Check"
echo "====================================="
echo

# Check for required tools
check_tool() {
    local tool="$1"
    if command -v "$tool" &> /dev/null; then
        success "$tool found"
    else
        warning "$tool not found - some hooks may not work properly"
    fi
}

info "Checking required tools..."
check_tool "python3"
check_tool "ruff"
check_tool "pyright"
check_tool "git"

# Check for Guix
if [ -n "$GUIX_ENVIRONMENT" ]; then
    success "Running in Guix environment"
else
    warning "Not in Guix environment - run: guix shell -m manifest.scm"
fi

# Test hook
echo
echo "====================================="
echo "🧪 Testing Hooks"
echo "====================================="
echo

# Create a test commit message
test_commit_msg() {
    local test_file=$(mktemp)
    echo "test: this is a test commit message" > "$test_file"
    
    if "${GIT_HOOKS_DIR}/commit-msg" "$test_file" &> /dev/null; then
        success "commit-msg hook test passed"
    else
        warning "commit-msg hook test failed"
    fi
    
    rm -f "$test_file"
}

test_commit_msg

echo
echo "====================================="
success "All hooks installed successfully! 🎉"
echo "====================================="
echo
info "Your repository now enforces:"
echo "  ✓ Code quality standards"
echo "  ✓ Conventional commits"
echo "  ✓ Bibliography correctness"
echo "  ✓ Security best practices"
echo "  ✓ Documentation standards"
echo
info "Happy coding! 🚀"