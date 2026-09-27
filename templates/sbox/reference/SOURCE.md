# Reference files from Facepunch

Copied unchanged from https://github.com/Facepunch/sbox-public (MIT licence, engine source)
at commit `372c601f8332149851410d88f36c0184bcb988f1` (2026-09-26), plus
https://github.com/Facepunch/sbox-libwheel (MIT) at `b67f9fb5faa4d776cdaf8e2ef7648fe377066931`.

| File | Original path | Used for |
|---|---|---|
| crate01.vmdl | game/addons/citizen/Assets/models/citizen_props/crate01.vmdl | RenderMeshFile, LODGroup, MaterialGroupList, PhysicsShapeList layout |
| recyclingbin01.vmdl, oldoven.vmdl | same folder | PhysicsHullFile keys |
| materialgroups_example.vmdl | game/addons/citizen/Assets/models/citizen_human/citizen_human_female.vmdl | MaterialGroup remaps (skins) |
| citizen_bodygrouplist.vmdl_prefab | game/addons/citizen/Assets/models/citizen/prefabs/ | BodyGroup / BodyGroupChoice |
| crate01a.vmat, complex_shader_example.vmat | citizen_props / game/addons/menu/Assets/materials/light_emit_bright.vmat | .vmat layout |
| my_entity.prefab | game/templates/sandbox.addon/Assets/entity/my_entity.prefab | prefab root and Rigidbody fields |
| menu-vr.scene | game/addons/menu/Assets/scenes/menu-vr.scene | ModelRenderer, ModelCollider, Prop fields |

Generated surveys (from the same commit):

- `modeldoc_classes.json`: every `_class` and key used in all 605 `.vmdl`/`.vmdl_prefab` files.
- `complex_shader_keys.json`: every key in the 387 `complex.shader` materials.

Tests fail if SourceBridge ever emits a ModelDoc class/key, material key or prefab field that
does not occur in these real files. Update the surveys when targeting a newer s&box version.
