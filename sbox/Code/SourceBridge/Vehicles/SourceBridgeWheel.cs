using System;

namespace SourceBridge.Vehicles;

/// <summary>
/// Raycast wheel with spring/damper suspension and a simple tire model. Placed at the wheel
/// position of the original Source vehicle (its wheel_* attachment). Forces are applied to the
/// vehicle's Rigidbody; <see cref="SourceBridgeVehicle"/> drives the wheels in a fixed order.
///
/// The raycast suspension follows the approach of Facepunch's libwheel (MIT,
/// github.com/Facepunch/sbox-libwheel); the tire and brake handling is SourceBridge's own.
/// This is a recreation of the driving behaviour, not Source's vphysics vehicle.
/// </summary>
[Title( "SourceBridge Wheel" ), Category( "SourceBridge" ), Icon( "trip_origin" )]
public sealed class SourceBridgeWheel : Component
{
	[Property] public float Radius { get; set; } = 14f;
	[Property] public float SuspensionTravel { get; set; } = 8f;
	[Property] public bool Steers { get; set; }
	[Property] public float DriveShare { get; set; } = 0.25f;
	[Property] public float BrakeShare { get; set; } = 0.25f;
	/// <summary>Bone that shows this wheel; animated through bone overrides.</summary>
	[Property] public string BoneName { get; set; }

	/// <summary>Spring rate and damping are derived from the static load by the vehicle.</summary>
	public float Stiffness { get; set; }
	public float Damping { get; set; }
	public float StaticLoad { get; set; }

	public bool IsGrounded { get; private set; }
	public float Compression { get; private set; }
	public float SteerAngle { get; set; }
	public float SpinDegrees { get; private set; }
	public float NormalForce { get; private set; }
	public float ForwardSpeed { get; private set; }

	internal void Step( Rigidbody body, Vector3 vehicleForward, Vector3 up, float drive, float brake, float grip, float dt )
	{
		var top = WorldPosition + up * (SuspensionTravel * 0.5f);
		var length = SuspensionTravel + Radius;
		var tr = Scene.Trace.Ray( top, top - up * length )
			.IgnoreGameObjectHierarchy( GameObject.Root )
			.Run();

		IsGrounded = tr.Hit;
		var forward = Rotation.FromAxis( up, SteerAngle ) * vehicleForward;
		var contact = tr.Hit ? tr.HitPosition : top - up * length;
		var velocity = body.GetVelocityAtPoint( WorldPosition );
		ForwardSpeed = Vector3.Dot( velocity, forward );

		if ( !tr.Hit )
		{
			Compression = 0;
			NormalForce = 0;
			SpinDegrees += ForwardSpeed / Radius * dt * (180f / MathF.PI);
			return;
		}

		Compression = Math.Clamp( length - tr.Distance, 0f, SuspensionTravel );
		var springVelocity = Vector3.Dot( velocity, up );
		var suspension = Stiffness * Compression - Damping * springVelocity;
		NormalForce = MathF.Max( 0f, suspension );
		body.ApplyForceAt( WorldPosition, up * NormalForce );

		// tire: cancel sideways slip, apply drive and brake, all limited by grip * load
		var groundForward = (forward - up * Vector3.Dot( forward, up )).Normal;
		var side = Vector3.Cross( up, groundForward ).Normal;
		var sideSpeed = Vector3.Dot( velocity, side );
		var loadMass = StaticLoad / MathF.Max( 1f, Scene.PhysicsWorld.Gravity.Length );

		var lateral = -sideSpeed * loadMass / dt;
		var longitudinal = drive;
		if ( brake > 0 )
		{
			var stop = -ForwardSpeed * loadMass / dt;
			longitudinal += MathF.Sign( stop ) * MathF.Min( MathF.Abs( stop ), brake );
		}

		var limit = grip * NormalForce;
		var total = new Vector2( longitudinal, lateral );
		if ( total.Length > limit && total.Length > 0 )
			total *= limit / total.Length;

		body.ApplyForceAt( contact, groundForward * total.x + side * total.y );
		SpinDegrees += ForwardSpeed / Radius * dt * (180f / MathF.PI);
	}

	protected override void DrawGizmos()
	{
		Gizmo.Draw.Color = Color.White;
		Gizmo.Draw.LineCircle( Vector3.Zero, Vector3.Left, Radius );
		Gizmo.Draw.Color = Color.Cyan;
		Gizmo.Draw.Line( Vector3.Up * (SuspensionTravel * 0.5f), Vector3.Down * (SuspensionTravel * 0.5f) );
	}
}
