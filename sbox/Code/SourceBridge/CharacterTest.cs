using System;

namespace SourceBridge.Tests;

/// <summary>
/// Target test for converted Source 1 characters (acceptance proof 2).
///
/// Structure: bone count, sequences, attachments, body groups, physics parts and joints match
/// the original model. Animation: every sequence is played with the renderer's sequence player
/// (no anim graph), frozen at sampled frames, and the model-space positions of end bones (hands,
/// feet, head) are compared with positions computed from the original Source 1 animation data.
/// That checks skeleton, bind pose, keyframes, frame rate and root orientation together.
/// Ragdoll: the ragdoll prefab (ModelPhysics) builds all bodies and joints, drops, and rests on
/// the ground without sinking through it.
/// </summary>
public sealed class CharacterTest : Component
{
	public sealed record BoneExpectation( string Bone, Vector3 Position );
	public sealed record SequenceCheck( string Sequence, int Frame, float Time, BoneExpectation[] Bones );
	public sealed record Case(
		string Prefab, string RagdollPrefab, int BoneCount, string[] Sequences, string[] Attachments,
		int BodyGroups, int PhysicsParts, int Joints, SequenceCheck[] Checks );

	public IReadOnlyList<Case> Cases => GeneratedCases.Characters;

	[Property] public float PositionTolerance { get; set; } = 1.0f;
	[Property] public float GroundTolerance { get; set; } = 3.0f;
	[Property] public float RagdollTimeout { get; set; } = 10f;

	sealed class Running
	{
		public Case Case;
		public GameObject Object;
		public SkinnedModelRenderer Renderer;
		public int CheckIndex = -1;
		public int WaitFrames;
		public GameObject Ragdoll;
		public ModelPhysics Physics;
		public float RagdollStartZ;
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
			var go = GameObject.Clone( c.Prefab, new Transform( new Vector3( x, 256, 0 ) ) );
			var ragdoll = c.RagdollPrefab is null ? null : GameObject.Clone( c.RagdollPrefab, new Transform( new Vector3( x, 384, 60 ) ) );
			x += 128f;

			var renderer = go?.GetComponent<SkinnedModelRenderer>();
			var model = renderer?.Model;
			if ( model is null || model.IsError )
			{
				TestResults.Report( "character.model", c.Prefab, false, "prefab, SkinnedModelRenderer or model missing" );
				continue;
			}
			TestResults.Report( "character.model", c.Prefab, true, $"loaded, {model.BoneCount} bones" );
			TestResults.Report( "character.bones", c.Prefab, model.BoneCount == c.BoneCount, $"{model.BoneCount} bones, expected {c.BoneCount}" );

			var names = model.AnimationNames ?? new List<string>();
			var missingSeq = c.Sequences.Where( s => !names.Contains( s ) ).ToArray();
			TestResults.Report( "character.sequences", c.Prefab, missingSeq.Length == 0,
				missingSeq.Length == 0 ? $"all {c.Sequences.Length} sequences present" : $"missing: {string.Join( ", ", missingSeq )} (model has: {string.Join( ", ", names )})" );

			var missingAtt = c.Attachments.Where( a => model.GetAttachment( a ) is null ).ToArray();
			TestResults.Report( "character.attachments", c.Prefab, missingAtt.Length == 0,
				missingAtt.Length == 0 ? $"all {c.Attachments.Length} attachments present" : $"missing: {string.Join( ", ", missingAtt )}" );

			TestResults.Report( "character.bodygroups", c.Prefab, model.BodyGroupCount == c.BodyGroups,
				$"{model.BodyGroupCount} body groups, expected {c.BodyGroups}" );

			var parts = model.Physics?.Parts.Count ?? 0;
			var joints = model.Physics?.Joints.Count ?? 0;
			TestResults.Report( "character.physics", c.Prefab, parts == c.PhysicsParts && joints == c.Joints,
				$"{parts} physics parts / {joints} joints, expected {c.PhysicsParts} / {c.Joints}" );

			renderer.UseAnimGraph = false;
			running.Add( new Running
			{
				Case = c, Object = go, Renderer = renderer, Ragdoll = ragdoll,
				Physics = ragdoll?.GetComponent<ModelPhysics>(), RagdollStartZ = ragdoll?.WorldPosition.z ?? 0,
			} );
		}
	}

	protected override void OnUpdate()
	{
		foreach ( var r in running )
		{
			if ( r.Done ) continue;
			StepAnimation( r );
		}
	}

	void StepAnimation( Running r )
	{
		if ( r.WaitFrames > 0 )
		{
			r.WaitFrames--;
			return;
		}

		if ( r.CheckIndex >= 0 && r.CheckIndex < r.Case.Checks.Length )
			Evaluate( r, r.Case.Checks[r.CheckIndex] );

		r.CheckIndex++;
		if ( r.CheckIndex >= r.Case.Checks.Length )
		{
			r.Done = r.Ragdoll is null;
			return;
		}

		var check = r.Case.Checks[r.CheckIndex];
		r.Renderer.Sequence.Name = check.Sequence;
		r.Renderer.Sequence.PlaybackRate = 0;
		r.Renderer.Sequence.Time = check.Time;
		r.WaitFrames = 3;
	}

	void Evaluate( Running r, SequenceCheck check )
	{
		var worst = 0f;
		var worstBone = "";
		var missing = new List<string>();
		foreach ( var b in check.Bones )
		{
			if ( !r.Renderer.TryGetBoneTransform( b.Bone, out var tx ) )
			{
				missing.Add( b.Bone );
				continue;
			}
			var local = r.Object.WorldTransform.ToLocal( tx ).Position;
			var d = local.Distance( b.Position );
			if ( d > worst ) { worst = d; worstBone = $"{b.Bone} at {local}, expected {b.Position}"; }
		}
		var ok = missing.Count == 0 && worst <= PositionTolerance;
		TestResults.Report( "character.animation", $"{r.Case.Prefab} {check.Sequence}@{check.Frame}", ok,
			missing.Count > 0 ? $"bones not found: {string.Join( ", ", missing )}" : $"max deviation {worst:0.00} ({worstBone})" );
	}

	protected override void OnFixedUpdate()
	{
		foreach ( var r in running )
		{
			if ( r.Ragdoll is null || r.Done ) continue;
			if ( r.CheckIndex < r.Case.Checks.Length ) continue; // animation checks first

			if ( r.Physics is null )
			{
				TestResults.Report( "character.ragdoll", r.Case.RagdollPrefab, false, "no ModelPhysics on the ragdoll prefab" );
				r.Done = true;
				continue;
			}

			var bodies = r.Physics.Bodies;
			var settled = bodies.Count > 0 && bodies.All( b => b.Component is not null && b.Component.Velocity.Length < 1f );
			if ( !settled && sinceStart < RagdollTimeout ) continue;
			r.Done = true;

			TestResults.Report( "character.ragdoll.bodies", r.Case.RagdollPrefab,
				bodies.Count == r.Case.PhysicsParts && r.Physics.Joints.Count == r.Case.Joints,
				$"{bodies.Count} bodies / {r.Physics.Joints.Count} joints, expected {r.Case.PhysicsParts} / {r.Case.Joints}" );

			var lowest = bodies.Count > 0 ? bodies.Min( b => b.Component.WorldPosition.z ) : float.NaN;
			var dropped = bodies.Count > 0 && bodies.Max( b => b.Component.WorldPosition.z ) < r.RagdollStartZ + 80f;
			TestResults.Report( "character.ragdoll.fall", r.Case.RagdollPrefab, settled && dropped && lowest >= -GroundTolerance,
				$"settled={settled} after {(float)sinceStart:0.0}s, lowest body origin z {lowest:0.00} (must not be below -{GroundTolerance})" );
		}
	}
}
