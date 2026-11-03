# WtE1000-Synthetic v1.0.0

A reproducible, fully synthetic BOM benchmark matching the aggregate WtE1000
statistics disclosed in the BOM-DCES manuscript. It contains no original
engineering drawings, industrial identifiers, original BOM edges, or measured
cryptographic/blockchain runtimes.

See README_ZH.md for Chinese instructions and DATA_CARD.md for assumptions and
limitations. Python 3.10 or newer is required. There are no third-party packages.

## Matched aggregate profile

| Property | Synthetic release |
| --- | ---: |
| BOM nodes | 18,563 |
| Leaf data entities | 4,116 |
| Maximum hierarchical levels | 19 |
| Engineering disciplines | 9 |
| Synthetic SPC identities | 52 |
| Drawing-page records | 12,820 |
| Logical payload volume | 272,000,000,000 bytes = 272 GB |
| Minimum synthetic page size | 4,096 bytes |
| Maximum page size | 280,000,000 bytes = 280 MB |

The approximate published counts/volumes are operationalized as exact synthetic
targets. Units are decimal: GB = 10^9 bytes and MB = 10^6 bytes. The manuscript's
"several KB" minimum is represented by a deliberately chosen 4,096-byte anchor.
The root is level 1: 19 levels correspond to 18 root-to-leaf edges. These
conventions are explicit assumptions, not recovered exact original byte counts.

## Quick start

Unzip the archive and run these commands from this directory:

    python validate.py --data data
    python reproduce.py --data data
    python benchmark.py --data data --repeats 5 --output traversal_results.json

The first command checks the shipped metadata. The second regenerates it in a
temporary directory, checks byte-for-byte equality, and verifies detection of
deliberately corrupted sizes, edges, and owners. The third runs a reference
descendant-traversal and affected-SPC deduplication benchmark. Its measurements
are not the paper's Init/Enc/Dec/Co-Editing runtimes.

To regenerate the canonical metadata:

    python generate.py --config config.json --output regenerated_data
    python validate.py --data regenerated_data

To generate another seed or disable shared references:

    python generate.py --seed 42 --shared-leaves 0 --output alternate_data
    python validate.py --data alternate_data

Always choose a new or empty output directory.

## Contents and schema

| File | Purpose |
| --- | --- |
| data/nodes.csv | Node ID, level, FP/MW/CP kind, synthetic discipline, entity/owner mapping and primary parent |
| data/edges.csv | Primary hierarchy edges and additional shared-leaf references |
| data/entities.csv | One entity per structural leaf; owner, discipline, page count and logical byte total |
| data/pages.csv | 12,820 page IDs, exact logical lengths, deterministic payload seeds and relative paths |
| data/spcs.csv | 52 fictional SPC identities and synthetic primary disciplines |
| data/disciplines.csv | Nine disclosed discipline categories, with English and Chinese labels |
| data/modifications.jsonl | 1,000 synthetic modification requests with explicit affected roots and expected traversal/owner results |
| data/confirmation_batches.jsonl | Participant sets for confirmation microbenchmarks of sizes 1, 2, 5, 10, 20 and 52 |
| data/generation_config.json | Exact generation configuration |
| data/summary.json | Recomputed size, topology and local-workload statistics |
| data/manifest.json | SHA-256 and file-size manifest for the canonical metadata |
| reports/ | Independent validation, deterministic reproduction and reference-traversal reports |

Node kind CP denotes a leaf data entity; FP denotes the root and MW other
internal nodes. Internal nodes have the logical LC role. The 52 reported
collaborators are represented as SPC identities; LC is a separate logical role,
not an additional entry in spcs.csv. This is a benchmark modeling convention.

## Shared components and local changes

The base hierarchy has 18,562 primary edges. The default adds 412 shared-leaf
references, a configurable synthetic assumption, not an observed WtE1000
frequency. All edges join adjacent levels, preserving a DAG and the declared
maximum number of levels. Shared leaves are not duplicated as nodes.

The local workload uses the author-specified caps of six levels and 282 visited
nodes. A deliberately constructed boundary subtree has level counts
[1, 5, 20, 56, 90, 110], totaling 282 nodes over six levels. This particular
shape is invented for boundary testing, not extracted from the industrial BOM.
The workload includes this boundary and additional size-biased random local
scopes. The exact generated results are in data/summary.json.

Affected roots are explicit inputs. The reference benchmark traverses their
descendant union and deduplicates leaf owners. It does not infer the engineering
semantics that decide where upward propagation should stop. To evaluate your
own propagation algorithm, replace this scenario selector with your policy and
continue to use the synthetic graph.

Confirmation microbenchmark participant sets are separate from the BOM-derived
modification scenarios. For a set of t participants, they record t confirmations,
t+2 ledger writes, and t separate confirmation queries. They contain no assumed
or fabricated execution times.

## Payload generation: no 272 GB download required

The archive contains metadata and generators, not 272 GB of files. The catalog
specifies exactly that logical volume. Generated payloads are deterministic
binary test bytes, not CAD documents or original industrial content.

Preview a plan for three small prefixes (no files are written):

    python materialize.py --data data --mode prefix

Write the complete minimum-sized page (4,096 bytes):

    python materialize.py --data data --mode full --page-id P000001 --execute

Write only 16 KiB of the maximum-sized logical page:

    python materialize.py --data data --mode prefix --page-id P000002 --prefix-bytes 16384 --execute

Materialize all 12,820 complete payloads when the full workload is needed:

    python materialize.py --data data --mode full --all-pages --execute

Full mode writes 272 GB of payload bytes plus metadata/filesystem overhead.
Generation is streamed in 1 MiB blocks with bounded memory. Output goes into a
mode-specific directory, and existing payload files are not overwritten.
Prefix output and its report clearly distinguish the logical size from bytes
actually materialized.

Sparse mode is available for filesystem/metadata tests:

    python materialize.py --data data --mode sparse --all-pages --execute

Sparse files contain zero-filled holes and are not a substitute for full
payloads in encryption, compression, disk-throughput or network benchmarks.

## Reproducibility boundaries

Matched counts do not establish a match to the original distribution of branch
degrees, component reuse, file sizes, owner correlations or modification
frequency. Those distributions are explicitly synthetic. This release supports
independent functional and scaling experiments under the disclosed aggregate
profile; it does not reproduce the confidential project or automatically
reproduce the paper's end-to-end performance results.

There are no real engineering-file contents, private keys, participant names,
transaction signatures, or original industrial mappings in this archive.
Payload seeds are public simulation inputs, not secret cryptographic keys.