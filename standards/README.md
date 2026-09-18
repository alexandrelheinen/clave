# Standards and agent toolchain

Three external pieces shape how work happens in this repository. One is a
document library, pinned here as a git submodule. Two are tools that
install into the agent on your machine, so they are pinned by version in
this file rather than vendored.

| Piece | Role | Consumed as | Pinned at |
| --- | --- | --- | --- |
| [guidelines](https://github.com/alexandrelheinen/guidelines) | Personal standards: method, writing voice, naming, per-language style | Submodule at `standards/guidelines` | `v1.2.0` |
| [caveman](https://github.com/JuliusBrussee/caveman) | Prompt compression, on demand | Claude Code plugin | commit `15581d14` |
| [mattpocock-skills](https://github.com/mattpocock/skills) | Skillset: TDD, review, spec and ticket flows, domain modeling | Claude Code plugin | `v1.2.3` |

The split is deliberate. A submodule is worth it when the checked-out
files are the thing you read, which holds for the guidelines. A plugin
installs into `~/.claude` on the machine and its repository is build
tooling, so vendoring it would add megabytes of source nobody reads and a
second version that can drift from the one actually running.

## The guidelines submodule

It is pinned to a tag rather than tracking a moving branch, so a checkout
of any commit in this repository reproduces the standards that applied
when it was written.

```bash
# First clone
git clone --recurse-submodules https://github.com/alexandrelheinen/clave.git

# Existing clone
git submodule update --init --recursive
```

Moving to a newer version is a deliberate commit, never a drive-by:

```bash
git -C standards/guidelines fetch --tags
git -C standards/guidelines checkout v1.3.0
git add standards/guidelines
git commit -m "Move guidelines to v1.3.0"
```

Read the guidelines before changing anything here. `CLAUDE.md` imports the
files that apply to every task; the rest of the library is worth reading
once.

## Installing the Claude Code plugins

Both are machine-level and only need installing once, not per repository:

```bash
claude plugin marketplace add mattpocock/skills
claude plugin install mattpocock-skills@mattpocock

claude plugin marketplace add JuliusBrussee/caveman
claude plugin install caveman@caveman
```

Verify with `claude plugin list`.

Version pinning differs between the two. `mattpocock-skills` declares a
`version` in its plugin manifest, so the install records `1.2.3`. caveman
declares none, so Claude Code pins to the marketplace commit it cloned and
records that sha instead. Either way the exact pin lives in
`~/.claude/plugins/installed_plugins.json`, and `claude plugin update`
moves it.

### caveman is switched off in this repository

caveman does not sit idle until invoked. Its plugin manifest registers a
`SessionStart` hook that injects its ruleset as hidden context and a
`UserPromptSubmit` hook, and `getDefaultMode` in its configuration module
falls through to `full` when nothing overrides it. Installing it is
therefore enough to turn it on everywhere.

That contradicts
[agents/writing.md](guidelines/agents/writing.md#compression-tools), which
governs every piece of prose that ends up committed and scopes a
compression tool to output nobody keeps. The `.caveman.json` at the
repository root turns it off for CLAVE:

```json
{
  "defaultMode": "off"
}
```

caveman walks up from the working directory looking for `.caveman/config.json`
or `.caveman.json` and takes the first one it finds, so the file covers the
whole repository. Only `CAVEMAN_DEFAULT_MODE` in the environment outranks
it.

Invoke it explicitly with `/caveman` for exploratory or throwaway work, and
leave it off when the output is a README, a spec, a commit message, or a
pull request description.

Note the license: caveman's skill surface is MIT, but its compression
engine and the Go binaries that embed it are Business Source License 1.1,
which is not open source in the OSI sense. The additional use grant covers
first-party self-hosted use, which is what this is, and a commercial
license would be required to offer it as a hosted or embedded service to
third parties. See
[LICENSING.md](https://github.com/JuliusBrussee/caveman/blob/main/LICENSING.md).

`mattpocock-skills` is MIT throughout.

## Precedence

The order is set once, upstream, in
[agents/claude.md](guidelines/agents/claude.md): a direct request from the
maintainer, then [CONTRIBUTING.md](../CONTRIBUTING.md), then the shared
guidelines, then the installed skills and plugins, then general best
practice. CLAVE slots [docs/guidelines.md](../docs/guidelines.md) between
the constitution and the guidelines, since it holds the notes specific to
this project.

Where a package and the guidelines genuinely conflict, the decision is
already recorded in
[integrations/toolkits.md](guidelines/integrations/toolkits.md#arbitration).
Look it up rather than re-deciding it here, and if the conflict is not
listed, add it there instead of settling it privately.
