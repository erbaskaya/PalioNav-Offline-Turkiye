# Palio Nav v6 package architecture

Build base: OsmAnd r5.4 release branch, androidFull + legacy renderer, ARMv7 + ARM64.

Startup flow:

1. Android starts OsmandApplication.
2. PalioBootstrapActivity is the launcher.
3. On first run it extracts seven embedded Turkey OBF packages to OsmAnd storage.
4. PalioRestartActivity runs in the existing `:restart` process, kills the first main process and opens MapActivity in a fresh process.
5. OsmAnd indexes the already-installed maps during normal startup.
6. Later launches pass through the lightweight bootstrap and immediately open MapActivity.

This avoids opening the full map UI while the offline data set is still absent or half-installed.
