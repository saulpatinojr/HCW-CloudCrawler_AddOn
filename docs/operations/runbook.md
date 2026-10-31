# Operations runbook (lab edition)

This page holds the procedures this repository owns; the lab host that runs the container belongs to the website repository (see `infrastructure/README.md`), so there are two procedures so far: the base image
(next) and Dependabot's Python updates (the last section).

## Keeping the base image on the website's pin (`base-update`)

The lab image is built on a base image (the image a build starts from). The website decides which one, in its file
`lab-image/versions.env`. This repository keeps a copy of that choice in `infrastructure/docker/versions.env` and repeats
it on every `FROM` line (the line that names the starting image) of `infrastructure/docker/Dockerfile`. Once a day, at
07:37 UTC, the workflow [`base-update`](../../.github/workflows/base-update.yml) compares the two. When the website has
moved, it opens one pull request that changes `versions.env` and every `FROM` together. A person reviews and merges that
pull request; nothing is merged for you. On a normal day nothing happens: the run is green and prints `changed=false`.
Runs: <https://github.com/saulpatinojr/HCW-CloudCrawler_AddOn/actions/workflows/base-update.yml>. Open pull requests it
made: <https://github.com/saulpatinojr/HCW-CloudCrawler_AddOn/pulls?q=is%3Apr+is%3Aopen+head%3Abase-update%2Fwebsite-base>.
Until the proof at the end of this section has been run once and recorded in `VALIDATION.md`, this section describes what
the workflow is built to do, not what has been seen happening.

**When the pull request appears.** Wait for its checks (the `image` check builds the image on the new base), then merge it.
Success looks like this: the next run of the `base-follows-website` job in `security.yml` on `main` is green.

**If you need to change the pull request.** A commit you push to the branch `base-update/website-base` is kept: while the
branch already holds the website's pin, the daily run leaves the pull request alone. If the website moves again, the branch
is rebuilt from `main` and your commit is replaced. For a change that has to last, close the pull request and make the
change on your own branch. If the website moves back (or someone moves `main` to the website's pin by hand) while a pull
request is open, the next run closes it as no longer needed.

**When the run is red.** Open the failed step's log and look for a line that starts with `::error::`. The refusals in
the table below print one; a network failure while the website's file is being read may print only the tool's own message,
so read the log even when there is no such line. Do not rely on the weekly
`base-follows-website` job to show it: that job compares only the image and its digest (`BASE_IMAGE` and `BASE_DIGEST`), not
the Python version. It usually goes red as well when the website moves, but if the website changes only
`BASE_PYTHON_VERSION` to another minor line (for example 3.14 to 3.15), `base-update` refuses and goes red while the weekly
job stays green. So watch for failed `base-update` runs on their own (GitHub can notify the person who last changed the
workflow's `cron` line, as their notification settings allow, so do not count on an email; the Actions tab lists every run). What the run left behind depends on where it stopped:

- If the red step is in the first job, `plan`, or is the step called "Apply the move" in the second, nothing was pushed and
  no pull request was opened: those steps only read and edit files on the runner.
- If the red step is a later step of the second job (the token, the commit identity or "Open the pull request"), the branch
  `base-update/website-base` may already have been pushed without its pull request. Look before you act. Success: the first
  command lists the pull requests of that branch (open or closed; nothing is fine), and the second prints
  `refs/heads/base-update/website-base` when the branch exists. A branch without a pull request does no harm: the next
  successful run reuses it and opens the pull request.

  ```powershell
  gh pr list -R saulpatinojr/HCW-CloudCrawler_AddOn --head base-update/website-base --state all
  ```

  ```powershell
  gh api "repos/saulpatinojr/HCW-CloudCrawler_AddOn/git/matching-refs/heads/base-update/website-base" --jq ".[].ref"
  ```

| The `::error::` line says | What it means | What to do |
|---|---|---|
| `the website's base image is X, not Y` | The website switched to a different image repository. | A decision for a person: change `versions.env` and the `FROM` lines by hand if the new image is wanted here. |
| `the website moved Python from 3.14 to 3.15` | The website moved to a new Python minor line. The Dockerfile, `pyproject.toml` and `ci.yml` name the line (`python3.14`, `requires-python`, `PYTHON_VERSION`). | A decision for a person: adopt the new line by hand in one pull request, or wait. |
| `Dockerfile line N: FROM ... is neither an earlier stage nor ...` or `still carries` | The Dockerfile has a `FROM` (or another line) the script cannot move. | Fix the Dockerfile so every `FROM` that is not an earlier stage is exactly `BASE_IMAGE@BASE_DIGEST`, or move the pin by hand. |
| `expected exactly one BASE_... line`, `is not an image reference` or `is not sha256:` | A `versions.env` (the website's or this one) is malformed or repeats a key. | Read the file named in the message. If it is the website's file, tell the website's owner; do not edit this repository to match it. |
| `the registry did not show ...` | The digest does not exist, or Docker Hub did not answer. | Run it again later: `gh workflow run base-update.yml --ref main`. If it keeps failing, the website's digest is wrong: tell the website's owner. |
| `... lacks platforms that ... has` | The website's new digest dropped a platform the old one had (for example `linux/arm64`). | A decision for a person; do not merge anything until it is settled. |

**If the daily run goes quiet.** GitHub switches off scheduled workflows in a public repository after 60 days without
repository activity (a push, a merged pull request and the like count as activity). That would switch off `base-update` and
the weekly `base-follows-website` job in `security.yml` together, so in that one case the weekly job is not an independent
second check. To look, list the workflows and their state. Success: every row says `active`; a workflow GitHub has switched
off says `disabled_inactivity`. To switch the two back on, run the second command (it does no harm to a workflow that is
already on); success is that it prints a line saying the workflow was enabled.

```powershell
gh workflow list -R saulpatinojr/HCW-CloudCrawler_AddOn --all --json name,state,path | ConvertFrom-Json | Where-Object { $_.path -like ".github/workflows/*" } | Select-Object state, path | Format-Table -AutoSize
```

```powershell
gh workflow enable base-update.yml -R saulpatinojr/HCW-CloudCrawler_AddOn; gh workflow enable security.yml -R saulpatinojr/HCW-CloudCrawler_AddOn
```

**Proving it (run this once after the workflow first reaches `main`, and again after any change to `base-update.yml`).** It
uses a throwaway branch, so `main` is never touched. The commands are PowerShell. The previous digest used below is the one
this repository pinned before 2026-10-26 (`git log -p -- infrastructure/docker/versions.env`); it is still in the registry.

**Read this before you start.** The workflow's pull request asks the repository owner for a review (`CODEOWNERS` names the
owner for every path), so a proof pull request looks exactly like a real one and is easy to merge by mistake. It happened
twice when the same workflow was first proved, in the Cloud Assessor add-on on 2026-10-27
([its record](https://github.com/saulpatinojr/HCW-CloudAssessor_AddOn/pull/59)): the owner's account merged the proof's pull
request into the throwaway branch about ten minutes after it opened, which is about when its checks finish, and the step
that needed it could no longer be done.
Nothing on `main` was affected, because the proof's pull requests go into the throwaway branch. To avoid it, do steps 5 to
11 in one sitting without pausing (they take about two minutes of waiting), and do not wait for the checks in step 8. If a
push in step 11 is refused because the proof's pull request was merged, reset the throwaway folder and begin again at
step 3: `git -C $wt fetch origin; git -C $wt reset --hard origin/proof/base-update`. Step 10 can be left out of a repeat.

1. Use one PowerShell window for every step (later steps use the variables set here). Set the names and a helper that starts
   the workflow on the throwaway branch and waits for the new run. Success: no output.

   ```powershell
   $repo = "saulpatinojr/HCW-CloudCrawler_AddOn"; $clone = "C:\Users\saulp\Workspace\HCW-CloudCrawler_AddOn"; $wt = "C:\Users\saulp\Workspace\HCW-wt-ccproof"
   ```

   ```powershell
   function Start-BaseUpdate { $before = gh run list -R $repo --workflow base-update.yml --branch proof/base-update --limit 1 --json databaseId --jq ".[0].databaseId"; gh workflow run base-update.yml -R $repo --ref proof/base-update; if ($LASTEXITCODE -ne 0) { Write-Host "the workflow could not be started (is base-update.yml on main yet?)"; return }; $global:run = $null; for ($i = 0; $i -lt 40 -and (-not $global:run -or $global:run -eq $before); $i++) { Start-Sleep -Seconds 3; $global:run = gh run list -R $repo --workflow base-update.yml --branch proof/base-update --limit 1 --json databaseId --jq ".[0].databaseId" }; if (-not $global:run -or $global:run -eq $before) { Write-Host "no new run appeared within two minutes"; return }; gh run watch $global:run -R $repo --exit-status }
   ```

2. First make sure the proof cannot meet a real update. It reuses the branch `base-update/website-base`, which a real update
   (the website's pin differing from `main`'s) uses too, and step 11 puts the throwaway branch back to what `main` holds.
   So the proof is only safe when `main` already has the website's pin. In that case the daily run at 07:37 UTC changes
   nothing while the proof is going on (it also looks only at pull requests into `main`, and the proof's pull requests go
   into the throwaway branch). Two checks. Success: the first command prints `same: the website and main hold the same pin`
   and `lines read: 3 and 3`; the second prints nothing (or `no pull requests match`).
   If the first says `DIFFERENT`, stop: a real update is due. Let the daily run open the real pull request (or start it with
   `gh workflow run base-update.yml --ref main`), merge it, and begin again. If the second lists a pull request, stop: it
   is a real one.

   ```powershell
   $a = gh api "repos/saulpatinojr/HCW-HybridCloudWorks/contents/lab-image/versions.env" -H "Accept: application/vnd.github.raw+json" | Where-Object { $_ -match "^BASE_" }; $b = gh api "repos/$repo/contents/infrastructure/docker/versions.env?ref=main" -H "Accept: application/vnd.github.raw+json" | Where-Object { $_ -match "^BASE_" }; if (-not $a -or ($a -join "|") -ne ($b -join "|")) { "DIFFERENT: stop and read the note under this step" } else { "same: the website and main hold the same pin" }; "lines read: $(@($a).Count) and $(@($b).Count)"
   ```

   ```powershell
   gh pr list -R $repo --head base-update/website-base --state open
   ```

   Then make a throwaway branch in its own folder. Success: the command prints `HEAD is now at` and a commit of `main`.

   ```powershell
   git -C $clone fetch origin; git -C $clone worktree add $wt -b proof/base-update origin/main
   ```

3. Put the pin one release back, in `versions.env` and both `FROM` lines. Success: the second line shows 2 files changed.

   ```powershell
   foreach ($p in "infrastructure\docker\versions.env", "infrastructure\docker\Dockerfile") { $f = (Resolve-Path -LiteralPath (Join-Path $wt $p)).Path; $t = [System.IO.File]::ReadAllText($f); [System.IO.File]::WriteAllText($f, $t.Replace("sha256:fbecd461fc72d21b2143c6eaba25143738079154a6d0ea3da3aec724f50eed4a", "sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170")) }; git -C $wt diff --stat
   ```

   If the first digest is no longer the pin in `main`'s `versions.env`, nothing changes and `git diff --stat` prints nothing: read
   the `BASE_DIGEST` line of `versions.env` and use that value in place of the first digest.

4. Commit and push it. Success: the push prints `[new branch]  proof/base-update -> proof/base-update`.

   ```powershell
   git -C $wt -c user.email=34853639+saulpatinojr@users.noreply.github.com -c user.name="Saul Patino" commit -am "proof: base image one release back"; git -C $wt push -u origin proof/base-update
   ```

5. Run the workflow on that branch and wait for it. Success: it ends with both jobs green (`plan` and `open-pr`).

   ```powershell
   Start-BaseUpdate
   ```

   If it ends red, read the `::error::` line (table above) and stop; this is the proof failing, which is what it is for.

6. Read what the plan decided. Success: the lines show `changed=true`, `old=python:` with `a2b82f3c48559aa0`, `new=python:`
   with `fbecd461fc72d21b` (or the website's newer pin), and a list of platforms that includes `linux/386` and
   `linux/s390x`. (These patterns match only what the run printed, not the script text, so they cannot match by accident.)

   ```powershell
   gh run view $run -R $repo --log | Select-String "changed=true|old=python:|new=python:|linux/386|linux/s390x"
   ```

7. Find the pull request it opened. Success: exactly one pull request; its base is `proof/base-update`; its title is
   `CI: the base image follows the website's current digest (` and 12 characters and `)`; its author is `app/hcw-main-admin`;
   and the last line shows the ticked box `- [x] The new digest is an index` (an unticked `[ ]` means the registry could not
   show the old digest, which the plan log's warning would also say).

   ```powershell
   $pr = gh pr list -R $repo --head base-update/website-base --state open --json number --jq ".[0].number"; gh pr list -R $repo --head base-update/website-base --state open --json number,url,baseRefName,title,author; gh pr view $pr -R $repo --json body --jq .body | Select-String "\[.\] The new digest is an index"
   ```

8. See that its checks started. Success: the list shows `lint`, `test`, `image`, `pip-audit` and `secret-scan`, pending or
   passing; they exist only because the pull request was opened with the App token. (`dependency-review` and CodeQL run
   only for pull requests into `main`, so they are not expected on the proof's pull request, which goes into the throwaway
   branch.) Do not wait for them to finish: that takes about ten minutes, which is when the pull request is most likely to be
   merged by mistake (see above). In the Cloud Assessor add-on's proof (the same workflow, run there first) they all finished
   green. Also note whether the pull request says it needs an extra approval.

   ```powershell
   gh pr checks $pr -R $repo
   ```

9. Check the commit is credited to the App's bot user. Success: a line that names `hcw-main-admin` (GitHub may print it with
   or without `[bot]` after it).

   ```powershell
   gh pr view $pr -R $repo --json commits --jq ".commits[].authors[].login"
   ```

10. Check that a person's commit on the pull request branch survives a second run. Success: the run is green; a line shows
    `left alone` (matched on the run's own notice, not on the script text); the job list shows `open-pr: skipped`; the last
    line printed is the commit you pushed. (An empty commit proves the guard; it does not prove what happens to a changed file.)

    ```powershell
    git -C $wt fetch origin base-update/website-base; git -C $wt switch -c proof/person-fix origin/base-update/website-base; git -C $wt -c user.email=34853639+saulpatinojr@users.noreply.github.com -c user.name="Saul Patino" commit --allow-empty -m "proof: a fix a person pushed"; git -C $wt push origin HEAD:base-update/website-base; Start-BaseUpdate; gh run view $run -R $repo --log | Select-String "##\[notice\].*left alone"; (gh run view $run -R $repo --json jobs | ConvertFrom-Json).jobs | ForEach-Object { "$($_.name): $($_.conclusion)" }; git -C $wt fetch origin; git -C $wt log origin/base-update/website-base -1 --format=%s
    ```

11. Check that a pull request that has become unnecessary is closed. Move the throwaway branch to the website's pin (undoing
    the commit of step 4 does that, because step 2 checked that `main` holds the website's pin) and run again. Success: the run is green; a line shows `obsolete`; the job list shows `open-pr: success`; the last line prints
    `CLOSED`. The workflow closes it by deleting the branch `base-update/website-base`. If the last line prints `OPEN` or
    `MERGED`, the proof has found a fault: record it and do not clean up before reading the `open-pr` log.

    ```powershell
    git -C $wt switch proof/base-update; git -C $wt -c user.email=34853639+saulpatinojr@users.noreply.github.com -c user.name="Saul Patino" revert --no-edit HEAD; git -C $wt push origin proof/base-update; Start-BaseUpdate; gh run view $run -R $repo --log | Select-String "##\[notice\].*obsolete"; (gh run view $run -R $repo --json jobs | ConvertFrom-Json).jobs | ForEach-Object { "$($_.name): $($_.conclusion)" }; gh pr view $pr -R $repo --json state --jq ".state"
    ```

12. Clean up. This deletes only what the proof made: the branch `base-update/website-base` (step 11 may already have deleted it,
    and then the delete command answers that the reference does not exist, which is fine), the throwaway branch and its
    folder. First check that the branch has not become a real one since step 2 (for example because the website moved while
    you were working). Success: the first command prints nothing (or `no pull requests match`). If it lists a pull request
    into `main`, stop and do not delete the branch: it is a real pull request, and the proof must be cleaned up by hand around
    it. Success of the second command: it prints nothing (or `no pull requests match`), so no pull request is left open.

    ```powershell
    gh pr list -R $repo --head base-update/website-base --base main --state open
    ```

    ```powershell
    gh api -X DELETE "repos/$repo/git/refs/heads/base-update/website-base"; git -C $clone push origin --delete proof/base-update; git -C $clone worktree remove --force $wt; git -C $clone branch -D proof/base-update proof/person-fix; gh pr list -R $repo --head base-update/website-base --state open
    ```

Record the run links, the pull request link and what steps 7 to 11 showed in `VALIDATION.md`.

## Keeping Dependabot's Python updates working (the engine's static metadata)

Dependabot is GitHub's service that opens a pull request when a dependency has a newer version. Every Monday at 06:00 UTC
it looks at this repository (settings: [`dependabot.yml`](../../.github/dependabot.yml)). For Python it works through `uv`
(the tool that installs Python packages here). It edits `pyproject.toml` (the file that lists what the project needs), then
asks uv to rebuild `uv.lock` (the file that records the exact version and checksum of every package), once for each package
it wants to update. If that rebuild fails, that package gets no pull request; on 2026-10-27 it failed for all four packages
Dependabot tried (`ruff`, `fastapi`, `certifi`, `coverage`), so the job finished red and no Python pull request was opened. The job's runs are listed on the
repository's [Dependabot page](https://github.com/saulpatinojr/HCW-CloudCrawler_AddOn/network/updates).
Until a Dependabot run after this change has been seen green and recorded in `VALIDATION.md`, this section describes what the
change is built to do, not what has been seen happening.

**What went wrong (2026-10-26 and 2026-10-27, issue [33](https://github.com/saulpatinojr/HCW-CloudCrawler_AddOn/issues/33)).**
The engine (`cloud-crawler-core`, the detector library written in the App repository) is pinned by the address of its release
file, a wheel (the Python package file, ending `.whl`). The Python job then failed for every package it tried with
`private_source_authentication_failure`, which Dependabot's
[error list](https://docs.github.com/en/code-security/reference/supply-chain-security/troubleshoot-dependabot/dependabot-errors)
describes as "can't authenticate to a private package registry". That wording is misleading here: the App repository is
public. What the [log of the failed run](https://github.com/saulpatinojr/HCW-CloudCrawler_AddOn/actions/runs/40499840932)
shows, in order:

1. Dependabot runs `uv lock --upgrade-package <the package it wants to update>`.
2. uv needs the engine's metadata (its name, version and what it depends on) and, for a file at an address, its first
   request is a HEAD (a request that asks only for the file's headers, not the file;
   [uv issue 18998](https://github.com/astral-sh/uv/issues/18998) describes this habit).
3. GitHub answers the release address with a redirect (HTTP 302) to a short-lived signed download link on
   `objects.githubusercontent.com`.
4. The signed link answered uv's HEAD with `401` (HTTP's "not authorised"; the job log shows the 302 and then the 401,
   for every package it tried).
   Dependabot's uv code
   ([`lock_file_error_handler.rb`](https://github.com/dependabot/dependabot-core/blob/main/uv/lib/dependabot/uv/file_updater/lock_file_error_handler.rb),
   read on 2026-10-27) turns a uv error that mentions "authentication", "unauthorized", "forbidden" or an HTTP status of
   401 or 403 into `PrivateSourceAuthenticationFailure`, without checking that anything is private. The job log does not
   print uv's own error text, so that uv's message matched that pattern is inferred from the result.

Why the signed link refused the HEAD is also an inference (a link signed for downloading may not accept a HEAD). It was not
reproduced: from the machine used on 2026-10-27 GitHub redirected to a different host, `release-assets.githubusercontent.com`,
and that host answered both HEAD and GET with 200. A local run of the same uv version (0.13.5) did send the HEAD, so the
first half of the chain was seen on both sides. The fix does not depend on the reason for the 401.

**The fix.** `pyproject.toml` holds the engine's dependency list itself, in the entry `[[tool.uv.dependency-metadata]]`
([uv's description](https://docs.astral.sh/uv/concepts/resolution/)), copied from the wheel's own `METADATA` file (the
description file inside the wheel). With it, uv has nothing to ask the address. `uv.lock` records the entry in its
`[manifest]` block. The wheel's address and its sha256 in the lock are unchanged, so the image build still checks the
engine's checksum, and the image build's `uv export` output is byte-identical.

**Which uv versions this works for.** Measured on 2026-10-27 by locking from an empty cache and counting requests to the
engine's address (the entry is meant for packages that do not declare their metadata, so skipping the fetch is what uv
does today, not something its documentation promises):

| uv version | Requests to the engine's address before the change | With the entry |
|---|---|---|
| 0.13.5 (what Dependabot ran: the line `Package manager uv, Info : uv 0.13.5` in its job log) and 0.13.6 (the newest at the time) | a HEAD, then a GET | none |
| 0.12.0 and 0.11.32 (the version `ci.yml` pins) | one GET (a full download); never a HEAD | one GET |

So only the newer uv sends the HEAD, and the entry is what keeps it away from the address. CI's uv still downloads the
wheel, which is harmless. If Dependabot's image moves to a uv that behaves differently, the job could fail again; the log
line above tells you which uv it used.

Things that look like fixes and are not:

- **Telling Dependabot to ignore `cloud-crawler-core`.** The failures were raised while updating `ruff`, `fastapi`,
  `certifi` and `coverage`, not the engine: uv re-reads the engine's metadata whatever package is being updated. An
  `ignore` entry changes which pull requests Dependabot wants, not what uv does while it rebuilds the lock.
- **A `registries` entry in `dependabot.yml`.** That setting gives Dependabot a login for a private package index or
  private repository. The App repository is public, so there is nothing to log in to, and it would mean keeping a secret for
  no gain.
- **Pinning the engine with `git+https://`.** A git pin has no checksum, and the image build installs with
  `pip --require-hashes`, so it would break the build (the header of `core-update.yml` says the same).
- **Publishing the engine to a package index** would work but is a separate decision about where the engine is published.

**What you do when the engine moves.** Normally nothing. When the App tags a new release, `core-update.yml` opens a pull
request ([open ones](https://github.com/saulpatinojr/HCW-CloudCrawler_AddOn/pulls?q=is%3Apr+is%3Aopen+label%3Acore-update))
and moves the pin and the entry's `version` line (the one that ends in `# CORE_METADATA`) together, with
`scripts/bump_core_pin.py`. The run has two jobs: `bump` runs the tests against the new engine with no secret, and
`pull-request` checks `bump`'s files against ones it makes itself before it uses the App key. If `pull-request` stops with
"the bump artifact is refused", the two did not match: read that job's log and do not simply re-run it. The entry's
`requires-dist` list (what the engine depends on) and its `provides-extra` list (the optional extras the engine offers, none
today) are copies, so the test `test_static_metadata_matches_the_installed_wheel` compares them with the wheel that really
got installed, extras and all (`pydantic[email]` is not `pydantic`: the image installs the lock without resolving anything,
so an extra that is missing from the lock is missing from the image). Two more tests look at the new release:
`test_engine_requires_only_pydantic` fails for any dependency other than a plain `pydantic`, and
`test_wheel_accepts_every_python_the_project_allows` fails if the engine's `Requires-Python` refuses a Python version the
project's own `requires-python` allows. If one of them fails, the compatibility check in the workflow run goes red and the
pull request carries the label `needs-adaptation`. Then:

1. Print the new wheel's metadata. These are two PowerShell commands, run one after the other in the same window from any
   folder; the first downloads the latest release's wheel into a new temporary folder, the second reads it. The latest
   release is the one the pull request adopts unless the App has tagged another since, so check that the `Version:` line
   equals the version in the pull request's title. Success: the second prints lines starting `Name:`, `Version:`,
   `Requires-Python:` and `Requires-Dist:` (one `Requires-Dist:` line per dependency, and a `Provides-Extra:` line only if
   the engine gained extras).

   ```powershell
   $dir = Join-Path $env:TEMP ("engine-wheel-" + (Get-Date -Format "yyyyMMdd-HHmmss")); gh release download -R saulpatinojr/HCW-CloudCrawler_App --pattern "*.whl" --dir $dir
   ```

   ```powershell
   Add-Type -AssemblyName System.IO.Compression.FileSystem; $zip = [IO.Compression.ZipFile]::OpenRead((Get-ChildItem "$dir\*.whl").FullName); $entry = $zip.Entries | Where-Object { $_.FullName -like "*.dist-info/METADATA" }; (New-Object IO.StreamReader($entry.Open())).ReadToEnd() -split "`n" | Select-String "^(Name|Version|Requires-Python|Requires-Dist|Provides-Extra):"; $zip.Dispose()
   ```

2. Look at every `Requires-Dist:` line that is not a plain `pydantic`, and at every `Provides-Extra:` line. A new
   dependency, or an extra on `pydantic` (for example `pydantic[email]`, which brings in more packages), is new code in the
   image and needs a person's decision before the pull request is merged. Check it against the edition's rules: the
   "Never weaken" bullet in [`CLAUDE.md`](../../CLAUDE.md) (no cloud SDK and no way to build a cloud credential, proved by
   `tests/security/test_edition_boundary.py`; nothing that fetches evidence or opens connections), its licence, and whether
   it is maintained. `security.yml` audits the locked packages with `pip-audit`. If it is not acceptable, do not merge; tell
   the owner. If it is approved, change `test_engine_requires_only_pydantic` in `tests/security/test_engine_adoption.py`
   in the same pull request so that it allows exactly that dependency (it fails on purpose for anything else), and write
   who approved it in the pull request description.
3. On the pull request's branch, edit the entry `[[tool.uv.dependency-metadata]]` in `pyproject.toml` so that its
   `requires-dist` list says what step 1 printed on the `Requires-Dist:` lines (all of them, including any that end in
   `; extra == "..."`) and, if step 1 printed `Provides-Extra:` lines, set `provides-extra = ["name", ...]` to exactly
   those names (replace the old list; if step 1 printed no `Provides-Extra:` line, remove the `provides-extra` field, or
   the tests will find a stale one). Python writes the same range in a different order (`pydantic<3,>=2.14` and `pydantic>=2.14,<3` are the same
   range), and the test accepts either order, but not a missing extra or a different spelling of the requirement. Leave
   `requires-python` out of the entry: Dependabot copies the first `requires-python` in `uv.lock` over every other one, so a
   different range there would break the lock of its pull requests (`test_static_metadata_does_not_set_requires_python`
   holds this).
4. Compare the `Requires-Python:` line from step 1 with the project's own `requires-python` in `pyproject.toml`
   (`>=3.14.6,<3.15` today). The test `test_wheel_accepts_every_python_the_project_allows` tries every version from 3.0.0
   to 3.40.99 that the project range allows and fails if the engine refuses any of them. If it fails, a person decides:
   either raise the project's `requires-python` to what the engine accepts (and change every place that names a Python
   version: `.python-version`, the Python in `infrastructure/docker/Dockerfile`, `PYTHON_VERSION` in `ci.yml`, and the
   `python-version: "3.14"` lines in `.github/workflows/core-update.yml` and `.github/workflows/security.yml`; search
   for `python-version` and `3.14` to catch any added later), or do not adopt that release.
5. Rebuild the lock with the uv version `ci.yml` names in `UV_VERSION` (0.11.32 today; use the number that file shows). It
   runs `uv` from a temporary environment, in the folder of the pull request's branch, and prints `Resolved` and a package
   count when it worked. Then push the change.

   ```powershell
   uvx uv@0.11.32 lock
   ```

   Success: the pull request's `lint` and `test` checks go green, including `test_static_metadata_matches_the_installed_wheel`.

**How to check that Dependabot is healthy.** Success is a run called `uv in /. - Update` with the result `success`. This
PowerShell command lists the latest runs (the outer brackets matter in Windows PowerShell 5.1, which otherwise prints
empty values). A failed run of the old kind has `private_source_authentication_failure` in its log, naming the engine's
release address.

```powershell
(gh run list -R saulpatinojr/HCW-CloudCrawler_AddOn --workflow "Dependabot Updates" --limit 6 --json displayTitle,conclusion,createdAt,url | ConvertFrom-Json) | Select-Object createdAt, conclusion, displayTitle, url | Format-List
```

To make Dependabot look now instead of waiting for Monday, open the
[Dependabot page](https://github.com/saulpatinojr/HCW-CloudCrawler_AddOn/network/updates), find the row for the `uv`
manifest (`/pyproject.toml`) and click **Check for updates**
([GitHub's steps](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/manage-your-dependency-security/re-run-dependabot-jobs);
the page needs a sign-in, so its exact layout was not checked when this was written).
Success: a new `uv in /. - Update` run appears and ends in `success`, and pull requests for the outdated packages open
(at the time of writing: `fastapi`, `certifi`, `coverage` and the `dev` group). If the run is red again and still names
the engine's release address, open its log and look for two things. First, the line `Package manager uv, Info : uv ...`:
the table above says which uv versions were measured. Second, a line such as
`HEAD https://github.com:443/saulpatinojr/HCW-CloudCrawler_App/releases/download/...`: it means uv is still asking the
address, usually because the entry's `version` is not the pinned wheel's version (the test
`test_static_metadata_carries_the_marker_core_update_moves` and `uv lock --check` in `ci.yml` should have said so).

**When another engine is adopted the same way.** The Cloud Assessor and Network Eyes add-ons keep their engines inside the
repository today, so their Dependabot jobs pass. The day one of them pins its engine's release file by address, this same
failure will start there. Copy the entry, the `CORE_METADATA` marker, the `core-update.yml` line and the tests, not a
workaround.
