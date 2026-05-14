# Tunnelgraf 2.0 — Rewrite Plan

## Context

Tunnelgraf today is a Python CLI that builds nested SSH tunnels through
bastion hosts from a YAML profile, exposes remote endpoints as local ports,
optionally rewrites `/etc/hosts`, and layers on `connect / show / urls /
command / shell / scp / stop`. It uses `sshtunnel` + `paramiko`, a thread
per tunnel, a singleton hosts manager, and shells out to `scp` + `sshpass`
for transfers.

The goal of 2.0 is a ground-up rewrite that keeps the YAML profile format
(so existing users migrate transparently), fixes structural problems in the
current design, and adds the features users have been working around.

## Problems with 1.x

Structural:

- `paramiko.AutoAddPolicy` — no host-key verification anywhere in the
  codebase (`run_remote.py`, `tunnel_builder.py`). Undermines the
  project's "securely share connection schemes" pitch.
- `sshpass -p <password>` is composed into argv for SCP
  (`transfer.py:166,177`). Any local `ps` reveals the password.
- `cmd.split()` on a shell string built by concatenation
  (`transfer.py:197`) — breaks on paths with spaces, quotes, or globs.
- `os.fork()` + syslog redirection for `--detach`, then `psutil`
  process-table scraping in `stop` (`__init__.py:71,217`). Unix-only,
  fragile, and fights cron/systemd.
- Raw-TTY "press q to quit" loop running alongside a SIGINT handler and
  blocking thread joins (`tunnels.py:92`). Poor behaviour under
  non-interactive stdin (cron, CI, systemd).
- `~/.ssh/config` is parsed but only a handful of keys consumed. No
  `ProxyJump`, no `Match`, no `ControlMaster` — so users who've already
  solved their hop graph in ssh config can't reuse it.
- LastPass is the only secrets backend. The company's trajectory plus
  the growing 1Password/Vault/Bitwarden share of the market means this
  is a hard sell to new users.
- Distribution is pip/pipx. The README itself warns about dependency
  conflicts and tells users to `pipx install` as a workaround — a sign
  Python packaging is hurting adoption.

Smaller smells:

- `HostsManager` is a singleton but mutable state lives on instances.
- `TunnelDefinition.__init__` does I/O (reads `~/.ssh/config`, calls
  LastPass) during model construction — every recursion re-parses ssh
  config.
- `TunnelCount` is a hidden global.
- `validate()` shadows Pydantic's own method.
- Subprocess stdout is printed line-by-line without timeout handling
  (`transfer.py:206`) — a hung SCP hangs tunnelgraf.

## Language choice: Go

Go is the right target language. Reasons, strongest first:

1. **Distribution.** Single static binary → Homebrew, scoop,
   `curl | sh`, `FROM scratch` Docker. Kills the pip-conflict problem
   the README currently apologises for.
2. **SSH ecosystem maturity.** `golang.org/x/crypto/ssh` is first-class
   and battle-tested (Teleport, Gitea, Drone).
   `kevinburke/ssh_config` parses OpenSSH config with full semantics
   including `ProxyJump`. `pkg/sftp` and `bramvdbogaerde/go-scp` give
   in-process transfers — no shelling out to `scp`/`sshpass`, no
   password-in-argv leak, works on Windows.
3. **Concurrency model fit.** Goroutines + channels +
   `context.Context` map naturally onto "a tree of tunnels with
   independent lifecycles, cancellation, and reconnect loops." Replaces
   the current Thread + signal handler + singleton + raw-TTY polling
   mix.
4. **TUI.** Bubble Tea is mature and replaces the `\r`-overwritten
   status line with a real dashboard.
5. **Cross-platform daemon story.** `kardianos/service` or generated
   systemd/launchd units — no `os.fork` + syslog hacks.

Rejected alternatives:

- **Rust.** Defensible (russh / tokio) but brings nothing decisive for
  this workload and has a thinner SSH ecosystem. Slower iteration.
- **Node/TypeScript.** Wrong class of tool; SSH libraries are
  wrappers, and we'd reintroduce a runtime dependency.
- **Stay on Python.** Only if the cost of a rewrite outweighs the
  distribution and structural wins — which it doesn't, given the size
  of the codebase (~1.4k LOC).

## Architecture sketch

```
cmd/tunnelgraf/          cobra entrypoints (one file per verb)
internal/profile/        YAML load, include/overlay, JSON Schema, validate
internal/ssh/            client wrapper, known_hosts, keyring, agent
internal/tunnel/         Node, Graph, Manager, reconnect loop
internal/transfer/       SFTP + SCP implementations
internal/secrets/        pluggable backends (lastpass, 1password, vault,
                         keychain, libsecret, env, aws/gcp/azure sm)
internal/hosts/          /etc/hosts segment rewriter (hostctl-style)
internal/tui/            Bubble Tea dashboard
internal/status/         JSON + Prometheus HTTP endpoint
internal/daemon/         service install / pidfile / IPC
```

Core types (rough):

```go
type Profile struct { Root *Node; Includes []string; /* ... */ }

type Node struct {
    ID              string
    Host, User      string
    Port            int
    Auth            AuthRef       // points into secrets backend
    LocalBind       BindSpec      // port, address, "auto"
    HostsEntries    []string
    Children        []*Node       // was "nexthops"; single-child is
                                  // Children with len==1
    // ...
}

type Manager struct {
    graph   *Node
    ssh     *ssh.Registry        // multiplexed clients
    tunnels map[string]*tunnel   // by node ID
    events  chan Event           // status stream for TUI/HTTP
}
```

SSH connections are multiplexed: one `*ssh.Client` per bastion, shared
by all children. Each tunnel runs in its own goroutine under a context
derived from the manager's root context; reconnect is a loop with
exponential backoff inside that goroutine.

## Feature additions

Ordered roughly by user impact. This is the target surface area for
2.0 — not every item ships in the first release (see milestones).

1. **TUI dashboard.** Tree view of tunnels with status, bytes
   through, latency, reconnect count. Keys: retry hop, open shell on
   leaf, copy URL, filter.
2. **`tunnelgraf graph`.** DOT/Mermaid output of the tunnel tree.
   The product is called tunnel-*graph* and ships no graph.
3. **Pluggable secrets backends.** 1Password, Bitwarden, Vault,
   AWS/GCP/Azure Secrets Manager, macOS Keychain, libsecret, env.
   LastPass remains as one driver.
4. **Host-key verification via `known_hosts`**, with TOFU prompt on
   first connect. Configurable strict mode.
5. **In-process SFTP/SCP**, with real progress bars (byte counts via
   `pkg/sftp`). Works on Windows. Passwords never enter argv.
6. **Auto-reconnect with exponential backoff** per tunnel,
   independent — a flaky bastion doesn't sink siblings.
7. **Connection multiplexing.** One SSH client per bastion, reused
   across children. Fewer auth prompts, faster startup for wide
   fan-outs.
8. **Dynamic (SOCKS) forwards and reverse (`-R`) forwards.** Today
   only local forwards exist.
9. **Port auto-assignment.** `localbindport: auto` replaces manual
   port registries.
10. **Real daemon mode.** `tunnelgraf daemon install` writes a user
    systemd unit / launchd plist; `stop` talks to the unit, not
    `ps`-scrapes.
11. **Status endpoint.** `tunnelgraf status --listen :9999` serves
    JSON + `/metrics` (Prometheus). Makes the existing "look up bind
    ports from automation" use case first-class.
12. **`tunnelgraf doctor <profile>`.** Probes every hop, reports
    where auth/DNS/port fails, highlights the failing step.
13. **`tunnelgraf validate`** plus a **published JSON Schema** for
    the YAML so VS Code/JetBrains autocomplete and lint.
14. **Environment overlays.** `--env staging` merges
    `base.yml + envs/staging.yml`, replacing the current one-way
    `include`.
15. **Dynamic nexthop generation.** Enumerate children from an
    external command (`kubectl get pods -o name`,
    `aws ec2 describe-instances`, etc.) so users don't maintain node
    lists by hand.
16. **`tunnelgraf exec <id> -- argv...`.** Argv-safe remote exec.
    Today `command` takes a single string; quoting bugs are the
    user's problem.
17. **Shell completions** (bash/zsh/fish/pwsh). Free with Cobra.
18. **Profile discovery.** `tunnelgraf -p staging` resolves to
    `~/.config/tunnelgraf/profiles/staging.yml` when it exists.
19. **`/etc/hosts` without `chown`.** Install-once privileged helper
    or hostctl-style segment rewriting. Drop the README's
    "chown /etc/hosts to yourself" advice.

## Compatibility

- YAML schema from 1.x continues to load. The field names
  (`nexthop`, `nexthops`, `localbindport`, `hosts_file_entry`, etc.)
  stay. New fields are additive.
- A `tunnelgraf migrate` subcommand rewrites deprecated fields. The
  main one: `lastpass: <id>` becomes
  `auth: { backend: lastpass, ref: <id> }` — or whatever uniform
  shape we pick. Old form still works with a deprecation warning
  for at least one minor version.
- The 1.x CLI verb set (`connect / show / urls / command / shell /
  scp / stop`) is preserved. `command` gains the argv-safe `exec`
  sibling rather than being replaced.

## Milestones

**M1 — Parity + safety.** Goal: 1.x users can switch without
noticing.

- Profile loader incl. `include`, ssh_config, Pydantic-equivalent
  validation (JSON Schema).
- SSH manager with multiplexing and `known_hosts` verification.
- `connect`, `show`, `urls`, `command`, `shell`, `stop`.
- In-process SFTP/SCP replacing the shell-out.
- Existing integration tests ported.

**M2 — UX.** Goal: visibly better than 1.x.

- Bubble Tea TUI dashboard.
- Auto-reconnect with backoff.
- `graph`, `doctor`, `validate` verbs.
- Port auto-assignment.
- Shell completions.
- JSON Schema published for editor integration.

**M3 — Integration surface.**

- Pluggable secrets backends (start with 1Password + env + keychain;
  LastPass ported for migration).
- Status HTTP endpoint with `/metrics`.
- Daemon install for systemd + launchd.
- Dynamic nexthops from external commands.
- Environment overlays.

**M4 — Long tail.**

- SOCKS and reverse forwards.
- Privileged hosts-file helper.
- Windows first-class support (CI on windows-latest).
- Homebrew tap, scoop manifest, Debian/RPM packaging.

## Distribution

- `goreleaser` publishing to GitHub Releases on tag.
- Homebrew tap for macOS/Linux.
- Scoop bucket for Windows.
- `FROM scratch` Docker image (few MB).
- A `curl https://tunnelgraf.sh/install | sh` one-liner.
- Keep the existing Python package published at 1.x for legacy
  installs, with a README pointer to 2.0.

## Risks and open questions

- **SSH protocol fidelity.** `x/crypto/ssh` covers the protocol but
  some OpenSSH config semantics (e.g., `Match exec`, token
  expansion) are non-trivial to reimplement. Decide early which
  subset is in scope.
- **Windows `/etc/hosts` equivalent.** `C:\Windows\System32\drivers\
  etc\hosts` needs admin. Plan a privileged helper or a clear
  "skip hosts management on Windows" flag.
- **Secrets UX.** The current LastPass integration returns
  hostname + user + pass in one lookup. Not every backend has that
  grouping. Need a small normalised schema
  (`{host?, user?, password?, key?}`) and per-backend adapters.
- **Reconnect semantics for the `/etc/hosts` layer.** Today entries
  are written once after all tunnels start. If a tunnel flaps we
  need to decide whether entries survive the gap (yes, almost
  certainly).
- **Bubble Tea + non-interactive mode.** Detect TTY and fall back
  cleanly to the current log-line output under systemd/cron.

## Non-goals

- Building a general SSH replacement. Tunnelgraf stays a profile
  orchestrator; features like SSH certificates, kerberos, or agent
  forwarding are supported only to the extent `x/crypto/ssh`
  already does.
- Re-inventing kubectl port-forward. Dynamic nexthops from
  `kubectl` is in scope; running inside a cluster is not.
- Secrets *storage*. We read from backends; we never write.
