"""Garry's Mod / Source vehicles: definitions, vehicle scripts, sounds -> VehicleDoc.

Adapter "gmod-standard-vehicle" v1 covers vehicles defined with list.Set( "Vehicles", ... )
(directly or through a local helper like base_vehicles.lua) that use a Source vehicle script
(prop_vehicle_jeep / _airboat / _prisoner_pod). Frameworks such as simfphys or LVS are detected
and reported, not converted.

Lua is never executed. Table literals are read statically; anything computed at runtime
(variables, concatenation, function calls) is reported as "dynamic, not evaluated".
Every VehicleDoc value records its unit and whether it is original, derived or estimated.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

from srctools.keyvalues import Keyvalues

from .safety import normalize_game_path
from .sources import Mount

ADAPTER = {"name": "gmod-standard-vehicle", "version": 1}
MPH_TO_INCHES_PER_SECOND = 17.6  # 1 mph = 5280 * 12 / 3600 in/s
WHEEL_ATTACHMENTS = ("wheel_fl", "wheel_fr", "wheel_rl", "wheel_rr")
FRAMEWORK_MARKERS = {
    "simfphys": re.compile(r"simfphys", re.I),
    "lvs": re.compile(r"\bLVS\b|lvs_base", re.I),
    "wac": re.compile(r"\bwac_", re.I),
    "scars": re.compile(r"\bscar_|SCars", re.I),
}


class LuaParseError(ValueError):
    pass


# ------------------------------------------------------------------ static Lua table reader


_TOKEN = re.compile(
    r"""(?P<ws>\s+)|(?P<comment>--\[(?P<eq>=*)\[.*?\](?P=eq)\]|--[^\n]*)|(?P<str>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\[(?P<eq2>=*)\[.*?\](?P=eq2)\])|(?P<num>0[xX][0-9a-fA-F]+|\d+\.?\d*(?:[eE][-+]?\d+)?|\.\d+)|(?P<name>[A-Za-z_][A-Za-z0-9_]*)|(?P<op>\.\.|==|~=|<=|>=|[{}()\[\],;=.:+\-*/#<>%^])""",
    re.S,
)


@dataclass
class Tok:
    kind: str
    value: str
    line: int


def tokenize(src: str) -> list[Tok]:
    out = []
    pos = 0
    line = 1
    while pos < len(src):
        m = _TOKEN.match(src, pos)
        if not m:
            raise LuaParseError(f"unexpected character {src[pos]!r} at line {line}")
        text = m.group(0)
        kind = m.lastgroup if m.lastgroup not in ("eq", "eq2") else "str"
        for g in ("ws", "comment", "str", "num", "name", "op"):
            if m.group(g) is not None:
                kind = g
                break
        if kind not in ("ws", "comment"):
            out.append(Tok(kind, text, line))
        line += text.count("\n")
        pos = m.end()
    return out


class Dynamic:
    """A value that can only be known by running the Lua code."""

    def __init__(self, text: str):
        self.text = text

    def __repr__(self):
        return f"<dynamic {self.text}>"


def _unquote(s: str) -> str:
    if s.startswith("["):
        return s[s.index("[", 1) + 1 : s.rindex("]", 0, len(s) - 1)]
    body = s[1:-1]
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), body)


class _Parser:
    def __init__(self, toks: list[Tok]):
        self.t = toks
        self.i = 0

    def peek(self, k=0):
        j = self.i + k
        return self.t[j] if j < len(self.t) else Tok("eof", "", -1)

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def expect(self, value):
        tok = self.take()
        if tok.value != value:
            raise LuaParseError(f"expected {value!r} at line {tok.line}, got {tok.value!r}")
        return tok

    def value(self):
        tok = self.peek()
        start = self.i
        if tok.value == "{":
            v = self.table()
        elif tok.kind == "str":
            self.take()
            v = _unquote(tok.value)
        elif tok.kind == "num":
            self.take()
            v = float(int(tok.value, 16)) if tok.value.lower().startswith("0x") else float(tok.value)
        elif tok.value in ("true", "false"):
            self.take()
            v = tok.value == "true"
        elif tok.value == "nil":
            self.take()
            v = None
        elif tok.value == "-" and self.peek(1).kind == "num":
            self.take()
            v = -float(self.take().value)
        else:
            v = Dynamic(self._skip_expression())
            return v
        # anything that continues the expression (concatenation, arithmetic, calls) is dynamic
        if self.peek().value in ("..", "+", "-", "*", "/", "(", ".", ":", "["):
            rest = self._skip_expression()
            text = " ".join(t.value for t in self.t[start : self.i])
            return Dynamic(text or rest)
        return v

    def _skip_expression(self) -> str:
        depth = 0
        start = self.i
        while True:
            tok = self.peek()
            if tok.kind == "eof":
                break
            if tok.value in ("{", "(", "["):
                depth += 1
            elif tok.value in ("}", ")", "]"):
                if depth == 0:
                    break
                depth -= 1
            elif tok.value in (",", ";") and depth == 0:
                break
            self.take()
        return " ".join(t.value for t in self.t[start : self.i])

    def table(self):
        self.expect("{")
        out: dict = {}
        n = 1
        while self.peek().value != "}":
            tok = self.peek()
            if tok.value == "[":
                self.take()
                key = self.value()
                self.expect("]")
                self.expect("=")
                out[key if not isinstance(key, Dynamic) else repr(key)] = self.value()
            elif tok.kind == "name" and self.peek(1).value == "=":
                self.take()
                self.take()
                out[tok.value] = self.value()
            else:
                out[n] = self.value()
                n += 1
            if self.peek().value in (",", ";"):
                self.take()
            elif self.peek().value != "}":
                raise LuaParseError(f"expected ',' or '}}' at line {self.peek().line}")
        self.expect("}")
        return out


def _calls(toks: list[Tok], name_parts: tuple[str, ...]):
    """Yield (index of '(', line) for calls like list.Set( or sound.Add( or a local helper name."""
    n = len(name_parts)
    for i in range(len(toks) - (2 * n)):
        seq = [toks[i + 2 * k].value for k in range(n)]
        dots = [toks[i + 2 * k + 1].value for k in range(n - 1)]
        if (
            seq == list(name_parts)
            and all(d in (".", ":") for d in dots)
            and toks[i + 2 * n - 1].value == "("
        ):
            if i > 0 and toks[i - 1].value in (".", ":"):
                continue
            yield i + 2 * n - 1, toks[i].line


def _args(toks: list[Tok], open_idx: int) -> list:
    p = _Parser(toks)
    p.i = open_idx + 1
    args = []
    while p.peek().value != ")":
        args.append(p.value())
        if p.peek().value == ",":
            p.take()
        elif p.peek().value != ")":
            raise LuaParseError(f"unexpected {p.peek().value!r} in call at line {p.peek().line}")
    return args


@dataclass
class VehicleDefinition:
    id: str
    table: dict
    source_file: str
    line: int
    dynamic: list[str] = field(default_factory=list)

    def get(self, key, default=None):
        v = self.table.get(key, default)
        return None if isinstance(v, Dynamic) else v

    @property
    def model(self) -> str | None:
        m = self.get("Model")
        return normalize_game_path(m) if isinstance(m, str) else None

    @property
    def script(self) -> str | None:
        kv = self.get("KeyValues") or {}
        s = kv.get("vehiclescript") if isinstance(kv, dict) else None
        return normalize_game_path(s) if isinstance(s, str) else None


def _dynamic_fields(t: dict, prefix="") -> list[str]:
    out = []
    for k, v in t.items():
        if isinstance(v, Dynamic):
            out.append(f"{prefix}{k} = {v.text}")
        elif isinstance(v, dict):
            out += _dynamic_fields(v, f"{prefix}{k}.")
    return out


def find_vehicle_definitions(lua_path: str, src: str) -> list[VehicleDefinition]:
    toks = tokenize(src)
    defs = []
    # helpers: local function Name( t, class ) ... list.Set( "Vehicles", class, t )
    helpers: dict[str, tuple[int, int]] = {}
    for i in range(len(toks) - 3):
        if toks[i].value == "function" and toks[i + 1].kind == "name" and toks[i + 2].value == "(":
            name = toks[i + 1].value
            j = i + 3
            params = []
            while toks[j].value != ")":
                if toks[j].kind == "name":
                    params.append(toks[j].value)
                j += 1
            k = j
            while k < len(toks) and toks[k].value != "end":
                if toks[k].value == "list" and toks[k + 2].value == "Set" and toks[k + 3].value == "(":
                    a = [t.value for t in toks[k + 4 : k + 9]]
                    if a[0] in ('"Vehicles"', "'Vehicles'") and a[2] in params and a[4] in params:
                        helpers[name] = (params.index(a[4]), params.index(a[2]))
                k += 1
    for open_idx, line in _calls(toks, ("list", "Set")):
        args = _args(toks, open_idx)
        if len(args) >= 3 and args[0] == "Vehicles" and isinstance(args[2], dict):
            vid = args[1] if isinstance(args[1], str) else repr(args[1])
            defs.append(VehicleDefinition(vid, args[2], lua_path, line, _dynamic_fields(args[2])))
    for helper, (table_idx, id_idx) in helpers.items():
        for open_idx, line in _calls(toks, (helper,)):
            args = _args(toks, open_idx)
            if len(args) > max(table_idx, id_idx) and isinstance(args[table_idx], dict):
                vid = args[id_idx] if isinstance(args[id_idx], str) else repr(args[id_idx])
                defs.append(
                    VehicleDefinition(vid, args[table_idx], lua_path, line, _dynamic_fields(args[table_idx]))
                )
    return defs


def find_sounds(lua_path: str, src: str) -> dict[str, dict]:
    """sound.Add( { name = ..., sound = ... } ) definitions."""
    out = {}
    toks = tokenize(src)
    for open_idx, line in _calls(toks, ("sound", "Add")):
        args = _args(toks, open_idx)
        if args and isinstance(args[0], dict) and isinstance(args[0].get("name"), str):
            t = args[0]
            snd = t.get("sound")
            files = (
                [snd]
                if isinstance(snd, str)
                else [v for v in snd.values() if isinstance(v, str)]
                if isinstance(snd, dict)
                else []
            )
            out[t["name"]] = {
                "files": files,
                "volume": t.get("volume") if not isinstance(t.get("volume"), Dynamic) else None,
                "level": t.get("level") if not isinstance(t.get("level"), Dynamic) else None,
                "pitch": _range(t.get("pitch")),
                "channel": t["channel"].text if isinstance(t.get("channel"), Dynamic) else t.get("channel"),
                "source": f"{lua_path}:{line}",
            }
    return out


def _range(v):
    if isinstance(v, (int, float)):
        return [float(v), float(v)]
    if isinstance(v, dict):
        vals = [x for x in v.values() if isinstance(x, (int, float))]
        return vals[:2] if vals else None
    return None


def find_soundscripts(path: str, text: str) -> dict[str, dict]:
    """KeyValues soundscripts (scripts/game_sounds*.txt): "Name" { "wave" "..." }."""
    out = {}
    try:
        kv = Keyvalues.parse(io.StringIO(text), path)
    except Exception:
        return out
    for entry in kv:
        if not entry.has_children():
            continue
        waves = [c.value for c in entry.find_all("wave")]
        for rnd in entry.find_all("rndwave"):
            waves += [c.value for c in rnd.find_all("wave")]
        if waves:
            out[entry.real_name] = {
                "files": [w.lstrip("*#@<>^)}$!?").replace("\\", "/") for w in waves],
                "volume": entry["volume", None],
                "level": entry["soundlevel", None],
                "pitch": entry["pitch", None],
                "channel": entry["channel", None],
                "source": path,
            }
    return out


# ------------------------------------------------------------------ vehicle script


def parse_script(text: str, path: str) -> Keyvalues:
    return Keyvalues.parse(io.StringIO(text), path)


def _num(kv: Keyvalues, key: str) -> float | None:
    try:
        return float(kv[key])
    except (LookupError, ValueError):
        return None


def _vec(s: str | None):
    if not s:
        return None
    parts = s.split()
    try:
        return [float(x) for x in parts[:3]] if len(parts) >= 3 else None
    except ValueError:
        return None


def V(value, unit: str, source: str, origin: str = "original", note: str = "") -> dict:
    d = {"value": value, "unit": unit, "source": source, "origin": origin}
    if note:
        d["note"] = note
    return d


def kv_to_json(kv: Keyvalues):
    """Lossless structure: list of [key, value | children] preserving order and duplicates."""
    if kv.has_children():
        return [[c.real_name, kv_to_json(c)] for c in kv]
    return kv.value


def build_vehicle_doc(
    definition: VehicleDefinition,
    script_path: str,
    script: Keyvalues,
    attachments: dict[str, tuple[float, float, float]],
    sounds: dict[str, dict],
    has_phy: bool,
) -> dict:
    """attachments: attachment name -> position in the exported (engine rest) model space."""
    root = script.find_key("vehicle", or_blank=True)
    body = root.find_key("body", or_blank=True)
    engine = root.find_key("engine", or_blank=True)
    steering = root.find_key("steering", or_blank=True)
    axles = list(root.find_all("axle"))
    src = script_path
    doc: dict = {
        "adapter": ADAPTER,
        "definition": {
            "id": definition.id,
            "name": definition.get("Name"),
            "class": definition.get("Class"),
            "category": definition.get("Category"),
            "author": definition.get("Author"),
            "information": definition.get("Information"),
            "model": definition.model,
            "script": definition.script,
            "defined_in": f"{definition.source_file}:{definition.line}",
            "dynamic_fields": definition.dynamic,
        },
        "script": {"path": script_path, "raw": kv_to_json(script)},
        "problems": [],
    }
    cls = (definition.get("Class") or "").lower()
    if cls not in ("prop_vehicle_jeep", "prop_vehicle_jeep_old", "prop_vehicle_airboat"):
        doc["problems"].append(
            f"class {cls or '?'} is not a wheeled Source vehicle; drivable conversion not supported"
        )

    # body
    mass = _num(body, "massoverride")
    doc["body"] = {
        "mass": V(mass, "kg", f"{src}:vehicle.body.massoverride")
        if mass
        else V(None, "kg", "model .phy", "original", "no override; the .phy mass applies"),
        "mass_center_offset": V(
            _vec(body["massCenterOverride", None]), "in", f"{src}:vehicle.body.massCenterOverride"
        ),
        "add_gravity": V(_num(body, "addgravity"), "g fraction", f"{src}:vehicle.body.addgravity"),
        "counter_torque_factor": V(
            _num(body, "countertorquefactor"), "factor", f"{src}:vehicle.body.countertorquefactor"
        ),
        "max_angular_velocity": V(
            _num(body, "maxAngularVelocity"), "deg/s", f"{src}:vehicle.body.maxAngularVelocity"
        ),
    }

    # engine
    gears = [float(g.value) for g in engine.find_all("gear")]
    maxspeed = _num(engine, "maxspeed")
    maxrev = _num(engine, "maxReverseSpeed")
    doc["engine"] = {
        "horsepower": V(_num(engine, "horsepower"), "hp", f"{src}:vehicle.engine.horsepower"),
        "max_rpm": V(_num(engine, "maxrpm"), "rpm", f"{src}:vehicle.engine.maxrpm"),
        "max_speed": V(
            maxspeed * MPH_TO_INCHES_PER_SECOND if maxspeed else None,
            "in/s",
            f"{src}:vehicle.engine.maxspeed",
            "derived",
            f"{maxspeed} mph",
        ),
        "max_reverse_speed": V(
            maxrev * MPH_TO_INCHES_PER_SECOND if maxrev else None,
            "in/s",
            f"{src}:vehicle.engine.maxReverseSpeed",
            "derived",
            f"{maxrev} mph",
        ),
        "axle_ratio": V(_num(engine, "axleratio"), "ratio", f"{src}:vehicle.engine.axleratio"),
        "gears": V(gears, "ratio", f"{src}:vehicle.engine.gear"),
        "automatic": V(
            engine["autotransmission", "0"] != "0", "bool", f"{src}:vehicle.engine.autotransmission"
        ),
        "shift_up_rpm": V(_num(engine, "shiftuprpm"), "rpm", f"{src}:vehicle.engine.shiftuprpm"),
        "shift_down_rpm": V(_num(engine, "shiftdownrpm"), "rpm", f"{src}:vehicle.engine.shiftdownrpm"),
        "boost": kv_to_json(engine.find_key("boost", or_blank=True)) or None,
    }

    # steering
    slow = _num(steering, "slowcarspeed")
    fast = _num(steering, "fastcarspeed")
    doc["steering"] = {
        "degrees_slow": V(_num(steering, "degreesSlow"), "deg", f"{src}:vehicle.steering.degreesSlow"),
        "degrees_fast": V(_num(steering, "degreesFast"), "deg", f"{src}:vehicle.steering.degreesFast"),
        "slow_speed": V(
            slow * MPH_TO_INCHES_PER_SECOND if slow else None,
            "in/s",
            f"{src}:vehicle.steering.slowcarspeed",
            "derived",
            f"{slow} mph",
        ),
        "fast_speed": V(
            fast * MPH_TO_INCHES_PER_SECOND if fast else None,
            "in/s",
            f"{src}:vehicle.steering.fastcarspeed",
            "derived",
            f"{fast} mph",
        ),
        "rate_slow": V(
            _num(steering, "slowSteeringRate"),
            "1/s",
            f"{src}:vehicle.steering.slowSteeringRate",
            "original",
            "interpreted as full lock per second",
        ),
        "rate_fast": V(
            _num(steering, "fastSteeringRate"),
            "1/s",
            f"{src}:vehicle.steering.fastSteeringRate",
            "original",
            "interpreted as full lock per second",
        ),
        "rest_rate_slow": V(
            _num(steering, "steeringRestRateSlow"), "1/s", f"{src}:vehicle.steering.steeringRestRateSlow"
        ),
        "rest_rate_fast": V(
            _num(steering, "steeringRestRateFast"), "1/s", f"{src}:vehicle.steering.steeringRestRateFast"
        ),
        "exponent": V(
            _num(steering, "steeringExponent"), "exponent", f"{src}:vehicle.steering.steeringExponent"
        ),
        "skid_allowed": V(steering["skidallowed", "0"] != "0", "bool", f"{src}:vehicle.steering.skidallowed"),
    }

    # axles + wheels (positions from the model's wheel attachments, like CFourWheelVehiclePhysics::CalcWheelData)
    wheels = []
    doc["axles"] = []
    for ai, axle in enumerate(axles):
        w = axle.find_key("wheel", or_blank=True)
        s = axle.find_key("suspension", or_blank=True)
        base = f"{src}:vehicle.axle[{ai}]"
        doc["axles"].append(
            {
                "radius": V(_num(w, "radius"), "in", f"{base}.wheel.radius"),
                "wheel_mass": V(_num(w, "mass"), "kg", f"{base}.wheel.mass"),
                "tire_material": V(w["material", None], "surfaceprop", f"{base}.wheel.material"),
                "spring_constant": V(
                    _num(s, "springConstant"), "vphysics", f"{base}.suspension.springConstant"
                ),
                "spring_damping": V(_num(s, "springDamping"), "vphysics", f"{base}.suspension.springDamping"),
                "spring_damping_compression": V(
                    _num(s, "springDampingCompression"),
                    "vphysics",
                    f"{base}.suspension.springDampingCompression",
                ),
                "stabilizer": V(
                    _num(s, "stabilizerConstant"), "vphysics", f"{base}.suspension.stabilizerConstant"
                ),
                "max_body_force": V(_num(s, "maxBodyForce"), "vphysics", f"{base}.suspension.maxBodyForce"),
                "torque_factor": V(_num(axle, "torquefactor"), "share", f"{base}.torquefactor"),
                "brake_factor": V(_num(axle, "brakefactor"), "share", f"{base}.brakefactor"),
            }
        )
    for ai, (left, right) in enumerate((("wheel_fl", "wheel_fr"), ("wheel_rl", "wheel_rr"))):
        if ai >= len(axles):
            break
        for name in (left, right):
            pos = attachments.get(name)
            if pos is None:
                doc["problems"].append(
                    f"model has no attachment '{name}'; the Source engine cannot place this wheel either"
                )
                continue
            wheels.append(
                {
                    "name": name,
                    "bone_hint": name,
                    "axle": ai,
                    "position": V(
                        list(pos),
                        "in",
                        f"model attachment {name}",
                        "original",
                        "engine rest pose, model space",
                    ),
                    "steers": V(
                        ai == 0, "bool", "Source four-wheel vehicles steer the first axle", "derived"
                    ),
                }
            )
    doc["wheels"] = wheels
    front = [w["position"]["value"] for w in wheels if w["axle"] == 0]
    rear = [w["position"]["value"] for w in wheels if w["axle"] == 1]
    if len(front) == 2 and len(rear) == 2:
        fc = [(front[0][k] + front[1][k]) / 2 for k in range(3)]
        rc = [(rear[0][k] + rear[1][k]) / 2 for k in range(3)]
        fwd = [fc[k] - rc[k] for k in range(3)]
        ln = sum(x * x for x in fwd) ** 0.5 or 1.0
        doc["forward_axis"] = V([x / ln for x in fwd], "unit vector", "rear axle -> front axle", "derived")
        doc["wheelbase"] = V(ln, "in", "rear axle -> front axle", "derived")
        doc["track_width"] = V(
            sum((front[0][k] - front[1][k]) ** 2 for k in range(3)) ** 0.5,
            "in",
            "front wheel attachments",
            "derived",
        )
    else:
        doc["problems"].append("need wheel_fl/fr/rl/rr attachments to derive driving direction")

    # seat, camera, exit
    doc["seat"] = {
        "feet": V(
            list(attachments["vehicle_feet_passenger0"]), "in", "model attachment vehicle_feet_passenger0"
        )
        if "vehicle_feet_passenger0" in attachments
        else V(None, "in", "missing", "estimated"),
        "eyes": V(list(attachments["vehicle_driver_eyes"]), "in", "model attachment vehicle_driver_eyes")
        if "vehicle_driver_eyes" in attachments
        else V(None, "in", "missing", "estimated"),
        "exit": V(
            None,
            "in",
            "Source uses exit animations/traces",
            "estimated",
            "s&box places the player beside the seat",
        ),
    }
    if "vehicle_engine" in attachments:
        doc["engine"]["position"] = V(
            list(attachments["vehicle_engine"]), "in", "model attachment vehicle_engine"
        )

    # sounds: vehicle_sounds states -> sound names -> files
    vs = script.find_key("vehicle_sounds", or_blank=True)
    states = []
    for st in vs.find_all("state"):
        name, snd = st["name", ""], st["sound", ""]
        entry = {"state": name, "sound": snd, "resolved": sounds.get(snd)}
        if snd and snd not in sounds:
            doc["problems"].append(f"sound '{snd}' for {name} is not defined in the given sources")
        states.append(entry)
    doc["sounds"] = {
        "states": states,
        "gears": [
            {"max_speed": _num(g, "max_speed"), "speed_approach_factor": _num(g, "speed_approach_factor")}
            for g in vs.find_all("gear")
        ],
        "crash": vs["crashsound", None] if vs.has_children() else None,
    }
    doc["collision"] = {"has_phy": has_phy}
    doc["status"] = {
        "asset": "converted",
        "definition": "extracted" if not doc["problems"] else "extracted with problems",
        "drivable": "prepared; target test not run",
        "multiplayer": "not implemented (single player only)",
        "physics_model": "recreated: raycast wheels tuned from the script, not Source's vphysics vehicle",
    }
    return doc


def scan_addon(mount: Mount) -> dict:
    """Inventory vehicle definitions, sounds and frameworks across the mount (static, no execution)."""
    vehicles: list[VehicleDefinition] = []
    sounds: dict[str, dict] = {}
    frameworks: dict[str, list[str]] = {}
    errors = []
    for path in sorted(mount.all_paths()):
        if path.endswith(".lua"):
            hit = mount.find(path)
            text = mount.read(hit).decode("utf-8", "replace")
            for fw, rx in FRAMEWORK_MARKERS.items():
                if rx.search(text):
                    frameworks.setdefault(fw, []).append(path)
            try:
                vehicles += find_vehicle_definitions(path, text)
                sounds.update(find_sounds(path, text))
            except LuaParseError as exc:
                errors.append(f"{path}: {exc}")
        elif path.startswith("scripts/") and path.endswith(".txt") and "sound" in path:
            hit = mount.find(path)
            sounds.update(find_soundscripts(path, mount.read(hit).decode("utf-8", "replace")))
    return {"vehicles": vehicles, "sounds": sounds, "frameworks": frameworks, "errors": errors}
