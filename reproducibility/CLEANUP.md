# Publication checkout cleanup

This branch removes 6292 historical paths from the current checkout,
including old simulation logs, ZIP copies, obsolete model/data directories,
NetBeans/IDE state, diagnostic scripts and earlier submission plots. Those paths
represented approximately 1400.1 MiB of uncompressed tracked files.
The old objects remain in Git history; this is not a history rewrite or an action
on Nancy's saved local outputs. All old results remain accessible at the frozen
v5 commit documented in SOURCE_PROVENANCE.json.

All 56 Java sources, nine required JARs, six AI-based Weka models and the active
optimization/training logic are byte-identical to the frozen v5 source. The EXP3
routing variant uses an existing JVM flag in its own new scenarios. The only
runner changes select/check that routing schema and a normalization-only manifest.
The cleanup itself changes no simulation algorithm, model, seeds or parameters.

Use a new directory for this branch while the overnight run uses its existing
checkout. Review and validate the new results before making this the default
publication branch. The draft pull request intentionally leaves main unchanged.

A compact clone (after publication of this branch) is:

```bash
git clone --depth 1 --single-branch --branch codex/publication-reproducible \
  https://github.com/nancyboughannam/SCOPE-major-revision.git SCOPE-publication
```

The repository includes source/configuration, the unchanged third-party binaries
and AI-based model files, scripts to regenerate SCOPE training data/models, fixed
protocols, resumable simulations, statistics and MATLAB plotting. It does not yet
include the final guard-off results, which are still to be produced. Add a durable,
checksummed result archive before resubmission, with the exact executed commit and
manifest. Do not replace this missing archive with selected summary curves.

MATLAB rendering must be checked on a machine with MATLAB and Times New Roman.
Do not claim this cleanup resolves remaining scientific reviewer requests.
