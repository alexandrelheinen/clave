# Standards and agent toolchain

Four external pieces shape how work happens in this repository. Two are
documents, pinned here as git submodules. Two are tools that install into
the agent on your machine, so they are pinned by version in this file
rather than vendored.

| Piece | Role | Consumed as | Pinned at |
| --- | --- | --- | --- |
| [guidelines](https://github.com/alexandrelheinen/guidelines) | Personal standards: method, writing voice, naming, per-language style | Submodule at `standards/guidelines` | `v1.1.0` |
| [cc-sdd](https://github.com/gotalab/cc-sdd) | Method: spec-driven development harness, 17 agent skills | Submodule at `standards/cc-sdd`, installed with `npx` | `v3.0.2` |
| [caveman](https://github.com/JuliusBrussee/caveman) | Prompt compression, on demand | Claude Code plugin | `v2.6.0` |
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

**caveman is not enabled by default in this repository.** It compresses
agent output into telegraphic style, which saves tokens in a working
session but contradicts
[guidelines/agents/writing.md](guidelines/agents/writing.md), the rule that
governs every piece of prose that ends up committed. Invoke it explicitly
with `/caveman` for exploratory or throwaway work, and leave it off when
the output is a README, a spec, a commit message, or a PR description.

Note the license: caveman's skill surface is MIT, but its compression
engine and the Go binaries that embed it are Business Source License 1.1,
which is not open source in the OSI sense. The additional use grant covers
first-party self-hosted use, which is what this is, and a commercial
license would be required to offer it as a hosted or embedded service to
third parties. See
[LICENSING.md](https://github.com/JuliusBrussee/caveman/blob/main/LICENSING.md).

`mattpocock-skills` is MIT throughout.

## Precedence

When two of these disagree, resolve in this order:

1. A direct request from the maintainer in the active task.
2. [CONTRIBUTING.md](../CONTRIBUTING.md), this repository's constitution.
3. `standards/guidelines`, the personal standards.
4. [docs/guidelines.md](../docs/guidelines.md), coding notes specific to
   CLAVE.
5. cc-sdd and the installed skillsets.

The guidelines outrank the imported skillsets on purpose. A skillset is
someone else's opinion about how to work and it is welcome, but the house
voice, naming, and language rules are the ones that survive into the
repository.
