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

The research import that consumed `verified_bundle/` was retired with the
research-governance track; its code is preserved under the git tag
`archive/research-governance-v1`. Altered publication copies must still never be
treated as the hash-verified originals.
The current capture feed prefix must be read from its existing private
configuration, never inferred from a public alias. See [capture operations](CAPTURE.md).

On 10 October 2026, `main` was rewritten and GitHub `main` was updated from
`c086682` to `cca7ba9` with `force-with-lease`. The rewritten tip has the same
file tree as the preceding publication-redaction commit. All 46 reachable commits
and 1,451 reachable objects in an isolated clean clone were scanned with no match
for the removed account number. A private original-history bundle is retained
under the ignored `data/private_publication_archive/history_preview_20261010/`.
Existing clones need to move to the rewritten history. The remote update cannot
remove copies held by local Git object stores, forks, other clones or external
caches.
