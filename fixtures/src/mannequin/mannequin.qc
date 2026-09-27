$modelname "sourcebridge/mannequin.mdl"
$body body "mannequin_ref.smd"
$bodygroup head
{
	studio "mannequin_head.smd"
	studio "mannequin_helmet.smd"
}
$cdmaterials "models/sourcebridge/"
$surfaceprop "flesh"
$attachment "eyes" "ValveBiped.Bip01_Head1" 5.00 0.00 5.00 rotate 0 0 0
$attachment "anim_attachment_RH" "ValveBiped.Bip01_R_Hand" 3.00 0.00 0.00 rotate 0 0 0
$hboxset "default"
$hbox 1 "ValveBiped.Bip01_Head1" -4 -4 0 4 4 9
$hbox 2 "ValveBiped.Bip01_Spine2" -4 -7 0 4 7 10
$hbox 3 "ValveBiped.Bip01_Pelvis" -4 -6 -3 4 6 4
$hbox 6 "ValveBiped.Bip01_L_Thigh" -2.5 -2.5 -17 2.5 2.5 0
$hbox 7 "ValveBiped.Bip01_R_Thigh" -2.5 -2.5 -17 2.5 2.5 0
$sequence idle "mannequin_idle.smd" loop fps 30 activity ACT_IDLE 1
$sequence walk "mannequin_walk.smd" loop fps 30 activity ACT_WALK 1
$collisionjoints "mannequin_phys.smd" {
	$mass 70
	$rootbone "ValveBiped.Bip01_Pelvis"
	$jointconstrain "ValveBiped.Bip01_Head1" x limit -20 20 0
	$jointconstrain "ValveBiped.Bip01_Head1" y limit -30 30 0
	$jointconstrain "ValveBiped.Bip01_Head1" z limit -40 40 0
	$jointconstrain "ValveBiped.Bip01_L_Forearm" x limit 0 0 0
	$jointconstrain "ValveBiped.Bip01_L_Forearm" y limit -120 0 0
	$jointconstrain "ValveBiped.Bip01_L_Forearm" z limit 0 0 0
	$jointconstrain "ValveBiped.Bip01_R_Forearm" x limit 0 0 0
	$jointconstrain "ValveBiped.Bip01_R_Forearm" y limit -120 0 0
	$jointconstrain "ValveBiped.Bip01_R_Forearm" z limit 0 0 0
	$jointconstrain "ValveBiped.Bip01_L_Calf" x limit 0 0 0
	$jointconstrain "ValveBiped.Bip01_L_Calf" y limit 0 140 0
	$jointconstrain "ValveBiped.Bip01_L_Calf" z limit 0 0 0
	$jointconstrain "ValveBiped.Bip01_R_Calf" x limit 0 0 0
	$jointconstrain "ValveBiped.Bip01_R_Calf" y limit 0 140 0
	$jointconstrain "ValveBiped.Bip01_R_Calf" z limit 0 0 0
}
