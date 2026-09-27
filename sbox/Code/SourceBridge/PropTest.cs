using System;

namespace SourceBridge.Tests;

/// <summary>
/// Target test for converted Source 1 props (acceptance proof 1).
///
/// For every prefab: spawn it <see cref="DropHeight"/> units above the ground plane, then check
///  1. the model loaded (not the error model) and has the expected skins,
///  2. the model carries physics (collision parts) and the Rigidbody uses the preserved mass,
///  3. it falls under gravity and comes to rest ON the ground: the lowest point of its physics
///     bounds ends within <see cref="GroundTolerance"/> of the ground plane (z = 0), i.e. it
///     neither sinks through nor hovers.
/// </summary>
public sealed class PropTest : Component
{
	public sealed record Case( string Prefab, float ExpectedMass, int ExpectedMaterialGroups );

	/// <summary>Cases come from GeneratedCases.cs, written by tools/prepare_sbox_project.py.</summary>
	public IReadOnlyList<Case> Cases => GeneratedCases.Props;
	[Property] public float DropHeight { get; set; } = 96f;
	[Property] public float GroundTolerance { get; set; } = 1.5f;
	[Property] public float Timeout { get; set; } = 10f;

	sealed class Running
	{
		public Case Case;
		public GameObject Object;
		public Rigidbody Body;
		public Model Model;
		public float StartZ;
		public bool Done;
	}

	readonly List<Running> running = new();
	TimeSince sinceStart;

	protected override void OnStart()
	{
		sinceStart = 0;
		var x = 0f;
		foreach ( var c in Cases )
		{
			var go = GameObject.Clone( c.Prefab, new Transform( new Vector3( x, 0, DropHeight ) ) );
			x += 96f;
			if ( go is null || !go.IsValid() )
			{
				TestResults.Report( "prop.spawn", c.Prefab, false, "prefab could not be cloned" );
				continue;
			}

			var renderer = go.GetComponent<ModelRenderer>();
			var model = renderer?.Model;
			var modelOk = model is not null && !model.IsError;
			TestResults.Report( "prop.model", c.Prefab, modelOk,
				modelOk ? $"loaded, bounds {model.Bounds.Mins} .. {model.Bounds.Maxs}" : "error model or no ModelRenderer" );
			if ( !modelOk ) continue;

			TestResults.Report( "prop.skins", c.Prefab, model.MaterialGroupCount == c.ExpectedMaterialGroups,
				$"{model.MaterialGroupCount} material groups, expected {c.ExpectedMaterialGroups}" );

			var parts = model.Physics?.Parts.Count ?? 0;
			TestResults.Report( "prop.collision", c.Prefab, parts > 0, $"{parts} physics part(s)" );

			var body = go.GetComponent<Rigidbody>();
			running.Add( new Running { Case = c, Object = go, Body = body, Model = model, StartZ = go.WorldPosition.z } );
		}
	}

	protected override void OnFixedUpdate()
	{
		foreach ( var r in running )
		{
			if ( r.Done ) continue;
			if ( r.Body is null )
			{
				TestResults.Report( "prop.physics", r.Case.Prefab, false, "no Rigidbody on the prefab" );
				r.Done = true;
				continue;
			}

			var settled = r.Body.Sleeping || (sinceStart > 2f && r.Body.Velocity.Length < 0.5f);
			if ( !settled && sinceStart < Timeout ) continue;
			r.Done = true;

			var massOk = r.Case.ExpectedMass <= 0 || MathF.Abs( r.Body.Mass - r.Case.ExpectedMass ) < 0.01f;
			TestResults.Report( "prop.mass", r.Case.Prefab, massOk, $"mass {r.Body.Mass}, expected {r.Case.ExpectedMass}" );

			var fell = r.Object.WorldPosition.z < r.StartZ - 1f;
			var lowest = r.Object.WorldPosition.z + r.Model.PhysicsBounds.Mins.z;
			var onGround = MathF.Abs( lowest ) <= GroundTolerance;
			TestResults.Report( "prop.fall", r.Case.Prefab, fell && settled && onGround,
				$"settled={settled} after {(float)sinceStart:0.0}s, start z {r.StartZ}, lowest physics point z {lowest:0.00} (ground 0 ± {GroundTolerance})" );
		}
	}
}
