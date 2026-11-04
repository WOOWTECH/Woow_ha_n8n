# AGENTS.md

Rules for every agent and person who changes this repository. The full
release mechanism is described in the Woow_HA_App_Store README (section
"版本策略與同步") and in ADR-0005 of the WOOW addon pipeline.

1. **``main`` only changes through a pull request.** A ruleset blocks direct
   pushes, force pushes and deleting the branch, and nobody can bypass it.
   Push a branch, open a PR, wait for the required checks, then merge.
2. **A PR that changes an addon version is a release.** Merging it publishes
   that version to the WOOW App Store. It must pass every required check; the
   checks are the approval, there is no human review step. Every PR runs
   `Upgrade comparison / compare` (pipeline #89); treat a failure as blocking.
   It compares each addon whose version the PR changes with the latest Stable
   Release. It also runs the upgrade test (pipeline #137): the Release's
   image, then this PR's amd64 image on the same data directories, under a
   mock Supervisor; the new version must start and keep its data (pipeline
   #138): the Store runs `n8n/upgrade-check/seed` on the Release, then
   `n8n/upgrade-check/verify` on this PR's image. Through n8n's own API
   (`n8n_upgrade.py`) seed writes the owner, an encrypted credential, an
   active webhook workflow with JavaScript and Python Code nodes, executions
   and a public API key; verify reads them back after the migrations. Every
   check is listed in the compare summary. Keep the hooks standard-library
   Python (they run in the Store's python:3.12-alpine mock Supervisor
   container), executable (`git update-index --chmod=+x`), and never
   `docker run` from them. A PR that changes no version passes it in seconds. The
   result is in the job summary. To re-run it, use "Re-run all jobs", not
   "Re-run failed jobs": a re-run judges its own build, and an earlier
   attempt's SBOM and image are not used.
3. **Breaking changes must be declared in `upgrade-notes.yaml`** next to the
   addon's `config.yaml` (here `n8n/upgrade-notes.yaml`). Create the file only
   when the upgrade comparison asks for it; copy `change` and `key` from its
   report and write the migration path. It also blocks a new fixable Critical
   or High vulnerability unless it is accepted with a reason. The release puts
   these entries on the GitHub Release. Rules, change names and the file
   format: the Woow_HA_App_Store README, section
   "升版比對與 `upgrade-notes.yaml`".
