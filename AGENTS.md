## Command Output

Protect context usage. Any command with unknown or potentially large output must be byte-capped.

Default pattern:

```powershell
COMMAND 2>&1 | Select-Object -First 200
```

Prefer `rg` / `rtk rg` for searches and keep outputs capped.

## RTK Command Proxy

Prefer running shell commands through RTK whenever practical:

```powershell
rtk <command>
```

Use direct PowerShell only when RTK would interfere with shell builtins, output caps, quoting, privileged installs, or precise environment setup.

## Git / Commit Scope

Do not include planning, discussion, or design documents in commits by default, especially files under `docs/`, unless the user explicitly asks to commit documentation.

When committing current work, include source, tests, config, and ignore-rule changes needed for the implementation, but leave local notes and proposal documents untracked/ignored unless requested.

## Live Workflow / XHS Safety

Do not run live Xiaohongshu/XHS collector flows, browser profile flows, or end-to-end workflow commands that may touch XHS, LangSmith, remote LLMs, proxies, or other network services unless the user explicitly asks for that exact live run.

Avoid commands such as:

```powershell
python -m app.cli ...
pipenv run xhs-smoke
python -m app.collectors.xiaohongshu_minimal ...
```

For verification, prefer unit tests, mocked tests, dry-run style checks, or direct tests of the changed function. If a live workflow is necessary, ask first and mention the external service/proxy risk.
