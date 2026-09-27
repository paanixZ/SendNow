$modelname "sourcebridge/sb_buggy.mdl"
$body body "sb_buggy_ref.smd"
$cdmaterials "models/sourcebridge/"
$surfaceprop "metalvehicle"
$attachment "wheel_fl" "wheel_fl" 0 0 0 rotate 0 0 0
$attachment "wheel_fr" "wheel_fr" 0 0 0 rotate 0 0 0
$attachment "wheel_rl" "wheel_rl" 0 0 0 rotate 0 0 0
$attachment "wheel_rr" "wheel_rr" 0 0 0 rotate 0 0 0
$attachment "vehicle_driver_eyes" "body" -4.0 12.0 44.0 rotate 0 0 0
$attachment "vehicle_feet_passenger0" "body" -4.0 12.0 16.0 rotate 0 0 0
$attachment "vehicle_engine" "body" 36 0 24 rotate 0 0 0
$sequence idle "sb_buggy_idle.smd" fps 30
$collisionmodel "sb_buggy_phys.smd" {
	$concave
	$mass 800
}
