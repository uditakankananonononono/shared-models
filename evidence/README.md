# Rebuild evidence

All text files are stdout/stderr captured from commands in this rebuild, not the
previous builder's attachments. No transcript, agent messages or internal runtime
instructions are included. Synthetic fixtures use the literal private-synthetic-fixture,
not user data. Tests are offline except scripts/verify_needle_live.py and the named
metadata/source checks.

- failing-first.txt: original boundary tests against base eaacd54, 49 failures, 8 errors.
- engine-failing-first.txt: stale automatic downgrade test failed before removal.
- extra-failing-first.txt: absent arguments and malformed catalog URL tests failed before fixes.
- needle-shapes-failing-first.txt: malformed Needle calls failed before shape checks.
- final-unittest.txt and final-pytest.txt: all final tests green.
- dependency-install.txt: real pinned cactus-needle and pytest installation.
- needle-real.txt: real pinned 3.0.2 engine inference and production router path.
- model-metadata.txt: live HF file sizes, revision and hashes.
- hardware.txt: current resource limits and exact hardware blockers.
- inkling-source.txt: HTTP 403 on the inherited source, no fresh confirmation.

No real Ornith/Inkling inference or three-product acceptance is claimed. No live
catalog request was performed in this rebuild. No push was performed.
