# CI and delivery boundary

The root Jenkinsfile loads the validation-only pipeline in
`ci/pipelines/checks.groovy`. Existing Docker-capable `vpn-agent2` is selected;
no credential IDs or live jobs are introduced. GitHub Actions uses an owned
PostgreSQL 15 service for reporting/authentication tests and builds the root
Dockerfile independently. Both paths preserve nonzero exits and JUnit results.

Run `bash ci/run-isolated.sh` for the full isolated local equivalent. See
[ci/README.md](../ci/README.md) for commands, artifact handling and cleanup.
The no-skip gate fails a run that omits its database tests. Source and test
syntax, pinned dependency consistency, Ruff and formatting are also checked.
Auth tests validate asymmetric tokens, issuer/audience/expiry, service roles,
failed discovery and key rotation; authorized chart queries use PostgreSQL.

This repository does not publish images or deploy. The owning registry pipeline
still builds the API from the unchanged root Dockerfile and owns image/source
provenance, managed secrets, reporting views, Helm and live acceptance. A local
suite or Docker build is not a deployment or live reporting compatibility proof.
No OpenG2P source/framework changes are involved.
