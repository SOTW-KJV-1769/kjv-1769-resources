# Owner manual installation

1. Establish or select the independent KJV translation repository under the intended Servants of the Way GitHub organization. The ZIPs are **repository-root-relative** and do not contain an enclosing wrapper folder. No target repository is assumed to exist yet.
2. Extract each `UPLOAD_PART_*.zip` locally. Upload/merge its contents at the **repository root**, preserving nested `data/`, `books/`, `docs/`, and `assets/` paths. The parts are disjoint; no previous files must be overwritten. Do not upload a `.zip` file as an inert file expecting GitHub to extract it. Each part contains **95 files or fewer**. GitHub browser upload allows at most **100 files at once** and **25 MiB per individual file**. These parts are kept below both limits; upload the *extracted files*, not the ZIP itself.
3. Place the site on GitHub Pages (branch `main`, root) only if you choose. This package itself does not deploy a website. Open `books/genesis/site/index.html` and test chapter selection, verse selection, `#GEN.1.1`, `?ref=GEN.1.1`, and next/previous navigation. Repeat on a Psalm, a Gospel, and Revelation.
4. Verify 66 catalogs and reader paths, 1,189 chapter files, 31,102 verse records, supplied italics, Psalm headings, source notes, 68 signed-manifest SHA checks, and source/release hashes.
5. Confirm no KJV facsimile PDFs, embedded Strong’s fields, original-language data, or commentary data were added. Study tools and CGBC player integration remain separate projects.

The source archive with embedded Strong’s tags is not copied into the public KJV repo. Keep the original owner-uploaded source ZIP and its SHA-256 lock outside this release. For an independent rebuild, run the separately supplied `scripts/build_kjv1769.py` using the exact archive, after adjusting its input/output paths for the local environment.

## Public display and archival source metadata

The public root book index and all 66 book readers show the King James Version and Servants of the Way Digital Library branding. They do **not** display the third-party digital text source, its URL, or the rights statement. Those details, including source SHA-256 and source edition ID, remain in `docs/EDITION.json`, `docs/SOURCE_LOCK.json`, `docs/RIGHTS_AND_PROVENANCE.md`, and each book's `SOURCE_INVENTORY.json`. The GitHub repository's technical documentation remains public by nature, but is separate from the public reading interface.
