-- SourceBridge test vehicle (MIT). Standard Source vehicle, no framework.
sound.Add( {
	name = "SB_Buggy.EngineIdle",
	channel = CHAN_STATIC,
	volume = 0.8,
	level = 80,
	pitch = { 95, 105 },
	sound = "vehicles/sb_buggy/engine_idle.wav"
} )

list.Set( "Vehicles", "sb_buggy", {
	Name = "SourceBridge Buggy",
	Model = "models/sourcebridge/sb_buggy.mdl",
	Class = "prop_vehicle_jeep",
	Category = "SourceBridge",
	Author = "SourceBridge",
	Information = "Test vehicle for SourceBridge",
	KeyValues = {
		vehiclescript = "scripts/vehicles/sb_buggy.txt"
	}
} )
