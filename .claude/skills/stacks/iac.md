---
name: iac
detect:
  files: ["**/*.tf", "**/*.tfvars", "**/*.hcl", "**/template.y*ml", "**/serverless.y*ml", "**/cdk.json", "**/Pulumi.*", "**/*.bicep", "**/k8s/**", "**/helm/**", "**/Chart.yaml", "**/kustomization.y*ml", "**/Dockerfile*", "**/docker-compose*.y*ml"]
evidence: NRD Sight corpus (≈200 findings on Terraform and CloudFormation); the Kubernetes and Docker entries are seeded from the same failure modes
---

# Infrastructure as code (Terraform, CloudFormation/SAM, CDK, Pulumi, Kubernetes, Docker)

## Build

- **Terraform:**
  - small, versioned modules;
  - pinned provider and module versions;
  - remote state with locking;
  - typed variables with `validation`;
  - no secrets in tfvars (read them from Secrets Manager or SSM data sources);
  - least-privilege IAM (specific actions and resources);
  - tags;
  - `prevent_destroy` on stateful resources.
- **CloudFormation, SAM, CDK, Serverless:** the same principles. Use explicit removal policies, and parameters per environment.
- **Functions and queues:**
  - the function timeout is below the queue visibility timeout;
  - a DLQ with an alarm;
  - reserved concurrency where needed;
  - retention that outlasts an outage.
- **Kubernetes and Helm:**
  - resource requests and limits;
  - liveness and readiness probes;
  - a non-root `securityContext`;
  - images pinned by digest;
  - secrets from an external secret store.
- **Docker:**
  - multi-stage builds;
  - pinned base images;
  - a non-root user;
  - no secrets in layers;
  - a `.dockerignore`.

## Review

### How the failure modes show up
- **FM-06 Budgets:**
  - the function timeout covers batch size × per-item latency at the rate limit;
  - the queue visibility timeout is longer than the function timeout;
  - concurrency is capped;
  - Kubernetes resource limits and probe timeouts fit real latency.
- **FM-08 Silent degradation:** alarms route to a real recipient and watch the metric that actually fails; dead-letter queues exist and are alarmed.
- **FM-10 Contract evolution:** renamed resources that force replacement or destroy state; message retention cut below the outage window. [critical for retention cuts]
- **FM-13 Authz / least privilege:**
  - no `*` actions or resources;
  - secret ARNs scoped, including the provider's random suffix;
  - no staging↔prod reach;
  - no `0.0.0.0/0` ingress;
  - narrowed rules still permit the calls the code makes;
  - public endpoints never run with admin DB credentials.
- **FM-14 Secrets:** no secrets in `.tf`, templates, function env vars or Dockerfiles. Use a secret store. A committed key gets rotated, not just deleted. [critical when live]
- **FM-15 Config:**
  - env and parameter names match what the code reads;
  - schedule expressions are valid (AWS `rate()` uses a plural unit for values above 1);
  - prod toggles fail loudly.
- **FM-16 Cost:** task CPU or memory raised with no stated reason; per-batch object writes; always-on capacity where on-demand fits.

### Stack-only checks
- **Remote state.** Remote state and locking are configured; no `terraform destroy` paths without a gate.
- **Pinning.** Pin providers, modules and base images to versions or digests, not `latest`.
- **Docker.** Run as non-root, use multi-stage builds without secrets in layers, and keep `.dockerignore` excluding env files.

## Test

- **Terraform:** `terraform fmt -check`, `terraform validate`, and tflint, checkov or tfsec when configured. Run `terraform plan` only in a sandbox or in CI; it is read-only. Never `apply`.
- **CDK, CloudFormation, Helm:**
  - CDK: `cdk synth` plus snapshot tests;
  - CloudFormation: `cfn-lint`;
  - Helm: `helm lint` and `helm template`, piped to kubeconform.

## Commands

- **lint:** `terraform fmt -check -recursive && terraform validate` (inferred), `tflint`, `cfn-lint`, `helm lint`.
- **plan and synth** are read-only but need credentials, so confirm before running them.
- **apply, deploy and destroy** are always unsafe.

## Entry points (scan mode)
- Root modules;
- IAM and policy documents;
- security groups and network rules;
- function, queue and schedule resources;
- secrets references;
- Kubernetes manifests and Helm values.
