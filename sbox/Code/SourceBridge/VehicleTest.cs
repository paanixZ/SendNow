using System;
using SourceBridge.Vehicles;

namespace SourceBridge.Tests;

/// <summary>
/// Target test for converted Source 1 / GMod vehicles (acceptance proof 3). Drives the vehicle
/// through its public inputs, no player needed:
///  1. rest: all wheels on the ground; each rendered wheel bone sits at its wheel position (model
///     orientation and rest pose correct); seat and eyes at the original attachments; mass; engine sound,
///  2. throttle: moves forward along the original driving direction, stays under the top speed,
///  3. brake: comes to a stop,
///  4. steering: turns left, then right,
///  5. reverse: moves backwards, stays under the reverse top speed,
///  6. seat: enter puts the occupant on the seat, exit places it beside the vehicle.
/// </summary>
public sealed class VehicleTest : Component
{
	public sealed record Case( string Prefab, float Mass, float MaxSpeed, float MaxReverseSpeed, float TrackWidth );

	public IReadOnlyList<Case> Cases => GeneratedCases.Vehicles;

	[Property] public float WheelTolerance { get; set; } = 1.5f;

	enum Phase { Settle, Drive, Brake, SteerLeft, SteerRight, Stop, Reverse, Seat, Done }

	sealed class Running
	{
		public Case Case;
		public GameObject Object;
		public SourceBridgeVehicle Vehicle;
		public Phase Phase;
		public TimeSince InPhase;
		public Vector3 PhaseStart;
		public float PhaseYaw;
		public float MaxAbsSpeed;
	}

	readonly List<Running> running = new();

	protected override void OnStart()
	{
		var x = 0f;
		foreach ( var c in Cases )
		{
			var go = GameObject.Clone( c.Prefab, new Transform( new Vector3( x, -900, 40 ) ) );
			x += 400f;
			var vehicle = go?.GetComponent<SourceBridgeVehicle>();
			if ( vehicle is null )
			{
				TestResults.Report( "vehicle.spawn", c.Prefab, false, "prefab or SourceBridgeVehicle missing" );
				continue;
			}
			vehicle.AcceptPlayerInput = false;
			running.Add( new Running { Case = c, Object = go, Vehicle = vehicle, Phase = Phase.Settle, InPhase = 0 } );
		}
	}

	float Yaw( Running r )
	{
		var f = r.Vehicle.WorldForward;
		return MathF.Atan2( f.y, f.x ) * 180f / MathF.PI;
	}

	float Along( Running r ) => Vector3.Dot( r.Object.WorldPosition - r.PhaseStart, r.Vehicle.WorldForward );

	void Next( Running r, Phase p )
	{
		r.Phase = p;
		r.InPhase = 0;
		r.PhaseStart = r.Object.WorldPosition;
		r.PhaseYaw = Yaw( r );
		r.MaxAbsSpeed = 0;
	}

	protected override void OnFixedUpdate()
	{
		foreach ( var r in running )
		{
			var v = r.Vehicle;
			r.MaxAbsSpeed = MathF.Max( r.MaxAbsSpeed, MathF.Abs( v.Speed ) );
			switch ( r.Phase )
			{
				case Phase.Settle:
					v.Throttle = 0; v.Steer = 0; v.Brake = 1;
					if ( r.InPhase > 3f ) { CheckRest( r ); v.Brake = 0; Next( r, Phase.Drive ); }
					break;
				case Phase.Drive:
					v.Throttle = 1; v.Brake = 0;
					if ( r.InPhase > 4f )
					{
						var d = Along( r );
						TestResults.Report( "vehicle.drive", r.Case.Prefab, d > 150f && r.MaxAbsSpeed <= r.Case.MaxSpeed * 1.1f,
							$"moved {d:0} in forward in 4 s, top speed {r.MaxAbsSpeed:0} in/s (limit {r.Case.MaxSpeed:0})" );
						Next( r, Phase.Brake );
					}
					break;
				case Phase.Brake:
					v.Throttle = 0; v.Brake = 1;
					if ( MathF.Abs( v.Speed ) < 5f || r.InPhase > 5f )
					{
						var stopped = MathF.Abs( v.Speed ) < 5f;
						TestResults.Report( "vehicle.brake", r.Case.Prefab, stopped,
							$"speed {v.Speed:0.0} in/s after {(float)r.InPhase:0.00} s, stopping distance {Along( r ):0} in" );
						Next( r, Phase.SteerLeft );
					}
					break;
				case Phase.SteerLeft:
					v.Brake = 0; v.Throttle = 0.6f; v.Steer = 1;
					if ( r.InPhase > 3f )
					{
						var turned = Angle( Yaw( r ) - r.PhaseYaw );
						TestResults.Report( "vehicle.steer.left", r.Case.Prefab, turned > 25f,
							$"yaw changed {turned:0.0} deg (steer angle {v.SteerAngle:0.0})" );
						Next( r, Phase.SteerRight );
					}
					break;
				case Phase.SteerRight:
					v.Throttle = 0.6f; v.Steer = -1;
					if ( r.InPhase > 3f )
					{
						var turned = Angle( Yaw( r ) - r.PhaseYaw );
						TestResults.Report( "vehicle.steer.right", r.Case.Prefab, turned < -25f,
							$"yaw changed {turned:0.0} deg (steer angle {v.SteerAngle:0.0})" );
						Next( r, Phase.Stop );
					}
					break;
				case Phase.Stop:
					v.Throttle = 0; v.Steer = 0; v.Brake = 1;
					if ( MathF.Abs( v.Speed ) < 2f && r.InPhase > 1f ) Next( r, Phase.Reverse );
					else if ( r.InPhase > 6f ) Next( r, Phase.Reverse );
					break;
				case Phase.Reverse:
					v.Brake = 0; v.Throttle = -1;
					if ( r.InPhase > 3f )
					{
						var d = Along( r );
						TestResults.Report( "vehicle.reverse", r.Case.Prefab, d < -60f && r.MaxAbsSpeed <= r.Case.MaxReverseSpeed * 1.1f,
							$"moved {d:0} in along forward in 3 s, top reverse speed {r.MaxAbsSpeed:0} in/s (limit {r.Case.MaxReverseSpeed:0})" );
						Next( r, Phase.Seat );
					}
					break;
				case Phase.Seat:
					v.Throttle = 0; v.Brake = 1;
					CheckSeat( r );
					Next( r, Phase.Done );
					break;
			}
		}
	}

	static float Angle( float a )
	{
		while ( a > 180f ) a -= 360f;
		while ( a < -180f ) a += 360f;
		return a;
	}

	void CheckRest( Running r )
	{
		var v = r.Vehicle;
		var grounded = v.Wheels.Count( w => w.IsGrounded );
		TestResults.Report( "vehicle.wheels.grounded", r.Case.Prefab, grounded == v.Wheels.Count && v.Wheels.Count == 4,
			$"{grounded}/{v.Wheels.Count} wheels on the ground" );

		var renderer = r.Object.GetComponent<SkinnedModelRenderer>();
		var worst = 0f;
		var detail = "";
		foreach ( var w in v.Wheels )
		{
			if ( renderer is null || !renderer.TryGetBoneTransform( w.BoneName, out var bone ) ) { worst = float.MaxValue; detail = $"bone {w.BoneName} missing"; continue; }
			var d = bone.Position.WithZ( 0 ).Distance( w.WorldPosition.WithZ( 0 ) );
			if ( d > worst ) { worst = d; detail = $"{w.BoneName}: {d:0.00}"; }
		}
		TestResults.Report( "vehicle.wheels.position", r.Case.Prefab, worst <= WheelTolerance,
			$"largest horizontal distance wheel bone to wheel {detail} (tolerance {WheelTolerance})" );

		var model = renderer?.Model;
		var seat = v.Seat;
		var eyesAttachment = model?.GetAttachment( "vehicle_driver_eyes" );
		var eyes = seat?.Eyes;
		var eyesOk = eyesAttachment.HasValue && eyes is not null
			&& r.Object.WorldTransform.PointToWorld( eyesAttachment.Value.Position ).Distance( eyes.WorldPosition ) <= WheelTolerance;
		TestResults.Report( "vehicle.seat", r.Case.Prefab, seat is not null && eyesOk,
			seat is null ? "no seat" : $"eyes anchor vs model attachment vehicle_driver_eyes within {WheelTolerance}: {eyesOk}" );

		TestResults.Report( "vehicle.mass", r.Case.Prefab, MathF.Abs( v.Body.Mass - r.Case.Mass ) < 1f, $"mass {v.Body.Mass:0}, expected {r.Case.Mass:0}" );

		var sound = v.EngineSoundHandle;
		TestResults.Report( "vehicle.sound", r.Case.Prefab, sound.IsValid() && sound.IsPlaying, sound.IsValid() ? "engine sound playing" : "no engine sound" );

		var lowest = v.Wheels.Min( w => w.WorldPosition.z - w.Radius );
		TestResults.Report( "vehicle.ride_height", r.Case.Prefab, MathF.Abs( lowest ) < 6f,
			$"lowest wheel bottom z {lowest:0.0} (ground 0, suspension travel {v.Wheels.First().SuspensionTravel})" );
	}

	void CheckSeat( Running r )
	{
		var seat = r.Vehicle.Seat;
		if ( seat is null ) { TestResults.Report( "vehicle.enter_exit", r.Case.Prefab, false, "no seat" ); return; }
		var dummy = new GameObject( true, "SourceBridge test occupant" );
		seat.Enter( dummy );
		var onSeat = dummy.WorldPosition.Distance( seat.WorldPosition ) < 0.5f && seat.Occupant == dummy;
		var exit = seat.Exit();
		var lateral = MathF.Abs( Vector3.Dot( exit - r.Object.WorldPosition, Vector3.Cross( r.Vehicle.WorldForward, Vector3.Up ).Normal ) );
		var outside = lateral > r.Case.TrackWidth * 0.5f;
		TestResults.Report( "vehicle.enter_exit", r.Case.Prefab, onSeat && outside && seat.Occupant is null,
			$"on seat after enter: {onSeat}; exit {lateral:0} in beside the centre line (half track {r.Case.TrackWidth * 0.5f:0})" );
		dummy.Destroy();
	}
}
