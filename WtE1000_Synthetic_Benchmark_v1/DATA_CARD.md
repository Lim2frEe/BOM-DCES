# Data card and provenance

## Generation history

This is a new procedural dataset. Its only source information is the aggregate
WtE1000 profile described in Section VII-C of the supplied BOM-DCES manuscript,
plus the author-specified local traversal caps discussed during revision.
No original engineering records were used to construct any graph edge,
collaborator mapping, file content, or workload event.

## Published facts versus operationalization

| Published description | Operationalization |
| --- | --- |
| Approximately 18,563 BOM nodes | Exactly 18,563 synthetic nodes |
| 4,116 leaf data entities | Exactly 4,116 structural leaves and one entity per leaf |
| Maximum depth 19 | 19 hierarchical levels, with root at level 1 |
| Nine engineering disciplines | The nine disclosed generic categories |
| 52 collaborating enterprises | 52 fictional SPC identities; LC is a separate logical role |
| 12,820 drawing pages | Exactly 12,820 binary-payload catalog records |
| Approximately 272 GB | Exactly 272,000,000,000 unencrypted payload bytes, SI convention |
| Several KB to 280 MB per page | Chosen minimum 4,096 bytes and maximum 280,000,000 bytes |
| Author-specified local observation: at most 6 levels and 282 nodes | Capped synthetic tasks, including a deliberately constructed boundary case |

Original approximate values and unspecified units are not represented as
recovered exact industrial measurements.

## Explicitly synthetic choices

1. Internal-node counts by level use the integer weights in config.json.
   The large internal/leaf ratio necessarily introduces many unary nodes in
   the primary tree. Its distribution is not fitted to the industrial BOM.
2. The first nine branches are synthetic discipline anchors. Remaining primary
   parents are capacity-limited assignments; the non-root primary degree cap is six.
3. A local boundary subtree uses invented level counts [1,5,20,56,90,110].
   Extra references do not add descendants outside this subtree.
4. The default 412 shared-leaf references are a configurable assumption.
   Their frequency is not disclosed by the manuscript and is not estimated here.
5. SPCs are distributed across primary disciplines, and leaf ownership is
   balanced within a discipline. These associations are not actual company roles.
6. Every entity has at least one page. Additional pages use random entity
   assignments. File sizes use bounded integer power-skewed weights and exact
   volume allocation, with range anchors; this is not an observed size distribution.
7. Local scopes are selected with size-biased sampling from admissible roots.
   The selector is not an engineering change-impact model or an empirical
   frequency estimate.
8. Confirmation microbenchmark sets are independent of local BOM impact scopes.

## Intended uses

- Reconstructing the aggregate-scale benchmark from a fixed seed.
- Testing BOM/DAG indexing, deduplication and affected-SPC set construction.
- Integrating synthetic payloads with an independent encryption implementation.
- Evaluating confirmation submissions with explicitly known transaction counts.
- Sensitivity tests with changed seeds and shared-reference counts.

## Unsupported claims

- This is not the confidential WtE1000 dataset, an anonymized copy of its graph,
  or a recovery of its engineering semantics.
- Matching marginal counts does not prove workload-distribution equivalence.
- The package does not implement the full BOM-DCES cryptographic protocol,
  Hyperledger Fabric network, or original experimental environment.
- No manuscript cryptographic, communication, or ledger timing is generated
  or validated by the dataset. New reference-traversal timings have their own scope.
- Sparse and prefix files do not constitute the full 272 GB payload.

## Validation and reproducibility

The validator independently recomputes the graph root, reachability, acyclicity,
longest-path levels, leaf set, owners, page assignments, total sizes, task results
and ledger operation counts. It checks SHA-256 for the shipped metadata.
The reproduction check regenerates every metadata file byte-for-byte and tests
that corrupted graphs, sizes and owners are rejected.

Canonical generation uses integer arithmetic, an explicitly implemented
SplitMix64/Fisher-Yates sampler, deterministic ordering, UTF-8 and LF line endings.
Payload blocks use SHAKE256 with public per-page seeds and fixed 1 MiB blocks.
The RNG and payload generator are simulation tools, not a cryptographic key setup.

## Release scope

The data can be distributed without disclosing any original project content.
Public availability still requires uploading this artifact to an accessible
repository or supplement. Choose the actual persistent URL/DOI at release time.
