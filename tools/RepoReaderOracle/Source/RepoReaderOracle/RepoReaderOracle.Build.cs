// ue-repo-reader editor oracle. No engine or third-party source is copied into this module;
// it only calls public engine APIs declared in the headers it includes.

using UnrealBuildTool;

public class RepoReaderOracle : ModuleRules
{
	public RepoReaderOracle(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = ModuleRules.PCHUsageMode.UseExplicitOrSharedPCHs;

		// The public header only needs UBlueprintFunctionLibrary.
		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core",
			"CoreUObject",
			"Engine",
		});

		// Everything that reads editor-only state stays private: this module is never in a game target.
		PrivateDependencyModuleNames.AddRange(new string[]
		{
			"Json",
			"UnrealEd",
			"BlueprintGraph",
			"UMG",
			"UMGEditor",
		});
	}
}
