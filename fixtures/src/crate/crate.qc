$modelname "sourcebridge/crate.mdl"
$staticprop
$body body "crate_ref.smd"
$cdmaterials "models/sourcebridge/"
$texturegroup skinfamilies
{
	{ "crate" }
	{ "crate_dark" }
}
$surfaceprop "wood_crate"
$keyvalues
{
	prop_data
	{
		"base" "Wooden.Medium"
	}
}
$sequence idle "crate_idle.smd"
$collisionmodel "crate_phys.smd" {
	$mass 40
}
