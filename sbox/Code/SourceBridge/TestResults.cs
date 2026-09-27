namespace SourceBridge.Tests;

/// <summary>
/// Collects PASS/FAIL results of the in-engine target tests. Every result is logged as a line
/// starting with "SOURCEBRIDGE-TEST" and written to data/sourcebridge_results.json so it can be
/// attached to the conversion report (see docs/target-tests.md).
/// </summary>
public static class TestResults
{
	public sealed record Result( string Test, string Subject, bool Passed, string Detail );

	static readonly List<Result> results = new();

	public static IReadOnlyList<Result> All => results;

	public static void Report( string test, string subject, bool passed, string detail )
	{
		var r = new Result( test, subject, passed, detail );
		results.Add( r );
		var line = $"SOURCEBRIDGE-TEST {(passed ? "PASS" : "FAIL")} [{test}] {subject}: {detail}";
		if ( passed ) Log.Info( $"{line}" );
		else Log.Warning( $"{line}" );
		FileSystem.Data.WriteJson( "sourcebridge_results.json", results );
	}
}
