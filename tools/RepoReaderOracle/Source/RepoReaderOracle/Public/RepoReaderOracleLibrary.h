// ue-repo-reader editor oracle: the native half of the Blueprint capture bridge.

#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"

#include "RepoReaderOracleLibrary.generated.h"

class UBlueprint;

/**
 * Read-only bridge from the running editor to tools/export_editor_oracle.py.
 *
 * UE 5.8's stock Python bindings do not expose Blueprint::UbergraphPages, FunctionGraphs,
 * NewVariables or UEdGraph::Nodes, and list_all_pins only reports visible K2 pins, so a Python-only
 * oracle cannot see the graph the engine actually holds. This library exposes the native reads
 * instead, as unreal.RepoReaderOracleLibrary.capture_blueprint(blueprint).
 *
 * Everything here observes. Nothing compiles, modifies, marks dirty or saves: the exporter hashes
 * each package before and after a capture and reports a mismatch as a failure.
 */
UCLASS()
class REPOREADERORACLE_API URepoReaderOracleLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/**
	 * Returns one JSON object describing the Blueprint's native editor state (schema v1: see
	 * tools/export_editor_oracle.py). Returns an empty string, never a partial or plausible-looking
	 * object, when there is nothing trustworthy to report.
	 */
	UFUNCTION(BlueprintCallable, Category = "Repo Reader Oracle")
	static FString CaptureBlueprint(UBlueprint* Blueprint);
};
