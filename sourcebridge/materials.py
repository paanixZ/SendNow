"""Source 1 materials (.vmt/.vtf): resolution, texture decoding and mapping to s&box .vmat.

The mapping only uses shader parameters that appear in Facepunch's own shipped materials
(see templates/sbox/reference and docs/decisions.md). Everything that has no equivalent is
reported, never silently dropped: the original VMT/VTF stay in the archive.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

import srctools.vmt as vmt

from .journal import Journal
from .sources import Hit, Mount

# VMT parameters that reference textures (VarType.TEXTURE in srctools plus a few common ones).
TEXTURE_PARAMS_EXTRA = {"$iris", "$corneatexture", "$ambientoccltexture", "$lightwarptexture"}

# Parameters this mapping understands. Everything else is listed as not transferred.
HANDLED = {
    "$basetexture", "$bumpmap", "$normalmap", "$translucent", "$alphatest", "$alphatestreference",
    "$nocull", "$color", "$color2", "$selfillum", "$selfillummask", "$surfaceprop", "$model",
    "$additive", "$alpha", "$basetexturetransform", "$halflambert",
}  # fmt: skip


@dataclass
class MaterialInfo:
    path: str  # canonical materials/... .vmt path
    hit: Hit | None
    shader: str
    params: dict[str, str]
    textures: dict[str, str]  # param -> canonical .vtf path
    includes: list[str] = field(default_factory=list)
    error: str | None = None


def texture_params(params: dict[str, str]) -> dict[str, str]:
    out = {}
    for k, v in params.items():
        if not v:
            continue
        t = vmt.get_parm_type(k)
        if (t is not None and t.name == "TEXTURE") or k in TEXTURE_PARAMS_EXTRA:
            if v.lower().startswith("_rt_") or v.lower() == "env_cubemap":
                continue
            p = v.replace("\\", "/").lower()
            if p.endswith(".vtf"):
                p = p[:-4]
            out[k] = f"materials/{p}.vtf"
    return out


def load_material(mount: Mount, path: str, depth: int = 0) -> MaterialInfo:
    hit = mount.find(path)
    if hit is None:
        return MaterialInfo(path, None, "", {}, {}, error="missing")
    text = mount.read(hit).decode("utf-8", "replace")
    try:
        mat = vmt.Material.parse(io.StringIO(text), path)
    except Exception as exc:  # srctools raises several tokenizer error types
        return MaterialInfo(path, hit, "", {}, {}, error=f"unparseable VMT: {exc}")
    params = {k.lower(): v for k, v in mat.items()}
    shader = mat.shader
    includes = []
    if shader.lower() == "patch":
        inc = params.pop("include", "")
        if not inc or depth > 8:
            return MaterialInfo(
                path, hit, shader, params, {}, error="patch material without resolvable include"
            )
        base = load_material(mount, inc.replace("\\", "/").lower(), depth + 1)
        includes = [base.path, *base.includes]
        if base.error:
            return MaterialInfo(
                path, hit, shader, params, {}, includes, error=f"patch base {base.path}: {base.error}"
            )
        merged = dict(base.params)
        for block in mat.blocks:
            name = block.real_name.lower()
            for kv in block:
                key = kv.real_name.lower()
                if name == "insert" or (name == "replace" and key in merged):
                    merged[key] = kv.value
        params, shader = merged, base.shader
    return MaterialInfo(path, hit, shader, params, texture_params(params), includes)


def decode_vtf(data: bytes) -> tuple[int, int, bytes, dict]:
    """VTF -> (width, height, RGBA8888 of mip 0, info)."""
    from sourcepp import vtfpp

    v = vtfpp.VTF(data)
    if not v.has_image_data:
        raise ValueError("VTF has no image data")
    rgba = v.get_image_data_as_rgba8888(0, 0, 0, 0)
    info = {
        "format": v.format.name,
        "width": v.width,
        "height": v.height,
        "mips": v.mip_count,
        "frames": v.frame_count,
        "faces": v.face_count,
        "flags": int(v.flags),
        "version": v.version,
    }
    return v.width, v.height, bytes(rgba), info


def encode_png(width: int, height: int, rgba: bytes) -> bytes:
    from sourcepp import vtfpp

    return bytes(
        vtfpp.ImageConversion.convert_image_data_to_file(
            rgba, vtfpp.ImageFormat.RGBA8888, width, height, vtfpp.ImageConversion.FileFormat.PNG
        )
    )


def alpha_as_gray(rgba: bytes) -> bytes:
    a = rgba[3::4]
    out = bytearray(len(rgba))
    out[0::4] = a
    out[1::4] = a
    out[2::4] = a
    out[3::4] = b"\xff" * len(a)
    return bytes(out)


def has_meaningful_alpha(rgba: bytes) -> bool:
    return any(b != 255 for b in rgba[3::4])


def _flag(params: dict[str, str], key: str) -> bool:
    v = params.get(key, "0").strip()
    try:
        return float(v) != 0
    except ValueError:
        return False


def _vec(value: str) -> tuple[float, float, float] | None:
    s = value.strip().strip("[]{}").split()
    try:
        vals = [float(x) for x in s]
    except ValueError:
        return None
    if len(vals) == 1:
        vals *= 3
    if len(vals) != 3:
        return None
    if value.strip().startswith("{"):
        vals = [x / 255.0 for x in vals]
    return (vals[0], vals[1], vals[2])


def build_vmat(
    info: MaterialInfo,
    texture_paths: dict[str, str],
    journal: Journal,
    subject: str,
) -> str:
    """Create a complex.shader .vmat. texture_paths maps role -> Assets-relative PNG path."""
    p = info.params
    shader = info.shader.lower()
    lines = ['"Layer0"', "{", '\t"shader"\t\t"shaders/complex.shader"']

    def put(key: str, value: str) -> None:
        lines.append(f'\t"{key}"\t\t"{value}"')

    if shader not in ("vertexlitgeneric", "unlitgeneric", "lightmappedgeneric", "worldvertextransition"):
        journal.approximated(subject, "shader", f"{info.shader} has no mapping; rendered as complex.shader")
    else:
        journal.converted(subject, "shader", f"{info.shader} -> shaders/complex.shader")
    if shader == "unlitgeneric":
        put("F_UNLIT", "1")

    if "color" in texture_paths:
        put("TextureColor", texture_paths["color"])
        journal.preserved(subject, "$basetexture", "decoded VTF mip 0 to PNG without resampling")
    else:
        put("TextureColor", "[1.000000 1.000000 1.000000 0.000000]")
        journal.approximated(subject, "$basetexture", "no base texture available; white placeholder")
    if "normal" in texture_paths:
        put("TextureNormal", texture_paths["normal"])
        journal.approximated(
            subject,
            "$bumpmap",
            "normal map copied unchanged; Source 1 vs s&box green-channel convention is not "
            "verified yet (check the comparison render)",
        )
    tint = (
        _vec(p.get("$color2", "") or p.get("$color", "")) if (p.get("$color2") or p.get("$color")) else None
    )
    if tint:
        put("g_vColorTint", f"[{tint[0]:.6f} {tint[1]:.6f} {tint[2]:.6f} 0.000000]")
        put("g_flModelTintAmount", "1.000")
        journal.converted(subject, "$color/$color2", "mapped to g_vColorTint")

    if _flag(p, "$translucent") or _flag(p, "$additive"):
        put("F_TRANSLUCENT", "1")
        if "translucency" in texture_paths:
            put("TextureTranslucency", texture_paths["translucency"])
        journal.converted(subject, "$translucent", "F_TRANSLUCENT with base alpha as TextureTranslucency")
        if _flag(p, "$additive"):
            journal.approximated(
                subject, "$additive", "additive blending has no direct equivalent; translucent"
            )
    elif _flag(p, "$alphatest"):
        put("F_ALPHA_TEST", "1")
        if "translucency" in texture_paths:
            put("TextureTranslucency", texture_paths["translucency"])
        ref = p.get("$alphatestreference")
        if ref is None:
            put("g_flAlphaTestReference", "0.500")
            journal.estimated(subject, "$alphatestreference", "not set in VMT; 0.5 assumed")
        else:
            put("g_flAlphaTestReference", f"{float(ref):.3f}")
            journal.converted(subject, "$alphatestreference", "mapped to g_flAlphaTestReference")
    if _flag(p, "$nocull"):
        put("F_RENDER_BACKFACES", "1")
        journal.converted(subject, "$nocull", "F_RENDER_BACKFACES")
    if _flag(p, "$selfillum"):
        put("F_SELF_ILLUM", "1")
        if "selfillum" in texture_paths:
            put("TextureSelfIllumMask", texture_paths["selfillum"])
        journal.approximated(subject, "$selfillum", "F_SELF_ILLUM; brightness differs from Source 1")

    put("TextureRoughness", "[0.700000 0.700000 0.700000 0.000000]")
    put("g_flMetalness", "0.000")
    journal.generated(
        subject, "roughness/metalness", "Source 1 has no PBR inputs; neutral defaults (0.7 rough, 0 metal)"
    )
    for key in sorted(p):
        if key not in HANDLED and not key.startswith("%"):
            journal.lost(subject, key, f"'{p[key]}' has no s&box mapping yet (original VMT archived)")
    surface = p.get("$surfaceprop")
    lines.append('\t"SystemAttributes"')
    lines.append("\t{")
    if surface:
        lines.append(f'\t\t"PhysicsSurfaceProperties"\t\t"{surface}"')
        journal.approximated(
            subject, "$surfaceprop", f"'{surface}' passed through; s&box surface names may differ"
        )
    lines.append("\t}")
    lines.append("}")
    return "\n".join(lines) + "\n"
