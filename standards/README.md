# Standards and agent toolchain

Four external pieces shape how work happens in this repository. Two are
documents, pinned here as git submodules. Two are tools that install into
the agent on your machine, so they are pinned by version in this file
rather than vendored.

| Piece | Role | Consumed as | Pinned at |
| --- | --- | --- | --- |
| [guidelines](https://github.com/alexandrelheinen/guidelines) | Personal standards: method, writing voice, naming, per-language style | Submodule at `standards/guidelines` | `v1.1.0` |
| [cc-sdd](https://github.com/gotalab/cc-sdd) | Method: spec-driven development harness, 17 agent skills | Submodule at `standards/cc-sdd`, installed with `npx` | `v3.0.2` |
| [caveman](https://github.com/JuliusBrussee/caveman) | Prompt compression, on demand | Claude Code plugin | commit `15581d14` |
| [mattpocock-skills](https://github.com/mattpocock/skills) | Skillset: TDD, review, spec and ticket flows, domain modelling | Claude Code plugin | `v1.2.3` |

The split is deliberate. A submodule is worth it when the checked-out
files are the thing you read, which holds for the guidelines and for the
cc-sdd method documents. A plugin installs into `~/.claude` on the machine
and its repository is build tooling, so vendoring it would add megabytes
of source nobody reads and a second version that can drift from the one
actually running.

## Submodules

Both submodules are pinned to a tag rather than tracking a moving branch,
so a checkout of any commit in this repository reproduces the standards
that applied when it was written.

```bash
# First clone
git clone --recurse-submodules https://github.com/alexandrelheinen/clave.git

# Existing clone
git submodule update --init --recursive
```

Moving to a newer version is a deliberate commit, never a drive-by:

```bash
git -C standards/guidelines fetch --tags
git -C standards/guidelines checkout v1.2.0
git add standards/guidelines
git commit -m "Move guidelines to v1.2.0"
```

Read the guidelines before changing anything here. `CLAUDE.md` imports the
files that apply to every task; the rest of the library is worth reading
once.

## Installing cc-sdd

cc-sdd ships its method as agent skills that have to be installed into the
project. The submodule holds the source and the reference documents; the
skills themselves are written by the installer.

Run it from the repository root, and preview first, because the installer
writes `CLAUDE.md` and would otherwise overwrite the one this repository
maintains:

```bash
npx cc-sdd@3.0.2 --claude-skills --lang en --dry-run --backup
```

Read what it plans to touch. If `CLAUDE.md` is on the list, keep the
backup it offers, then restore this repository's version afterwards with
`git checkout CLAUDE.md`. Then run it for real:

```bash
npx cc-sdd@3.0.2 --claude-skills --lang en --backup
git checkout CLAUDE.md
```

It creates `.claude/skills/` with 17 skills and `.kiro/` with the
templates, rules, steering documents, and specs. Both are committed: they
are project state, not machine state, and a reviewer needs to see a spec
change in the diff.

Pin the installed version to the submodule. If you upgrade one, upgrade
the other in the same commit, so `standards/cc-sdd` always documents the
skills that are actually installed.

Entry point once installed:

```
/kiro-discovery <idea>
```

Discovery routes the work and names the next command. The full phase chain
is `kiro-discovery`, `kiro-spec-init`, `kiro-spec-requirements`,
`kiro-spec-design`, `kiro-spec-tasks`, then `kiro-impl` for autonomous
implementation. Reference documents live in the submodule:

- [Skill reference](cc-sdd/docs/guides/skill-reference.md)
- [Spec-driven guide](cc-sdd/docs/guides/spec-driven.md)
- [Why cc-sdd](cc-sdd/docs/guides/why-cc-sdd.md)
- [Customization guide](cc-sdd/docs/guides/customization-guide.md)

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
