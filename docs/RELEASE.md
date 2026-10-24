# Public release scope

This repository is the verification and evaluation release of the Consilience engine (paper v1). It is a
mirror of a private working repository, with the sensitive trees removed and residual internal framing
scrubbed from the documentation.

## Excluded from this public release
For holdout integrity and privacy, the mirror excludes:
- held-out answer keys and any held-out key text;
- the obfuscation maps;
- personal review/annotation packets;
- all corpus input PDFs (copyright and held-out key sources);
- secrets and local caches.

Because the held-out key material and review packets are excluded, some task drivers and parts of the test
suite cannot be re-run here. The integrity gate that does run is the holdout scan, the secret scan, the
read-only and quarantine guards, the banned-phrase lint, and registry validation.

## Numbers
The README, the paper, and every rendered table draw their headline numbers from one locked registry
snapshot (`paper/NUMBERS_LOCK.json`, sha `e9c877812c8c6897…`); identical metric → identical number
everywhere.
