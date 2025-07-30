# Git Hooks Documentation

This directory contains Git hooks that enforce quality standards and maintain the correctness invariant of the bibliography repository.

## Overview

The hooks system is designed to prevent non-compliant changes from entering the repository, even when working in fresh contexts or with partial knowledge of project requirements. These hooks enforce:

- **Code Quality**: Linting, formatting, type checking
- **Data Integrity**: BibTeX validation, file path verification
- **Commit Standards**: Conventional commits, meaningful messages
- **Security**: Secret scanning, permission checks
- **Documentation**: Changelog updates, README maintenance

## Installation

```bash
./hooks/install.sh
```

This will install all hooks and backup any existing ones.

## Hooks

### pre-commit

Runs before each commit to ensure code quality and data integrity.

**Checks:**
- Environment verification (Guix shell)
- Python code formatting (ruff)
- Python linting (ruff)
- Python type checking (pyright)
- BibTeX validation (all entries must be valid)
- Secret scanning
- File permissions
- Commit size warnings

**Bypass:** `git commit --no-verify` (emergency only)

### commit-msg

Validates commit message format according to conventional commits.

**Format:** `type(scope): description`

**Valid types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes
- `refactor`: Code refactoring
- `test`: Test changes
- `chore`: Maintenance tasks
- `perf`: Performance improvements
- `ci`: CI/CD changes
- `build`: Build system changes
- `revert`: Revert previous commit

**Rules:**
- First line max 72 characters
- Use imperative mood
- No capital after colon
- No period at end
- No WIP/temporary commits

### pre-push

Final validation before pushing to remote repository.

**Checks:**
- Branch protection warnings
- Full test suite execution
- Bibliography integrity verification
- Documentation completeness
- Changelog updates
- Code coverage (if available)
- Security scan
- Commit quality

**Bypass:** `SKIP_PRE_PUSH=1 git push` (emergency only)

### prepare-commit-msg

Helps create properly formatted commit messages.

**Features:**
- Adds commit template for empty messages
- Suggests scope based on changed files
- Extracts issue numbers from branch names
- Shows file change summary
- Reminds about changelog updates

### post-commit

Runs after successful commits for maintenance tasks.

**Features:**
- Updates repository statistics
- Provides follow-up reminders
- Checks repository health
- Backup reminders
- TODO/FIXME tracking

## Configuration

### Required Tools

All tools are provided via Guix:
```bash
guix shell -m manifest.scm
```

Required tools:
- `python3` with `bibtexparser` and `click`
- `ruff` for Python linting/formatting
- `pyright` for type checking
- `git` (obviously)

### Environment Variables

- `GUIX_ENVIRONMENT`: Required to be set (automatically in Guix shell)
- `SKIP_PRE_PUSH=1`: Skip pre-push validation (emergency only)

## Troubleshooting

### Hook Not Running

1. Check if hook is executable:
   ```bash
   ls -la .git/hooks/
   ```

2. Make executable if needed:
   ```bash
   chmod +x .git/hooks/HOOK_NAME
   ```

### Hook Failing

1. Run validation manually:
   ```bash
   python3 -m bibmgr.cli check all
   python3 -m bibmgr.cli report all
   ```

2. Check environment:
   ```bash
   echo $GUIX_ENVIRONMENT
   which ruff pyright python3
   ```

3. For detailed output, run git commands with verbose flag:
   ```bash
   GIT_TRACE=1 git commit
   ```

### Emergency Bypass

**Only use in genuine emergencies:**

- Skip pre-commit: `git commit --no-verify`
- Skip pre-push: `SKIP_PRE_PUSH=1 git push`
- Remove hook temporarily: `mv .git/hooks/HOOK_NAME .git/hooks/HOOK_NAME.disabled`

**Remember to fix issues and re-enable hooks immediately after.**

## Best Practices

1. **Always work in Guix shell**: `guix shell -m manifest.scm`
2. **Run checks before committing**: `python3 -m bibmgr.cli check all`
3. **Write meaningful commit messages**: Follow conventional format
4. **Keep commits focused**: One logical change per commit
5. **Update documentation**: Keep README and CHANGELOG current
6. **Fix issues immediately**: Don't accumulate technical debt

## Hook Development

When modifying hooks:

1. Test changes locally first
2. Update both the hook file and install.sh
3. Document new checks in this README
4. Consider backward compatibility
5. Add appropriate bypass mechanisms for emergencies

## Security Notes

The hooks perform basic security scanning but are not a replacement for comprehensive security practices:

- Never commit secrets, even temporarily
- Use environment variables for sensitive data
- Review diff before committing: `git diff --cached`
- Be cautious with generated files

## Maintenance

### Updating Hooks

```bash
# Edit hook files in hooks/
vim hooks/pre-commit

# Reinstall all hooks
./hooks/install.sh
```

### Viewing Hook Logs

```bash
# View statistics
cat .git/bibliography-stats.log

# View backups
ls -la .git/hooks/*.backup.*
```

### Uninstalling Hooks

```bash
# Remove all hooks
rm .git/hooks/{pre-commit,commit-msg,pre-push,prepare-commit-msg,post-commit}

# Remove specific hook
rm .git/hooks/HOOK_NAME
```

## Philosophy

These hooks embody the principle that **correctness is non-negotiable**. They ensure that:

1. Invalid data never enters the repository
2. Code quality standards are maintained
3. Documentation stays current
4. Security best practices are followed
5. Technical debt is minimized

The hooks are intentionally strict to prevent "vibe coding" sessions from introducing problems that would be difficult to fix later.

## Support

If hooks are blocking legitimate work:

1. First ensure you're in the correct environment
2. Read the specific error messages carefully
3. Run the suggested fix commands
4. If still blocked, check if it's a hook bug
5. Use emergency bypass only as last resort

Remember: The hooks are there to help maintain long-term repository health!