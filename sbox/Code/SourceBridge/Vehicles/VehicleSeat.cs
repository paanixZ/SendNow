using System;

namespace SourceBridge.Vehicles;

/// <summary>
/// Driver seat at the original vehicle_feet_passenger0 attachment. A child GameObject named
/// "Eyes" marks vehicle_driver_eyes; while occupied, the scene camera follows it.
/// Exit places the occupant beside the vehicle (Source uses exit animations and traces; this is an
/// estimate and is reported as such).
/// </summary>
[Title( "SourceBridge Vehicle Seat" ), Category( "SourceBridge" ), Icon( "event_seat" )]
public sealed class VehicleSeat : Component
{
	[Property] public float ExitDistance { get; set; } = 48f;
	[Property] public bool DriveCamera { get; set; } = true;

	public GameObject Occupant { get; private set; }
	public GameObject Eyes => GameObject.Children.FirstOrDefault( c => c.Name == "Eyes" );

	public void Enter( GameObject who )
	{
		if ( who is null || Occupant is not null ) return;
		Occupant = who;
		who.SetParent( GameObject, false );
		who.LocalPosition = Vector3.Zero;
		who.LocalRotation = Rotation.Identity;
	}

	/// <summary>Leaves the seat; returns the exit position.</summary>
	public Vector3 Exit()
	{
		if ( Occupant is null ) return WorldPosition;
		var vehicle = GetComponentInParent<SourceBridgeVehicle>();
		var right = vehicle is not null ? Vector3.Cross( vehicle.WorldForward, WorldRotation.Up ).Normal : WorldRotation.Right;
		var side = Vector3.Dot( WorldPosition - (vehicle?.WorldPosition ?? WorldPosition), right ) >= 0 ? right : -right;
		var exit = WorldPosition + side * ExitDistance + WorldRotation.Up * 4f;
		var who = Occupant;
		Occupant = null;
		who.SetParent( null, true );
		who.WorldPosition = exit;
		return exit;
	}

	protected override void OnUpdate()
	{
		if ( !DriveCamera || Occupant is null || Scene.Camera is null ) return;
		var eyes = Eyes;
		var vehicle = GetComponentInParent<SourceBridgeVehicle>();
		if ( eyes is null || vehicle is null ) return;
		Scene.Camera.WorldPosition = eyes.WorldPosition;
		Scene.Camera.WorldRotation = Rotation.LookAt( vehicle.WorldForward, WorldRotation.Up );
	}
}
