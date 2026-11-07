# P4 unified-analysis accuracy contract

Date: 2026-11-07

## Resolution levels

| Status | Meaning in schema 1 | Forbidden interpretation |
|---|---|---|
| `verified` | exact saved source and target identities already present in an input IR | compiled C++ target, runtime order or gameplay meaning |
| `candidate` | one logical spelling/path candidate remains after retaining declaration/definition duplicates | unique target proven by compiler/UHT |
| `ambiguous` | two or more logical targets remain and are all preserved | first/nearest/name-matching target selected |
| `unavailable` | required identity is missing, unknown, unsupported, or has no observable target | empty/default/no relation |

Cross-language `verified` is currently prohibited. A saved `/Script/Module.Class`, member name and GUID are
preserved as evidence, but the C++ syntax index has no compiler or UHT symbol ID with which to prove equality.
`accuracy_contract.cross_language_verified_count` is therefore zero and is covered by tests.

## Provenance and traversal

Each relationship records one or more of `graph_ir:saved-package`, `saved-pin-reference`, and
`cpp.precision:tree-sitter-cpp`. Blueprint relationships preserve asset, graph, node and pin IDs. C++
relationships preserve file and exact source/byte span from P3 when present. Missing spans remain null; they are
not reconstructed from rendered Markdown.

The source index answers “what does this function/node refer to?” The target-or-candidate index answers “which
observations mention this declaration/pin?” Both indexes point to relation IDs, so callers still read status,
evidence and issues rather than treating index membership as proof.

## Supported synthesis

- Blueprint parent `/Script` path to reflected C++ type candidates using module and Unreal prefix-normalized
  source spelling;
- FunctionReference, EventReference and Interface function records to C++ or same-asset Blueprint function candidates;
- VariableReference and DelegateReference records to C++ field candidates;
- Blueprint self/asset variable reference to saved declaration candidates;
- exact, candidate, ambiguous and unresolved saved Blueprint execution/data pin links;
- exact saved MacroGraph object paths and candidate same-asset function/delegate targets;
- C++ base syntax, call spelling candidates, lexical field reads/writes, `override` candidates and Unreal
  `_Implementation/_Validate` links;
- Blueprint entry and result pins, with return role retained only as an unverified name candidate;
- forward/reverse lookup by exact entity IDs and a separate case-folded name lookup for discovery.

Declaration and definition records with the same qualified spelling and normalized parameter syntax are one
logical candidate but retain their separate source identities. Different parameter syntax remains ambiguous.
Duplicate class names, namespaces and Blueprint graph names keep separate IDs.

## Fail-closed cases

- A short name alone never creates a cross-language relation.
- Multiple overloads or duplicate class/member identities remain `ambiguous`.
- Missing owner paths, wrong/missing member identity and unsupported reference kinds remain `unavailable`.
- P2 saved/editor-loaded mismatch is an input issue and forces overall `partial` status.
- P3 `partial`/`unavailable`, partial graph IR, or partial declaration IR forces overall `partial` status.
- BlueprintNativeEvent, BlueprintImplementableEvent, RPC, interface, virtual and override dispatch retain explicit
  UHT/compiler/runtime issues.
- Pure-node data links preserve saved topology; no evaluation or execution order is synthesized.

## What has and has not been verified

Synthetic tests independently assert the status contract, duplicates, overloads, wrong GUID, missing target,
saved/loaded mismatch, inheritance/override, NativeEvent implementation, interface and partial-input cases.
The four pinned repositories verify deterministic generation without changing legacy expectations. The fixed
ActionRoguelike commit verifies that C++ and Blueprint data coexist and produce conservative relationships.

No new P2 Native Oracle capture was produced. Existing native regression data validates its earlier selected
profiles; it lacks the new semantic capability and cannot independently certify P4's C++ targets. No compiler,
Clang AST, UHT or Unreal runtime call target was observed. These are `not run`, not passing checks.

## Before GridInventorySystem analysis

Run 1.20.0 against a clean, pinned GridInventorySystem commit and preserve its generated analysis separately
from the game repository. Confirm every source asset/package hash. On Windows UE 5.8, build the read-only P2
plugin and create a fresh `semantic-references` capture; compare it with the same package bytes and report every
saved/loaded difference. Repeat on UE 5.7 only if that version must be supported.

For any relationship that must become exact across languages, generate a compile database using the matching
engine, platform defines, UHT output and project configuration, then add an independent typed resolver. Do not
upgrade current name/path candidates in place. Until that exists, use candidate relations to locate the original
C++ source and Blueprint node/pin, inspect both, and retain virtual/interface/RPC dispatch uncertainty.
