using System;

namespace SourceBridge.Vehicles;

/// <summary>
/// Drivable vehicle recreated from a Source / Garry's Mod vehicle script.
///
/// Values come from the converted VehicleDoc (engine power, top and reverse speed, steering
/// angles and rates, axle torque and brake shares, wheel radius and positions, mass). Values the
/// Source script does not define (tire grip, brake deceleration, suspension travel) are
/// estimates and are marked as such in the conversion report.
///
/// Driving model (recreated, not identical to Source's vphysics vehicle):
///  - drive force = min(power / speed, grip * weight) until the top speed,
///  - brakes: <see cref="BrakeDeceleration"/> g total, split by the axle brake shares,
///  - steering angle blends from DegreesSlow to DegreesFast between SlowSpeed and FastSpeed.
/// Single player only; nothing is networked yet.
/// </summary>
[Title( "SourceBridge Vehicle" ), Category( "SourceBridge" ), Icon( "directions_car" )]
public sealed class SourceBridgeVehicle : Component
{
	/// <summary>1 hp = 745.7 W; power in kg·in²/s³ because s&box works in inches.</summary>
	public const float HorsepowerToEngineUnits = 745.7f / (0.0254f * 0.0254f);

	[Property, Group( "Engine" )] public float Horsepower { get; set; } = 180f;
	[Property, Group( "Engine" )] public float MaxSpeed { get; set; } = 528f;
	[Property, Group( "Engine" )] public float MaxReverseSpeed { get; set; } = 176f;
	[Property, Group( "Steering" )] public float DegreesSlow { get; set; } = 40f;
	[Property, Group( "Steering" )] public float DegreesFast { get; set; } = 20f;
	[Property, Group( "Steering" )] public float SlowSpeed { get; set; } = 176f;
	[Property, Group( "Steering" )] public float FastSpeed { get; set; } = 440f;
	[Property, Group( "Steering" )] public float SteerRateSlow { get; set; } = 3f;
	[Property, Group( "Steering" )] public float SteerRateFast { get; set; } = 1.5f;
	[Property, Group( "Steering" )] public float SteerRestRateSlow { get; set; } = 3f;
	[Property, Group( "Steering" )] public float SteerRestRateFast { get; set; } = 1.5f;
	[Property, Group( "Steering" )] public float SteerExponent { get; set; } = 1f;
	[Property, Group( "Estimated" )] public float TireGrip { get; set; } = 1.0f;
	[Property, Group( "Estimated" )] public float BrakeDeceleration { get; set; } = 0.8f;
	[Property, Group( "Estimated" )] public float SuspensionDampingRatio { get; set; } = 0.7f;
	/// <summary>Driving direction in model space, from the rear axle to the front axle.</summary>
	[Property] public Vector3 ForwardAxis { get; set; } = Vector3.Forward;
	[Property] public string EngineSound { get; set; }
	[Property] public bool AcceptPlayerInput { get; set; } = true;

	public float Throttle { get; set; }
	public float Steer { get; set; }
	public float Brake { get; set; }

	public float Speed { get; private set; }
	public float SteerAngle { get; private set; }
	public IReadOnlyList<SourceBridgeWheel> Wheels => wheels;
	public SoundHandle EngineSoundHandle => engineSound;
	public Rigidbody Body => body;
	public VehicleSeat Seat => seat;

	Rigidbody body;
	SkinnedModelRenderer renderer;
	VehicleSeat seat;
	readonly List<SourceBridgeWheel> wheels = new();
	readonly Dictionary<SourceBridgeWheel, Transform> wheelBoneRest = new();
	SoundHandle engineSound;

	public Vector3 WorldForward => WorldRotation * ForwardAxis.Normal;

	protected override void OnStart()
	{
		body = GetComponent<Rigidbody>();
		renderer = GetComponent<SkinnedModelRenderer>();
		seat = GetComponentInChildren<VehicleSeat>();
		wheels.Clear();
		wheels.AddRange( GetComponentsInChildren<SourceBridgeWheel>() );
		SetupSuspension();


		if ( !string.IsNullOrEmpty( EngineSound ) )
			engineSound = Sound.Play( EngineSound, WorldPosition );
	}

	/// <summary>Static load per wheel from the mass centre (moment balance), then spring rates
	/// so every wheel sits at half its travel under that load.</summary>
	void SetupSuspension()
	{
		if ( body is null || wheels.Count == 0 ) return;
		var gravity = Scene.PhysicsWorld.Gravity.Length;
		var mass = body.MassOverride > 0 ? body.MassOverride : (body.Mass > 0 ? body.Mass : 1000f);
		var weight = mass * gravity;
		var fwd = ForwardAxis.Normal;
		var com = body.OverrideMassCenter ? body.MassCenterOverride : Vector3.Zero;
		var along = wheels.Select( w => Vector3.Dot( w.LocalPosition - com, fwd ) ).ToArray();
		var front = along.Max();
		var rear = along.Min();
		var span = MathF.Max( 1f, front - rear );
		var frontCount = wheels.Where( ( w, i ) => along[i] > (front + rear) * 0.5f ).Count();
		var rearCount = Math.Max( 1, wheels.Count - frontCount );
		frontCount = Math.Max( 1, frontCount );
		var frontShare = Math.Clamp( -rear / span, 0.05f, 0.95f );
		for ( var i = 0; i < wheels.Count; i++ )
		{
			var w = wheels[i];
			var isFront = along[i] > (front + rear) * 0.5f;
			w.StaticLoad = weight * (isFront ? frontShare / frontCount : (1 - frontShare) / rearCount);
			w.Stiffness = w.StaticLoad / MathF.Max( 0.5f, w.SuspensionTravel * 0.5f );
			var sprungMass = w.StaticLoad / gravity;
			w.Damping = 2f * SuspensionDampingRatio * MathF.Sqrt( w.Stiffness * sprungMass );
		}
	}

	protected override void OnFixedUpdate()
	{
		if ( body is null || IsProxy ) return;
		var dt = Time.Delta;
		if ( AcceptPlayerInput && seat is not null && seat.Occupant is not null )
		{
			Throttle = Input.AnalogMove.x;
			Steer = Input.AnalogMove.y;
			Brake = Input.Down( "Jump" ) ? 1f : 0f;
		}

		var up = WorldRotation.Up;
		var forward = WorldForward;
		Speed = Vector3.Dot( body.Velocity, forward );
		UpdateSteering( dt );

		var gravity = Scene.PhysicsWorld.Gravity.Length;
		var weight = (body.Mass > 0 ? body.Mass : body.MassOverride) * gravity;
		var power = Horsepower * HorsepowerToEngineUnits;
		var traction = TireGrip * weight;
		var drive = 0f;
		var brake = Brake * BrakeDeceleration * weight;

		if ( Throttle > 0.01f )
		{
			if ( Speed < -8f ) brake = MathF.Max( brake, Throttle * BrakeDeceleration * weight );
			else if ( Speed < MaxSpeed ) drive = Throttle * MathF.Min( power / MathF.Max( MathF.Abs( Speed ), 1f ), traction );
		}
		else if ( Throttle < -0.01f )
		{
			if ( Speed > 8f ) brake = MathF.Max( brake, -Throttle * BrakeDeceleration * weight );
			else if ( -Speed < MaxReverseSpeed ) drive = Throttle * MathF.Min( power / MathF.Max( MathF.Abs( Speed ), 1f ), traction );
		}

		var driveTotal = wheels.Sum( w => w.DriveShare );
		var brakeTotal = wheels.Sum( w => w.BrakeShare );
		foreach ( var w in wheels )
		{
			w.SteerAngle = w.Steers ? SteerAngle : 0f;
			var wd = driveTotal > 0 ? drive * w.DriveShare / driveTotal : 0f;
			var wb = brakeTotal > 0 ? brake * w.BrakeShare / brakeTotal : 0f;
			w.Step( body, forward, up, wd, wb, TireGrip, dt );
		}
	}

	void UpdateSteering( float dt )
	{
		var t = Math.Clamp( (MathF.Abs( Speed ) - SlowSpeed) / MathF.Max( 1f, FastSpeed - SlowSpeed ), 0f, 1f );
		var maxAngle = DegreesSlow + (DegreesFast - DegreesSlow) * t;
		var input = Math.Clamp( Steer, -1f, 1f );
		var target = MathF.Sign( input ) * MathF.Pow( MathF.Abs( input ), SteerExponent ) * maxAngle;
		var rate = MathF.Abs( input ) > 0.01f
			? SteerRateSlow + (SteerRateFast - SteerRateSlow) * t
			: SteerRestRateSlow + (SteerRestRateFast - SteerRestRateSlow) * t;
		var step = rate * maxAngle * dt;
		SteerAngle += Math.Clamp( target - SteerAngle, -step, step );
	}

	protected override void OnUpdate()
	{
		if ( renderer is not null )
		{
			var upModel = Vector3.Up;
			var axle = Vector3.Cross( upModel, ForwardAxis.Normal ).Normal;
			foreach ( var w in wheels )
			{
				if ( string.IsNullOrEmpty( w.BoneName ) ) continue;
				if ( !wheelBoneRest.TryGetValue( w, out var rest ) )
				{
					// capture the rest pose once the model has posed its bones (before any override)
					if ( !renderer.TryGetBoneTransform( w.BoneName, out var tx ) ) continue;
					rest = WorldTransform.ToLocal( tx );
					wheelBoneRest[w] = rest;
				}
				var spin = Rotation.FromAxis( axle, -w.SpinDegrees );
				var steer = Rotation.FromAxis( upModel, w.SteerAngle );
				var offset = w.IsGrounded ? w.Compression - w.SuspensionTravel * 0.5f : -w.SuspensionTravel * 0.5f;
				var pos = rest.Position + upModel * offset;
				renderer.SetBoneTransform( renderer.Model.Bones.GetBone( w.BoneName ), new Transform( pos, steer * spin * rest.Rotation ) );
			}
		}

		if ( engineSound.IsValid() )
		{
			engineSound.Position = WorldPosition;
			engineSound.Pitch = 0.8f + 0.8f * Math.Clamp( MathF.Abs( Speed ) / MathF.Max( 1f, MaxSpeed ), 0f, 1f );
		}
	}

	protected override void OnDestroy()
	{
		if ( engineSound.IsValid() ) engineSound.Stop();
	}
}
