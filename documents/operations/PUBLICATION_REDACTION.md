# Public artifact redaction

Publication copies of 33 previously tracked files had one live broker account
number removed. This includes measurement logs, research JSON, test fixtures and
operational prose. The JSON and log copies carry a publication marker with the
SHA-256 hash of their original bytes. They are **not authoritative evidence**.
Account aliases in these copies are display labels, not broker or feed IDs.

Byte-exact originals are retained locally under the ignored path
`data/private_publication_archive/account_redaction_20261010/original/`. Its
`original_index.json` lists each path, original hash and occurrence count. The
adjacent `verified_bundle/` retains the original relative `documents/` paths
needed for hash-checked research import. Keep this private archive access
controlled and back it up separately; the local directory alone is not a backup.
Keep any original-account-to-public-alias mapping in private operator records.

Research import must reject the altered publication copies when their frozen hashes
do not match. Set `LEDGERQUANT_PRIVATE_EVIDENCE_ROOT` to the ignored
`verified_bundle/` for an authorized local import. See [research operations](RESEARCH.md).
The current capture feed prefix must be read from its existing private
configuration, never inferred from a public alias. See [capture operations](CAPTURE.md).

This redaction changes the working tree only. Earlier Git commits may still
contain the account number. Removing it from public history requires a separate,
coordinated history rewrite and remote update; this cleanup has not done that.
