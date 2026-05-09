---
name: git-workflow
description: Git workflow patterns including branching strategies, commit conventions, merge vs rebase, conflict resolution, and collaborative development best practices for teams of all sizes.
origin: ECC
---

# Git Workflow Patterns

Best practices for Git version control, branching strategies, and collaborative development.

## When to Activate

- Setting up Git workflow for a new project
- Deciding on branching strategy (GitFlow, trunk-based, GitHub flow)
- Writing commit messages and PR descriptions
- Resolving merge conflicts
- Managing releases and version tags
- Onboarding new team members to Git practices

## Branching Strategies

### GitHub Flow (Simple, Recommended for Most)

Best for continuous deployment and small-to-medium teams.

```
main (protected, always deployable)
  │
  ├── feature/user-auth      → PR → merge to main
  ├── feature/payment-flow   → PR → merge to main
  └── fix/login-bug          → PR → merge to main
```

**Rules:**
- `main` is always deployable
- Create feature branches from `main`
- Open Pull Request when ready for review
- After approval and CI passes, merge to `main`
- Deploy immediately after merge

### Trunk-Based Development (High-Velocity Teams)

Best for teams with strong CI/CD and feature flags.

```
main (trunk)
  │
  ├── short-lived feature (1-2 days max)
  ├── short-lived feature
  └── short-lived feature
```

**Rules:**
- Everyone commits to `main` or very short-lived branches
- Feature flags hide incomplete work
- CI must pass before merge
- Deploy multiple times per day

### GitFlow (Complex, Release-Cycle Driven)

Best for scheduled releases and enterprise projects.

```
main (production releases)
  │
  └── develop (integration branch)
        │
        ├── feature/user-auth
        ├── feature/payment
        │
        ├── release/1.0.0    → merge to main and develop
        │
        └── hotfix/critical  → merge to main and develop
```

**Rules:**
- `main` contains production-ready code only
- `develop` is the integration branch
- Feature branches from `develop`, merge back to `develop`
- Release branches from `develop`, merge to `main` and `develop`
- Hotfix branches from `main`, merge to both `main` and `develop`

### When to Use Which

| Strategy | Team Size | Release Cadence | Best For |
|----------|-----------|-----------------|----------|
| GitHub Flow | Any | Continuous | SaaS, web apps, startups |
| Trunk-Based | 5+ experienced | Multiple/day | High-velocity teams, feature flags |
| GitFlow | 10+ | Scheduled | Enterprise, regulated industries |

## Commit Messages

### Conventional Commits Format

```
<type>(<scope>): <subject>

[optional body]

[optional footer(s)]
```

### Types

| Type | Use For | Example |
|------|---------|---------|
| `feat` | New feature | `feat(auth): add OAuth2 login` |
| `fix` | Bug fix | `fix(api): handle null response in user endpoint` |
| `docs` | Documentation | `docs(readme): update installation instructions` |
| `style` | Formatting, no code change | `style: fix indentation in login component` |
| `refactor` | Code refactoring | `refactor(db): extract connection pool to module` |
| `test` | Adding/updating tests | `test(auth): add unit tests for token validation` |
| `chore` | Maintenance tasks | `chore(deps): update dependencies` |
| `perf` | Performance improvement | `perf(query): add index to users table` |
| `ci` | CI/CD changes | `ci: add PostgreSQL service to test workflow` |
| `revert` | Revert previous commit | `revert: revert "feat(auth): add OAuth2 login"` |

### Good vs Bad Examples

```
# BAD: Vague, no context
git commit -m "fixed stuff"
git commit -m "updates"
git commit -m "WIP"

# GOOD: Clear, specific, explains why
git commit -m "fix(police): retry requests on 503 Service Unavailable

The external API occasionally returns 503 errors during peak hours.
Added exponential backoff retry logic with max 3 attempts.

Closes #123"
```

## Merge vs Rebase

### Merge (Preserves History)

```bash
# Creates a merge commit
git checkout main
git merge feature/user-auth
```

Use when merging feature branches into `main`, or when multiple people worked on the branch.

### Rebase (Linear History)

```bash
# Rewrites feature commits onto target branch
git checkout feature/user-auth
git rebase main
```

Use when updating your local feature branch with latest `main`, and the branch is local-only.

**NEVER rebase** branches that are shared, already pushed, or are protected branches.

## Pull Request Workflow

### PR Description Template

```markdown
## What

Brief description of what this PR does.

## Why

Explain the motivation and context.

## How

Key implementation details worth highlighting.

## Testing

- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual testing performed

## Checklist

- [ ] Code follows project style guidelines
- [ ] Self-review completed
- [ ] No new warnings introduced
- [ ] Tests pass locally

Closes #123
```

## Conflict Resolution

```bash
# See conflicted files
git status

# After resolving, stage and commit
git add path/to/file
git commit
```

### Conflict Prevention

1. Keep feature branches small and short-lived
2. Rebase frequently onto main
3. Communicate about touching shared files
4. Review and merge PRs promptly

## Branch Naming

```
feature/user-authentication
feature/JIRA-123-payment-integration
fix/login-redirect-loop
hotfix/critical-security-patch
release/1.2.0
experiment/new-caching-strategy
```

## Branch Cleanup

```bash
# Delete local merged branches
git branch --merged main | grep -v "^\*\|main" | xargs -n 1 git branch -d

# Delete remote-tracking references for deleted remote branches
git fetch -p
```

## Release Management

### Semantic Versioning

```
MAJOR.MINOR.PATCH
MAJOR: Breaking changes
MINOR: New features, backward compatible
PATCH: Bug fixes, backward compatible
```

### Creating Releases

```bash
git tag -a v1.2.0 -m "Release v1.2.0"
git push origin v1.2.0
```

## Common Workflows

### Starting a New Feature

```bash
git checkout main && git pull origin main
git checkout -b feature/police-stuck-fix
git add src/...
git commit -m "fix(police): resolve terminal stuck deadlock at clearing position"
git push -u origin feature/police-stuck-fix
```

### Undoing Mistakes

```bash
git reset --soft HEAD~1      # Undo last commit, keep changes
git revert HEAD              # Safe undo for pushed commits
git checkout HEAD -- path/   # Restore specific file
```

## Anti-Patterns

```
# BAD: Vague commit messages
git commit -m "update"

# BAD: Committing directly to main without review

# BAD: Giant PRs (1000+ lines)
# GOOD: Break into smaller, focused PRs

# BAD: Rewriting public history
git push --force origin main
# GOOD: Use revert for public branches
```
