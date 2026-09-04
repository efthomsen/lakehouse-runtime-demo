# legacy/runtime-clone

**This directory is not a peer option.** It documents the execution model
the reference architecture grew out of, for the "how the execution model
itself evolved" thread in article 1 ("Cheap Compute, Real Engineering"). If
you are looking for how this repo actually runs the workload, see
[`runtime/image/`](../../runtime/image/) instead.

## What it was

The first production version kept deployment deliberately lightweight: a
Batch task cloned the workload repository and executed the relevant Python
entry point through `uv`. That gave fast iteration, isolated dependencies,
and a development workflow that was already substantially better than
embedding the same logic in notebooks. See [`task-command.sh`](task-command.sh)
for the literal shape of that task command, and
[`example-script.py`](example-script.py) for what the workload itself
looked like — a single PEP 723 script, not yet split into the `ingestion`/
`silver` packages this repo ships today.

## What it got right

- **It was already software engineering.** The unit of work was a package
  with an entry point, not a notebook. Code review, tests, and version
  control applied from day one.
- **Dependencies were declared, not installed by hand.** `uv` resolved a
  declared dependency set into an ephemeral environment at task start. No
  interactively mutated runtime, no drift between what a developer ran and
  what the task ran — at a given commit.
- **Iteration was fast.** Push, run, observe. For a small team building out
  many ingestion paths, that loop mattered more than release ceremony.
- **It cost almost nothing extra.** No registry, no build pipeline, no
  image lifecycle. The task needed a VM, git, and `uv`.

For the phase the platform was in, this was the right trade. The mistake
would be to pretend it has no cost.

## Its defining property, and what that costs

The clone-and-run model has one defining property: **the executable version
of the workload is determined when the task starts, not when a release is
approved.** That means:

- A new push can change the next production run without an explicit
  promotion step.
- Reproducing an earlier run means reconstructing repository state and
  dependency resolution, not looking up an artifact.
- Rollback is "push a revert and hope the next task picks it up," not
  "point production back at the previous artifact."
- Binding a run to *exactly what code and dependencies executed* takes
  reconstruction rather than lookup.
- System-level dependencies (OS packages, compiled libraries) live on the
  node image, outside the workload's declared world.

## The three tiers

```text
RUNTIME CHECKOUT
git clone HEAD + uv
Fast iteration, but deployment occurs when the task starts.
                    ↓  (this directory)

LIGHTWEIGHT VERSIONED ARTIFACT
pinned revision + pinned dependencies + uv
Reproducible without necessarily building an image.

IMMUTABLE DEPLOYMENT ARTIFACT
tested container image + pinned digest
Stronger promotion, rollback, system-dependency and environment guarantees.
                    ↓  (see ../../runtime/image/)
```

The correction is **not** "abandon `uv` for Docker." `uv` and containers are
not competing choices — `uv` remains the dependency resolver and Python
runner *inside* the build (see `runtime/image/Dockerfile`). The actual
change is narrower and more important:

> The executable version of the workload moves from being resolved at task
> start to being fixed at release.

A pinned revision with a lockfile already fixes the executable version at
release. The image adds the system-dependency and environment guarantees,
and a promotion unit that moves between environments without being
rebuilt. PEP 723 inline metadata (as in `example-script.py`) makes the
lightweight form self-describing; it is not by itself sufficient
reproducibility — the reproducible unit is pinned code plus deterministic
dependency resolution (a lockfile).
