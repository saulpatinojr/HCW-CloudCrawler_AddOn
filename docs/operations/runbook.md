# Operations runbook (lab edition)

This page holds the procedures this repository owns; the lab host that runs the container belongs to the website repository (see `infrastructure/README.md`), so there is one procedure so far.

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
