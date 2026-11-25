---
name: ci-cd
detect:
  files: [".github/workflows/**", ".gitlab-ci.yml", "bitbucket-pipelines.yml", "Jenkinsfile", ".circleci/**", "azure-pipelines.yml", "**/deploy*.sh", "**/buildspec*.yml", "**/Makefile"]
evidence: NRD Sight corpus (≈60 findings on GitHub Actions, Bitbucket and deploy scripts)
---

# CI/CD pipelines and deploy scripts

## Build

- **Permissions:**
  - pin third-party actions to a commit SHA;
  - minimal workflow `permissions:`;
  - OIDC instead of long-lived keys;
  - secrets from the secret store, masked in logs.
- **Deploy jobs:**
  - protected branches or environments with required reviewers;
  - plan before apply;
  - a health check and a rollback step.
- **Build hygiene:**
  - caches keyed on the lockfile hash;
  - a matrix covering the versions the project supports;
  - test and lint fail the pipeline (no `continue-on-error` on gates);
  - path filters that include every build input;
  - reusable workflows for shared steps.

## Review

### How the failure modes show up
- **FM-13 Authz:**
  - deploy to prod, and run `apply`/`destroy`, only from protected branches, with plan, approval and a health gate;
  - manual or tag-triggered runs must not deploy arbitrary branches to prod;
  - an ungated prod destroy is critical.
- **FM-14 Secrets:**
  - credentials never echoed into job logs (`set -x`, `env`, `printenv`);
  - secrets passed through the secret store, not inline env;
  - third-party actions pinned to a commit SHA.
- **FM-15 Config:**
  - change-detection hashes cover every build input (manifests, lockfiles, env files);
  - newly added checks actually run (job wiring, path filters);
  - the environment matrix doesn't cross staging and prod.
- **FM-18 Verification:** test and lint jobs fail the pipeline; no `continue-on-error`/`|| true` on gates.

### Stack-only checks
- **Least privilege.** Use OIDC or short-lived credentials instead of long-lived keys, and keep workflow `permissions:` minimal.
- **Caches.** Cache keys include the lockfile hash, so a stale cache can't mask a dependency change.

## Test

- **Static checks:** actionlint and yamllint, when available.
- **Dry runs:** run workflows on a branch or PR with deploy disabled, or use `act` locally if the repo does.
- **Prove new checks run:** a new check must appear in the PR's checks, and must fail on a deliberately broken commit.

## Commands

- **lint:** `actionlint` (inferred).
- **Deploy scripts** (`deploy*.sh`, release scripts) are unsafe. Never run them locally without confirmation.

## Entry points (scan mode)
- Workflow files;
- reusable workflows and composite actions;
- deploy scripts;
- release tagging.
