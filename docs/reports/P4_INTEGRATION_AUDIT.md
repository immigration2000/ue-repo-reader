# P4 C++ ↔ Blueprint integration audit

Date: 2026-11-07

Branch: `codex/p4-unified-analysis`

Base: `codex/accuracy-p0-p1` at `dcb99dc`

Integrated inputs: P2 `d4012f9`, P3 `0c945e6`

## Integration result

P2 was merged as `c66da40` and P3 as `6511059`. P2 and P3 had no product-code or test conflict. Both had
added handoff entries to `docs/dev/DECISIONS.md` and `docs/dev/WORKLOG.md`; those two documentation conflicts
were resolved by retaining both records and assigning D-031 to P2 and D-032 to P3. No existing branch was
rewritten. The P2 editor producer/comparator and P3 syntax index remain independent inputs.

The integrated baseline, before P4 implementation, passed 169 unit tests, six external asset cases, the
existing Native Oracle and saved/loaded evidence checks, and all four pinned project digests. P2's actual
UE 5.7/5.8 plugin build and new semantic-reference capture were not run in this Linux environment. Their
status therefore remains unavailable rather than inherited from the older native fixtures.

## Inputs that P4 can combine

| Input | Direct observations retained | Accuracy boundary retained |
|---|---|---|
| `cpp.precision` | types, bases, declarations/definitions, fields, calls, reads/writes, source and byte spans, Unreal annotations | tree-sitter observes syntax; it does not resolve types, overloads, preprocessing, UHT output or runtime dispatch |
| `graph_ir` | graph/node/pin identities, pin types/defaults, exact or unresolved saved links, saved semantic references | decoder-exposed saved package data; graph completeness is not gameplay-semantic completeness |
| `declaration_ir` | saved parent path, variables, types/defaults/flags and function graph references | missing/default-omitted/inherited/runtime fields remain unknown |
| P2 native comparison | editor-loaded owner/member/GUID and saved-package identity under a same-hash profile | unavailable until a clean new UE 5.7/5.8 capture is actually built and compared |

The earlier `cpp.classes`, `graph_ir`, `declaration_ir`, and `cpp.precision` structures were not removed or
redefined. P4 is an additive synthesis in `analysis/UNIFIED_ANALYSIS.json` and `digest.json.unified_analysis`.

## Existing mapping risks found

The catalog's historical C++ ↔ Blueprint display mapping is a navigation hint based on unique names. P3's
call candidates are also spelling candidates. Neither source establishes a compiled C++ symbol or UHT member
identity. Promoting either to a resolved target would produce false positives for overloads, duplicate class
names, namespaces, inherited members, virtual calls, interfaces, BlueprintNativeEvent thunks and RPC dispatch.

Blueprint FunctionReference/VariableReference/EventReference/DelegateReference records contain stronger saved
owner paths and member fields, but the binary observation still does not identify a C++ AST declaration. A
saved `/Script/Module.Class` path plus member name narrows the candidates; it does not prove overload selection,
generated thunk identity or runtime dispatch. Wrong/missing GUIDs and saved/editor-loaded disagreement must
remain visible.

Function result nodes can contain both output parameters and a return value. P4 retains every output pin and
marks a uniquely named `ReturnValue`/`Result` pin only as a return candidate. It does not reinterpret every
result pin as a return value.

## Priority and remaining risk

P4 addresses the highest-risk synthesis errors by retaining duplicates, recording all candidates, providing
forward and reverse relation indexes, propagating partial/unavailable input status, and banning name-only
cross-language `verified` results. It does not create compiler semantics.

The main remaining risks are:

- C++ aliases, templates, overload conversion and macro-expanded declarations need a matching Clang AST or
  compiler index before exact symbol resolution.
- UHT generated functions, `_Implementation`, `_Validate`, BlueprintNativeEvent, RPC and interface dispatch
  need generated headers/UHT or runtime evidence.
- The P2 collector still needs a real UE 5.8 build and capture, with UE 5.7 repeated separately.
- Saved graph links establish stored topology, not the runtime execution order after compilation or latent flow.
- Blueprint member GUIDs and editor-loaded owner paths may differ from saved fields; P4 does not erase that
  boundary or treat unknown as equal.

No game project, source fixture, package, fixture expectation, editor Oracle JSON or independent evidence JSON
was changed during the integration.
