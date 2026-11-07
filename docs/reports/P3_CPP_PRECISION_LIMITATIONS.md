# P3 C++ precision limitations

The P3 index improves visibility into source syntax. It is not a C++ compiler, UnrealHeaderTool, UnrealBuildTool,
or runtime trace. The following boundaries are part of its public accuracy contract.

## Unresolved C++ meaning

- tree-sitter does not resolve types, aliases, overloads, argument conversions, ADL, using directives,
  inheritance lookup, templates, concepts, conditional specializations, or generated declarations.
- A unique function spelling candidate is still `unresolved`. Multiple same-name candidates are retained as
  ambiguous. No candidate is also retained rather than guessed.
- Calls through function pointers, delegates, callable objects, lambdas, macros, reflection, interfaces,
  virtual dispatch, or dynamic loading cannot generally be assigned a runtime target by this index.
- Qualified names are source spellings assembled from namespace/class syntax. They are not canonical compiler
  USRs and do not prove that a declaration is valid or visible at the call site.
- Declaration/definition and RPC/event suffix links are conservative source candidates. Default arguments,
  typedef-equivalent parameters, macro expansion, generated overrides, and UHT validation are not checked.

## Preprocessor and Unreal generation

- `#if`, `#ifdef`, `WITH_EDITOR`, platform/build defines, and included macro state are recorded but not evaluated.
  Mutually exclusive declarations may therefore coexist in the index.
- Includes are not expanded. Missing headers do not stop syntax recovery, but types from them stay unresolved.
- `*.generated.h` is recorded as an include. Generated bodies, reflection registrations, thunk functions,
  replicated/RPC wrappers, and Blueprint event glue are absent unless their source exists in the repository.
- UCLASS/UFUNCTION-style macro arguments are preserved as raw source. P3 does not attempt to reproduce UHT's
  full specifier grammar or validate whether a specifier combination is legal in UE 5.7/5.8.
- Build.cs and Target.cs are lexical C# observations. Rule execution, conditional dependency changes, plugin
  enablement, target/platform configuration, and the final module graph require UBT.

## Error recovery and data-flow limits

- tree-sitter can recover after invalid or macro-heavy syntax. Any error node makes the file and top-level
  result `partial`; recovered records remain observations with their spans and issues.
- Assignment sides, updates, and identifier/member expressions provide a local syntax-level read/write view.
  Aliasing, references, pointer effects, operator overloads, interprocedural effects, captures, lifetime,
  constexpr evaluation, and control-dependent values are not resolved.
- Control-flow records are syntax statements, not a control-flow graph. Short-circuit behavior, exception flow,
  coroutine suspension, macro-generated branches, reachability, and runtime order are not proven.
- Nested calls and lambdas are attributed to the containing source function, but lambda invocation identity and
  captured-object semantics remain unresolved.

## Blueprint connection boundary

UFUNCTION raw specifiers and native declaration names are now available for a later exact bridge. Current
catalog C++↔Blueprint navigation still lacks a shared compiler/UHT identity. A Blueprint short name matching a
C++ name is not proof of the same member. Saved Blueprint `semantic_references` should be compared with an
exact native owner/object identity when available; P3 does not promote name-only matches.

## Follow-up Clang validation

A separate semantic resolver should consume the P3 syntax IR and add results without overwriting it. It needs:

1. per-target `compile_commands.json` or faithfully reconstructed UBT actions;
2. the matching UE 5.7/5.8 headers, generated headers, toolchain, platform defines, and plugin/module settings;
3. stable compiler identities such as Clang USRs for declarations and resolved call expressions;
4. explicit failure/partial records per translation unit;
5. tests that compare independently authored sources and compiler AST facts rather than accepting P3 output as truth.

Until that exists, `semantic_resolved` remains unused and its count remains zero. No engine-based C++ validation
was completed in this Linux environment.
