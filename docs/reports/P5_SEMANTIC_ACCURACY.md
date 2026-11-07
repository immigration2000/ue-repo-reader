# P5 semantic-reference accuracy status

Date: 2026-11-07

## Verdict

No new UE 5.8 Native semantic accuracy result was produced. The attached executor is Linux and has neither an
Unreal installation nor access to the stated Windows PC. All Native result fields below therefore remain **not
measured**, rather than zero or passed.

| Native P5 classification | Count |
|---|---:|
| matched | not measured |
| mismatched | not measured |
| saved/editor-loaded difference | not measured |
| unavailable/unknown | not measured |
| extraction failure | not measured |
| independently verified semantic references | 0 new verified observations |

The last value means this task added no evidence, not that the reader is known to have zero correct references.

## Saved-package baseline for the selected asset

The P4 binary reader was run against ActionRoguelike commit
`31bd38491d9dcec99460d85f3084c79441c5ce8b`, asset
`/Game/ActionRoguelike/UI/PlayerHealth_Widget`, package SHA-256
`2687fa1435cf25e493bf05c2d1e4ddff79cb991dc9c4d43411e6beea4e2cb37e`.

| Reference kind | Saved records | Reader status `complete` | Reader status `partial` |
|---|---:|---:|---:|
| function | 14 | 0 | 14 |
| variable | 3 | 0 | 3 |
| event | 1 | 0 | 1 |
| delegate | 1 | 0 | 1 |
| delegate function name | 1 | 1 | 0 |
| macro graph | 2 | 2 | 0 |
| custom event name | 1 | 1 | 0 |
| **Total** | **23** | **4** | **19** |

The asset has two graphs containing references: EventGraph has 13 records and `OnPlayerHealthChanged` has 10.
Its graph IR is `complete`, its asset parse status is `ok`, and all 32 graph nodes decoded. Those facts establish
reader coverage only. In particular, a partial FMemberReference is not upgraded from its node count or graph
status.

## What Linux tests establish

- The P2 producer schema, exporter guards, and semantic comparator fail-closed behavior pass synthetic tests.
- Same-name/different-owner, wrong GUID, missing parent, duplicate node/reference, saved/loaded mismatch,
  unsupported/unknown, package-hash mismatch, macro/custom-event, and CreateDelegate-owner gaps are tested.
- The P2/P3/P4 full regression remains unchanged: 173 unit tests, six external assets, eight legacy Native Oracle
  groups, two evidence checks, and all four fixed projects pass.
- An old native capture without `semantic_reference_state=loaded-editor` is rejected by the
  `semantic-references` profile as `incomplete` with zero checked observations.

These checks validate comparison behavior and regression compatibility. They do not validate that the new C++
collector compiles against UE 5.8 or that the binary reader agrees with a real loaded `FMemberReference`.

## What the Windows comparison must decide

For every selected node it must retain exact graph path, node path/class/GUID, reference kind and source property.
FMemberReference comparisons must retain MemberParent or self context, MemberName, MemberGuid, effective owner,
resolved member/owner path, and both `saved-package` and `loaded-editor` provenance. MacroGraphReference must use
the exact graph object path. A matching short member name is insufficient.

Results must be separated as follows:

- **match**: all required comparable loaded and saved identity fields agree;
- **mismatch**: both sides are available and differ, with the exact field path and values retained;
- **saved/loaded difference**: a mismatch known to be between serialized and editor-fixed-up state; it remains a
  mismatch until its engine behavior is independently explained;
- **unavailable**: required owner/GUID/target, supported field, clean state, hash, or unique identity is missing;
- **extraction failure**: plugin build, asset load, capture, JSON validation, or binary decode failed.

`passed` is allowed only when observations were actually compared, no mismatch exists, and no required field is
unavailable. Runtime execution, virtual/interface/RPC dispatch, compiled Blueprint behavior, Clang AST, UHT
generated symbols, inherited/CDO values, and gameplay correctness remain outside this profile.

## GridInventorySystem boundary

After P5 succeeds on the fixed validation asset, GridInventorySystem still needs a separate run against its own
clean Windows copy. Pin its Git commit and every selected package hash, capture before any save/compile operation,
compare the same bytes, and preserve all incomplete or saved/loaded differences. The ActionRoguelike result may
validate the toolchain and covered node kinds, but it cannot establish correctness for node/reference kinds absent
from that asset or for GridInventorySystem's generated classes and project modules.
