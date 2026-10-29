// ue-repo-reader editor oracle: read a Blueprint's native editor state and write it out as JSON.
//
// Only engine reads happen here. Anything the engine reports as null or invalid becomes an entry in
// the snapshot's "issues" list rather than a silently shorter array, because the comparator treats a
// missing graph, node or pin as a difference in our own decoder.

#include "RepoReaderOracleLibrary.h"

#include "EdGraph/EdGraph.h"
#include "EdGraph/EdGraphNode.h"
#include "EdGraph/EdGraphPin.h"
#include "Engine/Blueprint.h"
#include "Internationalization/Text.h"
#include "K2Node_FunctionEntry.h"
#include "Misc/EngineVersionComparison.h"
#include "Misc/Guid.h"
#include "Policies/CondensedJsonPrintPolicy.h"
#include "Serialization/JsonWriter.h"
#include "Templates/Casts.h"
#include "UObject/Class.h"
#include "UObject/Package.h"
#include "WidgetBlueprint.h"

// Guarded rather than pinned to one release: the reads below are declared the same way in 5.7 and 5.8,
// so the module builds against both, and an older engine fails here instead of silently half-working.
#if UE_VERSION_OLDER_THAN(5, 7, 0)
#error RepoReaderOracle is only supported on Unreal Engine 5.7 or newer.
#endif

namespace
{
	using FOracleWriter = TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>;

	FString GuidDigits(const FGuid& Guid)
	{
		return Guid.ToString(EGuidFormats::Digits);
	}

	/** Writes an object's path, or JSON null when there is no object; never an empty-string stand-in. */
	void WritePath(FOracleWriter& Writer, const TCHAR* Key, const UObject* Object)
	{
		if (Object != nullptr)
		{
			Writer.WriteValue(Key, Object->GetPathName());
		}
		else
		{
			Writer.WriteNull(Key);
		}
	}

	/**
	 * Writes an FText's authored source string.
	 *
	 * Never its display string: FText::ToString() returns whatever the editor's current culture
	 * resolves to, so a localized project would make the oracle disagree with the source text our
	 * own reader decodes out of the package. When the engine has no source string to give, the field
	 * is null and the reason is reported, rather than quietly standing in the localized display.
	 */
	void WriteTextSource(FOracleWriter& Writer, const TCHAR* Key, const FText& Text,
		const FString& Context, TArray<FString>& Issues)
	{
		const FString* Source = FTextInspector::GetSourceString(Text);
		if (Source == nullptr)
		{
			Issues.Add(FString::Printf(
				TEXT("%s: text field '%s' has no source string; the localized display string is not ")
				TEXT("substituted for it"), *Context, Key));
			Writer.WriteNull(Key);
			return;
		}
		// An empty source string is a real value and is written as "", not as null.
		Writer.WriteValue(Key, *Source);
	}

	void WriteTerminalType(FOracleWriter& Writer, const FEdGraphTerminalType& Terminal,
		const FString& Context, TArray<FString>& Issues)
	{
		// Written for every type, not just maps: an always-present field keeps the records comparable.
		Writer.WriteObjectStart(TEXT("terminal"));
		Writer.WriteValue(TEXT("category"), Terminal.TerminalCategory.ToString());
		Writer.WriteValue(TEXT("subcategory"), Terminal.TerminalSubCategory.ToString());
		if (Terminal.TerminalSubCategoryObject.IsStale())
		{
			Issues.Add(FString::Printf(
				TEXT("%s: the terminal sub-category object has been destroyed; its path is unknown"), *Context));
		}
		WritePath(Writer, TEXT("object_path"), Terminal.TerminalSubCategoryObject.Get());
		// Cast every flag: WriteValue takes its value by reference, and a reference cannot bind to a
		// bitfield, so the neighbouring bitfield flags below would not compile without this.
		Writer.WriteValue(TEXT("is_const"), static_cast<bool>(Terminal.bTerminalIsConst));
		Writer.WriteValue(TEXT("is_weak_pointer"), static_cast<bool>(Terminal.bTerminalIsWeakPointer));
		Writer.WriteObjectEnd();
	}

	void WritePinType(FOracleWriter& Writer, const TCHAR* Key, const FEdGraphPinType& Type,
		const FString& Context, TArray<FString>& Issues)
	{
		Writer.WriteObjectStart(Key);
		Writer.WriteValue(TEXT("category"), Type.PinCategory.ToString());
		Writer.WriteValue(TEXT("subcategory"), Type.PinSubCategory.ToString());
		if (Type.PinSubCategoryObject.IsStale())
		{
			Issues.Add(FString::Printf(
				TEXT("%s: the pin sub-category object has been destroyed; its path is unknown"), *Context));
		}
		WritePath(Writer, TEXT("object_path"), Type.PinSubCategoryObject.Get());
		Writer.WriteValue(TEXT("container"), static_cast<int32>(Type.ContainerType));
		Writer.WriteValue(TEXT("is_reference"), static_cast<bool>(Type.bIsReference));
		Writer.WriteValue(TEXT("is_const"), static_cast<bool>(Type.bIsConst));
		Writer.WriteValue(TEXT("is_weak_pointer"), static_cast<bool>(Type.bIsWeakPointer));
		WriteTerminalType(Writer, Type.PinValueType, Context, Issues);
		Writer.WriteObjectEnd();
	}

	/** Every pin the node owns, including hidden, orphaned and advanced ones, with all of its links. */
	void WritePin(FOracleWriter& Writer, const UEdGraphPin& Pin, const FString& NodePath, TArray<FString>& Issues)
	{
		const FString Context = FString::Printf(TEXT("pin '%s' of node '%s'"), *Pin.PinName.ToString(), *NodePath);

		Writer.WriteObjectStart();
		Writer.WriteValue(TEXT("guid"), GuidDigits(Pin.PinId));
		Writer.WriteValue(TEXT("name"), Pin.PinName.ToString());
		Writer.WriteValue(TEXT("direction"), static_cast<int32>(Pin.Direction.GetValue()));
		WritePinType(Writer, TEXT("type"), Pin.PinType, Context, Issues);
		Writer.WriteValue(TEXT("default_value"), Pin.DefaultValue);
		Writer.WriteValue(TEXT("auto_default_value"), Pin.AutogeneratedDefaultValue);
		WritePath(Writer, TEXT("default_object"), Pin.DefaultObject.Get());
		WriteTextSource(Writer, TEXT("default_text_value"), Pin.DefaultTextValue, Context, Issues);
		Writer.WriteValue(TEXT("hidden"), static_cast<bool>(Pin.bHidden));
		Writer.WriteValue(TEXT("orphaned_pin"), static_cast<bool>(Pin.bOrphanedPin));
		Writer.WriteValue(TEXT("not_connectable"), static_cast<bool>(Pin.bNotConnectable));
		Writer.WriteValue(TEXT("advanced_view"), static_cast<bool>(Pin.bAdvancedView));

		// Links are reported exactly as the engine stores them: no execution order is inferred here.
		Writer.WriteArrayStart(TEXT("links"));
		for (int32 Index = 0; Index < Pin.LinkedTo.Num(); ++Index)
		{
			const UEdGraphPin* Linked = Pin.LinkedTo[Index];
			if (Linked == nullptr)
			{
				Issues.Add(FString::Printf(TEXT("%s: link %d is null and cannot be identified"), *Context, Index));
				continue;
			}

			// Unchecked: a link whose owner was already torn down is an observation, not a reason to assert.
			UEdGraphNode* Owner = Linked->GetOwningNodeUnchecked();
			if (Owner == nullptr)
			{
				Issues.Add(FString::Printf(TEXT("%s: link %d has no owning node"), *Context, Index));
			}

			Writer.WriteObjectStart();
			WritePath(Writer, TEXT("owner_path"), Owner);
			Writer.WriteValue(TEXT("guid"), GuidDigits(Linked->PinId));
			Writer.WriteObjectEnd();
		}
		Writer.WriteArrayEnd();
		Writer.WriteObjectEnd();
	}

	void WriteNode(FOracleWriter& Writer, const UEdGraphNode& Node, TArray<FString>& Issues)
	{
		const FString NodePath = Node.GetPathName();

		Writer.WriteObjectStart();
		Writer.WriteValue(TEXT("object_path"), NodePath);
		Writer.WriteValue(TEXT("class"), Node.GetClass()->GetName());
		Writer.WriteValue(TEXT("guid"), GuidDigits(Node.NodeGuid));

		Writer.WriteArrayStart(TEXT("pins"));
		for (int32 Index = 0; Index < Node.Pins.Num(); ++Index)
		{
			const UEdGraphPin* Pin = Node.Pins[Index];
			if (Pin == nullptr)
			{
				Issues.Add(FString::Printf(TEXT("node '%s': pin %d is null"), *NodePath, Index));
				continue;
			}
			WritePin(Writer, *Pin, NodePath, Issues);
		}
		Writer.WriteArrayEnd();

		if (const UK2Node_FunctionEntry* Entry = Cast<UK2Node_FunctionEntry>(&Node))
		{
			const FString Context = FString::Printf(TEXT("function entry '%s'"), *NodePath);
			const FKismetUserDeclaredFunctionMetadata& MetaData = Entry->MetaData;
			Writer.WriteObjectStart(TEXT("function_metadata"));
			WriteTextSource(Writer, TEXT("tooltip"), MetaData.ToolTip, Context, Issues);
			WriteTextSource(Writer, TEXT("category"), MetaData.Category, Context, Issues);
			WriteTextSource(Writer, TEXT("keywords"), MetaData.Keywords, Context, Issues);
			WriteTextSource(Writer, TEXT("compact_node_title"), MetaData.CompactNodeTitle, Context, Issues);
			Writer.WriteValue(TEXT("call_in_editor"), static_cast<bool>(MetaData.bCallInEditor));
			// GetFunctionFlags() hands back int32, but the saved EFunctionFlags bits are unsigned, so
			// the decimal string is printed unsigned to keep the top bit from reading as a negative.
			Writer.WriteValue(TEXT("flags"),
				FString::Printf(TEXT("%u"), static_cast<uint32>(Entry->GetFunctionFlags())));
			Writer.WriteObjectEnd();
		}
		else
		{
			Writer.WriteNull(TEXT("function_metadata"));
		}

		Writer.WriteObjectEnd();
	}

	void WriteGraph(FOracleWriter& Writer, const UEdGraph& Graph, TArray<FString>& Issues)
	{
		const FString GraphPath = Graph.GetPathName();

		Writer.WriteObjectStart();
		Writer.WriteValue(TEXT("object_path"), GraphPath);
		Writer.WriteValue(TEXT("name"), Graph.GetName());

		Writer.WriteArrayStart(TEXT("nodes"));
		for (int32 Index = 0; Index < Graph.Nodes.Num(); ++Index)
		{
			const UEdGraphNode* Node = Graph.Nodes[Index];
			if (Node == nullptr)
			{
				Issues.Add(FString::Printf(TEXT("graph '%s': node %d is null"), *GraphPath, Index));
				continue;
			}
			WriteNode(Writer, *Node, Issues);
		}
		Writer.WriteArrayEnd();
		Writer.WriteObjectEnd();
	}

	void WriteVariables(FOracleWriter& Writer, const UBlueprint& Blueprint, TArray<FString>& Issues)
	{
		Writer.WriteArrayStart(TEXT("variables"));
		for (const FBPVariableDescription& Variable : Blueprint.NewVariables)
		{
			const FString Context = FString::Printf(TEXT("variable '%s'"), *Variable.VarName.ToString());
			Writer.WriteObjectStart();
			Writer.WriteValue(TEXT("name"), Variable.VarName.ToString());
			Writer.WriteValue(TEXT("guid"), GuidDigits(Variable.VarGuid));
			WritePinType(Writer, TEXT("type"), Variable.VarType, Context, Issues);
			// A decimal string, because PropertyFlags is 64 bits wide and JSON numbers are doubles.
			Writer.WriteValue(TEXT("flags"), FString::Printf(TEXT("%llu"), Variable.PropertyFlags));
			WriteTextSource(Writer, TEXT("category"), Variable.Category, Context, Issues);
			Writer.WriteValue(TEXT("default_value"), Variable.DefaultValue);
			Writer.WriteObjectEnd();
		}
		Writer.WriteArrayEnd();
	}

	void WriteFunctionGraphPaths(FOracleWriter& Writer, const UBlueprint& Blueprint, TArray<FString>& Issues)
	{
		Writer.WriteArrayStart(TEXT("function_graphs"));
		for (int32 Index = 0; Index < Blueprint.FunctionGraphs.Num(); ++Index)
		{
			const UEdGraph* Graph = Blueprint.FunctionGraphs[Index];
			if (Graph == nullptr)
			{
				Issues.Add(FString::Printf(TEXT("blueprint: function graph %d is null"), Index));
				continue;
			}
			Writer.WriteValue(Graph->GetPathName());
		}
		Writer.WriteArrayEnd();
	}

	void WriteGraphs(FOracleWriter& Writer, const UBlueprint& Blueprint, TArray<FString>& Issues)
	{
		// GetAllGraphs covers ubergraph pages, functions, macros, delegate signatures and sub-graphs.
		TArray<UEdGraph*> Graphs;
		Blueprint.GetAllGraphs(Graphs);

		TSet<const UEdGraph*> Seen;
		Writer.WriteArrayStart(TEXT("graphs"));
		for (int32 Index = 0; Index < Graphs.Num(); ++Index)
		{
			const UEdGraph* Graph = Graphs[Index];
			if (Graph == nullptr)
			{
				Issues.Add(FString::Printf(TEXT("blueprint: graph %d is null"), Index));
				continue;
			}

			bool bAlreadySeen = false;
			Seen.Add(Graph, &bAlreadySeen);
			if (bAlreadySeen)
			{
				// The same graph object twice: captured once, but the repetition is still reported.
				Issues.Add(FString::Printf(
					TEXT("blueprint: graph '%s' was listed more than once; it is captured once"),
					*Graph->GetPathName()));
				continue;
			}
			WriteGraph(Writer, *Graph, Issues);
		}
		Writer.WriteArrayEnd();
	}

	void WriteWidgetBindings(FOracleWriter& Writer, const UBlueprint& Blueprint)
	{
		const UWidgetBlueprint* WidgetBlueprint = Cast<UWidgetBlueprint>(&Blueprint);
		if (WidgetBlueprint == nullptr)
		{
			// Null, not an empty array: a non-widget Blueprint has no binding list at all.
			Writer.WriteNull(TEXT("widget_bindings"));
			return;
		}

		Writer.WriteArrayStart(TEXT("widget_bindings"));
		for (const FDelegateEditorBinding& Binding : WidgetBlueprint->Bindings)
		{
			Writer.WriteObjectStart();
			Writer.WriteValue(TEXT("object_name"), Binding.ObjectName);
			Writer.WriteValue(TEXT("property_name"), Binding.PropertyName.ToString());
			Writer.WriteValue(TEXT("function_name"), Binding.FunctionName.ToString());
			Writer.WriteValue(TEXT("kind"), static_cast<int32>(Binding.Kind));
			Writer.WriteObjectEnd();
		}
		Writer.WriteArrayEnd();
	}
}

FString URepoReaderOracleLibrary::CaptureBlueprint(UBlueprint* Blueprint)
{
	if (Blueprint == nullptr)
	{
		// An empty response, so the exporter records a failed capture instead of an empty Blueprint.
		return FString();
	}

	TArray<FString> Issues;
	FString Json;
	const TSharedRef<FOracleWriter> Writer =
		TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Json);

	Writer->WriteObjectStart();
	Writer->WriteValue(TEXT("asset_class"), Blueprint->GetClass()->GetName());
	// Declares what every FText-derived field in this snapshot holds, so a later change of mind about
	// source vs. display text is visible to the comparator instead of silently shifting its meaning.
	Writer->WriteValue(TEXT("text_values"), TEXT("source"));

	// An editor that is holding unsaved edits reports graph state that is not in the package file, and
	// the file's bytes are unchanged while it does, so hashes alone cannot catch it. Reported, never
	// resolved: saving or clearing the flag here would destroy the very thing being compared.
	if (const UPackage* Package = Blueprint->GetOutermost())
	{
		Writer->WriteValue(TEXT("package_dirty"), Package->IsDirty());
	}
	else
	{
		Issues.Add(TEXT("blueprint: it has no outermost package, so unsaved changes cannot be ruled out"));
		Writer->WriteNull(TEXT("package_dirty"));
	}

	WritePath(*Writer, TEXT("parent_class"), Blueprint->ParentClass.Get());
	WriteVariables(*Writer, *Blueprint, Issues);
	WriteFunctionGraphPaths(*Writer, *Blueprint, Issues);
	WriteGraphs(*Writer, *Blueprint, Issues);
	WriteWidgetBindings(*Writer, *Blueprint);

	// Written last so it carries everything noticed above.
	Writer->WriteArrayStart(TEXT("issues"));
	for (const FString& Issue : Issues)
	{
		Writer->WriteValue(Issue);
	}
	Writer->WriteArrayEnd();
	Writer->WriteObjectEnd();

	if (!Writer->Close())
	{
		// A truncated document would parse as a smaller but complete capture, so report nothing.
		return FString();
	}
	return Json;
}
