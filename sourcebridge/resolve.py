"""Dependency resolution for a Source 1 model inside an explicit mount."""

from __future__ import annotations

from dataclasses import dataclass, field

from .formats.binary import FormatError
from .formats.mdl import StudioModel, read_mdl
from .formats.phy import PhyFile, read_phy
from .formats.vtx import VtxFile, read_vtx
from .formats.vvd import VertexFile, read_vvd
from .materials import MaterialInfo, load_material
from .safety import normalize_game_path
from .sources import Mount, sha256

VTX_VARIANTS = (".dx90.vtx", ".vtx", ".dx80.vtx", ".sw.vtx")


@dataclass
class Dependency:
    kind: str
    path: str
    required_by: str
    status: str  # found | missing | optional-missing | invalid
    source: str | None = None
    original_name: str | None = None
    size: int | None = None
    sha256: str | None = None
    shadowed_in: list[str] = field(default_factory=list)
    note: str = ""


@dataclass
class ResolvedModel:
    path: str
    mdl: StudioModel | None = None
    vvd: VertexFile | None = None
    vtx: VtxFile | None = None
    phy: PhyFile | None = None
    includes: dict[str, StudioModel] = field(default_factory=dict)
    materials: dict[int, MaterialInfo] = field(default_factory=dict)  # texture index -> material
    skin_materials: dict[str, MaterialInfo] = field(default_factory=dict)  # all referenced
    textures: dict[str, bytes] = field(default_factory=dict)
    files: dict[str, bytes] = field(default_factory=dict)  # every original read, by canonical path
    deps: list[Dependency] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not any(d.status in ("missing", "invalid") for d in self.deps)


class Resolver:
    def __init__(self, mount: Mount):
        self.mount = mount

    def _fetch(self, res: ResolvedModel, kind: str, path: str, by: str, optional=False) -> bytes | None:
        path = normalize_game_path(path)
        copies = self.mount.shadowed(path)
        if not copies:
            res.deps.append(Dependency(kind, path, by, "optional-missing" if optional else "missing"))
            return None
        hit = copies[0]
        data = self.mount.read(hit)
        res.files[path] = data
        res.deps.append(
            Dependency(
                kind,
                path,
                by,
                "found",
                hit.source,
                hit.original_name,
                len(data),
                sha256(data),
                [c.source for c in copies[1:]],
            )
        )
        return data

    def _invalid(self, res: ResolvedModel, path: str, exc: Exception) -> None:
        for d in res.deps:
            if d.path == path:
                d.status = "invalid"
                d.note = str(exc)
        res.problems.append(f"{path}: {exc}")

    def resolve_model(self, path: str) -> ResolvedModel:
        path = normalize_game_path(path)
        res = ResolvedModel(path)
        data = self._fetch(res, "model", path, "(input)")
        if data is None:
            res.problems.append(f"{path}: not found in any source")
            return res
        try:
            res.mdl = read_mdl(data)
        except FormatError as exc:
            self._invalid(res, path, exc)
            return res
        stem = path[:-4]
        vvd = self._fetch(res, "vertex-data", stem + ".vvd", path)
        if vvd is not None:
            try:
                res.vvd = read_vvd(vvd)
                if res.vvd.checksum != res.mdl.checksum:
                    raise FormatError(f"checksum {res.vvd.checksum} does not match model {res.mdl.checksum}")
            except FormatError as exc:
                self._invalid(res, stem + ".vvd", exc)
                res.vvd = None
        vtx_path = next((stem + v for v in VTX_VARIANTS if self.mount.find(stem + v)), None)
        if vtx_path is None:
            res.deps.append(
                Dependency(
                    "mesh-data", stem + ".dx90.vtx", path, "missing", note="tried " + ", ".join(VTX_VARIANTS)
                )
            )
        else:
            raw = self._fetch(res, "mesh-data", vtx_path, path)
            try:
                res.vtx = read_vtx(raw)
                if res.vtx.checksum != res.mdl.checksum:
                    raise FormatError(f"checksum {res.vtx.checksum} does not match model {res.mdl.checksum}")
            except FormatError as exc:
                self._invalid(res, vtx_path, exc)
                res.vtx = None
        phy = self._fetch(res, "collision", stem + ".phy", path, optional=True)
        if phy is not None:
            try:
                res.phy = read_phy(phy)
                if res.phy.checksum != res.mdl.checksum:
                    raise FormatError(f"checksum {res.phy.checksum} does not match model {res.mdl.checksum}")
            except FormatError as exc:
                self._invalid(res, stem + ".phy", exc)
                res.phy = None
        if res.mdl.anim_block_name:
            self._fetch(res, "animation-block", res.mdl.anim_block_name, path)
        for inc in res.mdl.include_models:
            inc_path = normalize_game_path(inc)
            raw = self._fetch(res, "include-model", inc_path, path)
            if raw is not None:
                try:
                    res.includes[inc_path] = read_mdl(raw)
                except FormatError as exc:
                    self._invalid(res, inc_path, exc)
        self._resolve_materials(res)
        return res

    def _resolve_materials(self, res: ResolvedModel) -> None:
        mdl = res.mdl
        cds = mdl.cd_textures or [""]
        for ti, tex in enumerate(mdl.textures):
            candidates = []
            for cd in cds:
                cd_n = cd.replace("\\", "/").strip("/").lower()
                tex_n = tex.replace("\\", "/").lstrip("/").lower()
                candidates.append(f"materials/{cd_n}/{tex_n}.vmt" if cd_n else f"materials/{tex_n}.vmt")
            found = next((c for c in candidates if self.mount.find(c)), None)
            if found is None:
                res.deps.append(
                    Dependency(
                        "material",
                        candidates[0],
                        res.path,
                        "missing",
                        note="searched: " + ", ".join(candidates),
                    )
                )
                continue
            self._fetch(res, "material", found, res.path)
            info = load_material(self.mount, found)
            for inc in info.includes:
                self._fetch(res, "material-include", inc, found)
            if info.error:
                self._invalid(res, found, ValueError(info.error))
            res.materials[ti] = info
            res.skin_materials[found] = info
            for param, tex_path in info.textures.items():
                if tex_path in res.textures:
                    continue
                optional = param not in ("$basetexture", "$bumpmap", "$normalmap")
                raw = self._fetch(res, f"texture:{param}", tex_path, found, optional=optional)
                if raw is not None:
                    res.textures[tex_path] = raw
