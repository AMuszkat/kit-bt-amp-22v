"""Headless Blender scene for the kit_bt_amp_22v product render.

    blender -b --factory-startup --python scene.py -- job.json

job.json: {"glb", "components", "beauty", "matte"} plus optional overrides of
px, samples, adaptive, device, view, fill, lens, lights, world and exposure.
The GLB contains the unmodified native board and its embedded Altium STEP parts.
components.json is read-only pcbnew metadata used to supply simple, unlabelled
bodies for footprints that have no embedded model. No KiCad file is written.

Writes two RGBA PNGs of the same frame:
  beauty  Cycles, floor as shadow catcher: alpha = objects + floor shadow
  matte   the objects alone (floor hidden), low samples: alpha = object coverage
compose.py uses the pair to set the floor shadow's strength independently of
the board itself.
"""
import json
import math
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector

job = json.load(open(sys.argv[sys.argv.index("--") + 1]))
MM = 0.001

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=job["glb"])
scene = bpy.context.scene


# ---- materials ----------------------------------------------------------------

def new_mat(name, colour, metallic=0.0, rough=0.5, **extra):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*colour, 1.0)
    b.inputs["Metallic"].default_value = metallic
    b.inputs["Roughness"].default_value = rough
    for k, v in extra.items():
        b.inputs[k.replace("_", " ")].default_value = v
    return m


def srgb(*c):
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def microfinish(mat, roughness=None, bump_mm=0.0, scale=180.0, anisotropy=None):
    """Small-scale physical finish, not an image texture: roughness variation and
    a microscopic normal perturbation keep large surfaces from looking like CAD."""
    n, links = mat.node_tree.nodes, mat.node_tree.links
    b = n.get("Principled BSDF")
    tex = n.new("ShaderNodeTexCoord")
    noise = n.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = 2.0
    noise.inputs["Roughness"].default_value = 0.65
    links.new(tex.outputs["Generated"], noise.inputs["Vector"])
    if roughness:
        remap = n.new("ShaderNodeMapRange")
        remap.inputs["To Min"].default_value = roughness[0]
        remap.inputs["To Max"].default_value = roughness[1]
        links.new(noise.outputs["Fac"], remap.inputs["Value"])
        links.new(remap.outputs["Result"], b.inputs["Roughness"])
    if bump_mm:
        bump = n.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.16
        bump.inputs["Distance"].default_value = bump_mm * MM
        links.new(noise.outputs["Fac"], bump.inputs["Height"])
        links.new(bump.outputs["Normal"], b.inputs["Normal"])
    if anisotropy is not None and b.inputs.get("Anisotropic IOR Level"):
        b.inputs["Anisotropic IOR Level"].default_value = anisotropy


M = {
    "enig":     new_mat("enig", srgb(0.88, 0.74, 0.47), 1.0, 0.22),
    "solder":   new_mat("solder", srgb(0.82, 0.82, 0.81), 1.0, 0.24),
    "copper":   new_mat("copper_enig", srgb(0.88, 0.74, 0.47), 1.0, 0.30),   # all exposed copper is ENIG
    "silk":     new_mat("silk", srgb(0.93, 0.93, 0.91), 0.0, 0.62),
    "laminate": new_mat("fr4_edge", srgb(0.66, 0.64, 0.47), 0.0, 0.65),
    "tin":      new_mat("tin", srgb(0.82, 0.82, 0.80), 1.0, 0.30),
    "nickel":   new_mat("nickel", srgb(0.78, 0.77, 0.74), 1.0, 0.20),
    "steel":    new_mat("steel", srgb(0.74, 0.74, 0.73), 1.0, 0.28),
    "gold":     new_mat("gold", srgb(0.93, 0.73, 0.38), 1.0, 0.20),
    "ceramic":  new_mat("ceramic", srgb(0.48, 0.36, 0.25), 0.0, 0.45),
    "res_body": new_mat("resistor_body", srgb(0.06, 0.06, 0.065), 0.0, 0.45),
    "epoxy":    new_mat("epoxy", srgb(0.075, 0.075, 0.08), 0.0, 0.42, Specular_IOR_Level=0.45),
    "black":    new_mat("black_plastic", srgb(0.06, 0.06, 0.065), 0.0, 0.40),
    "ferrite":  new_mat("ferrite", srgb(0.07, 0.07, 0.072), 0.0, 0.62),
    "ferrite_g": new_mat("ferrite_grey", srgb(0.28, 0.28, 0.29), 0.0, 0.6),
    "grey_pl":  new_mat("grey_plastic", srgb(0.64, 0.65, 0.63), 0.0, 0.48),
    "nylon":    new_mat("nylon", srgb(0.95, 0.94, 0.91), 0.0, 0.42,
                        Subsurface_Weight=0.25, Subsurface_Scale=0.002),
    "button":   new_mat("button", srgb(0.86, 0.85, 0.82), 0.0, 0.5),
    "alumina":  new_mat("alumina", srgb(0.90, 0.89, 0.86), 0.0, 0.55),
    "molded":   new_mat("molded_inductor", srgb(0.20, 0.20, 0.21), 0.0, 0.6),
}

# The Altium 3-D configuration specifies a deep-blue mask (BGR 0x6b3917).
# Native import leaves KiCad's generic green mask at alpha 0.83, so identify it
# by that alpha and restore the source colour as a satin lacquer. Other alpha-0
# materials are opaque vendor part geometry, not solder mask.
MASKS = []
for mat in bpy.data.materials:
    b = mat.node_tree.nodes.get("Principled BSDF") if mat.use_nodes else None
    if not b:
        continue
    r, g, bl, _ = b.inputs["Base Color"].default_value
    alpha = b.inputs["Alpha"].default_value
    if 0.5 < alpha < 0.9 and max(r, g, bl) < 0.95:
        b.inputs["Base Color"].default_value = (*srgb(0.090, 0.224, 0.420), 1)
        b.inputs["Alpha"].default_value = job.get("mask_alpha", 0.95)
        b.inputs["Roughness"].default_value = job.get("mask_rough", 0.38)
        b.inputs["Specular IOR Level"].default_value = 0.5
        MASKS.append(mat)
    elif alpha < 0.9:
        b.inputs["Alpha"].default_value = 1.0


def part(o):
    """The footprint reference an object belongs to (its top empty under Node_0)."""
    p = o
    while p.parent and p.parent.name != "Node_0":
        p = p.parent
    return p.name.split(".")[0]


# The footprints specify top-actuated SKRPABE010 switches, but the embedded
# SKRPAC STEP model is side-actuated. Its actuator points along local +Y while
# the mounting plane's outward normal is local -Z. Turn it upright about the
# model origin; doing this in local space preserves each footprint's PCB rotation.
for o in scene.objects:
    if o.type == "MESH" and part(o).startswith("SW"):
        o.matrix_basis = Matrix.Rotation(-math.pi / 2, 4, "X") @ o.matrix_basis


def base_colour(mat):
    b = mat.node_tree.nodes.get("Principled BSDF") if mat and mat.use_nodes else None
    return tuple(b.inputs["Base Color"].default_value[:3]) if b else (0, 0, 0)


def lum(c):
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def classify(o, mat):
    """Material role for one slot of one object, from the part and object names
    first and the exported colour second."""
    ref, name = part(o), o.name.split(".")[0]
    c, L = base_colour(mat), lum(base_colour(mat))
    b = mat.node_tree.nodes.get("Principled BSDF")
    met = b.inputs["Metallic"].default_value if b else 1
    if ref.startswith("=>") or ref == "Node_0":            # the board itself
        # KiCad's GLB: the copper layers come out gold-coloured (under the mask),
        # the exposed-pad finish layer grey, 5 um above them.  Pads of an
        # assembled board are solder-coated; mounting rings get ENIG gold below.
        if met > 0.5 and c[2] < 0.2 * c[0]:
            return "mask_covered"
        if met > 0.5:
            return "solder"
        if L > 0.8:
            return "silk"
        return "laminate"
    for prefix, role in (("NYLON_", "nylon"), ("EPOXY_", "epoxy"), ("NICKEL_", "nickel"),
                         ("PLASTIC_", "grey_pl"), ("ALU_", "alu"), ("BLACK_", "black"),
                         ("TIN_", "tin"), ("MOLDED_", "molded")):
        if name.startswith(prefix):
            return role
    if "Logo" in name or "logo" in name or name == "Vishay":   # vendor logos on part models
        return "HIDE"
    if name.startswith("6130xx"):                            # Wurth header pins
        return "gold"
    if name.startswith("6130"):                              # header housing
        return "black"
    if ref == "Q1" and mat.name == "mat_15":                 # fused laser-marking faces
        return "epoxy"                                      # suppress historical logo artwork
    if ref.startswith(("U", "Q", "MD")):                       # IC and module packages
        return "tin" if L > 0.1 else "epoxy"
    if ref.startswith(("CSUP", "C17", "C25", "C5")):          # aluminium electrolytics
        return "alu" if L > 0.3 else "black"
    if ref == "P2":                                          # white JST power connector
        return "tin" if met > 0.5 and L > 0.25 else "grey_pl"
    if ref.startswith(("J1", "J2")):                          # speaker terminal blocks
        return "tin" if met > 0.5 and L > 0.25 else "grey_pl"
    if ref == "P6":                                          # Samtec debug header
        return "gold" if met > 0.5 and L > 0.2 else "black"
    if ref == "J4":                                          # 3.5 mm audio socket
        return "nickel" if met > 0.5 and L > 0.2 else "black"
    if ref.startswith(("L", "LSUP")):                         # inductors and ferrites
        return "tin" if L > 0.3 else "ferrite"
    if ref.startswith("R"):
        if name == "body":
            return "alumina"                                 # Vishay model: substrate
        if name == "top":
            return "res_body"
        return "tin" if L > 0.3 else "res_body"
    if ref.startswith("C"):
        if L > 0.3 or (c[0] > 0.4 and abs(c[0] - c[2]) < 0.1):
            return "tin"
        return "ceramic"
    return "tin" if L > 0.3 else "black"


M["alu"] = new_mat("aluminium_can", srgb(0.72, 0.73, 0.74), 1.0, 0.32)
M["mask_covered"] = new_mat("blue_mask_over_copper", srgb(0.090, 0.224, 0.420), 0.0, 0.40,
                            Coat_Weight=0.10, Coat_Roughness=0.36)
M["alu_top"] = new_mat("aluminium_can_top", srgb(0.58, 0.59, 0.60), 1.0, 0.52)
M["ceramic_dark"] = new_mat("ceramic_dark", srgb(0.12, 0.12, 0.12), 0.0, 0.5)
M["vent"] = new_mat("stamped_aluminium_vent", srgb(0.30, 0.31, 0.32), 1.0, 0.48)

# Real surface finishes: pale ENIG, softly brushed metal, moulded plastics and
# a satin lacquer with a separate clear coat.  All scales are sub-visible grain;
# the board's geometry and silkscreen still come exclusively from KiCad.
for key, rgb in {
    "enig": (0.86, 0.75, 0.52), "copper": (0.86, 0.75, 0.52),
    "gold": (0.86, 0.69, 0.37), "laminate": (0.50, 0.49, 0.36),
}.items():
    M[key].node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*srgb(*rgb), 1)
for key, rough, bump, anis in (
    ("enig", (0.18, 0.25), 0.0003, 0.12), ("copper", (0.23, 0.31), 0.0004, 0.12),
    ("solder", (0.25, 0.34), 0.0006, 0.10), ("tin", (0.26, 0.35), 0.0005, 0.18),
    ("nickel", (0.19, 0.28), 0.0004, 0.28), ("steel", (0.25, 0.34), 0.0005, 0.20),
    ("gold", (0.20, 0.28), 0.0003, 0.18), ("alu", (0.29, 0.39), 0.0005, 0.38),
    ("alu_top", (0.48, 0.58), 0.0007, 0.22),
    ("ceramic", (0.43, 0.53), 0.0010, None), ("res_body", (0.42, 0.52), 0.0008, None),
    ("epoxy", (0.38, 0.47), 0.0008, None), ("black", (0.38, 0.47), 0.0012, None),
    ("ferrite", (0.56, 0.66), 0.0015, None), ("molded", (0.55, 0.65), 0.0015, None),
    ("grey_pl", (0.43, 0.53), 0.0018, None), ("nylon", (0.38, 0.47), 0.0012, None),
    ("alumina", (0.50, 0.60), 0.0008, None),
    ("mask_covered", (0.36, 0.44), 0.0008, None),
):
    microfinish(M[key], rough, bump, anisotropy=anis)
M["nylon"].node_tree.nodes["Principled BSDF"].inputs["Subsurface Weight"].default_value = 0.08
for mask in MASKS:
    b = mask.node_tree.nodes["Principled BSDF"]
    b.inputs["Specular IOR Level"].default_value = 0.32
    b.inputs["Coat Weight"].default_value = 0.08
    b.inputs["Coat Roughness"].default_value = 0.40
    microfinish(mask, (0.40, 0.47), 0.0008, scale=240)

hidden = []
for o in list(scene.objects):
    if o.type != "MESH":
        continue
    for slot in o.material_slots:
        if not slot.material or slot.material in MASKS:
            continue
        role = classify(o, slot.material)
        if role == "HIDE":
            hidden.append(o)
            break
        if role:
            slot.link = "OBJECT"
            slot.material = M[role]
for o in hidden:
    bpy.data.objects.remove(o)
print("HIDDEN", len(hidden))

# The Altium importer produced no top mask mesh. Keep the FR4 vertical edge, but
# put the source blue mask on the substrate's horizontal faces as well as on its
# covered copper. This avoids an unmasked yellow laminate/copper appearance.
for o in scene.objects:
    if o.type != "MESH" or not any(sl.material == M["laminate"] for sl in o.material_slots):
        continue
    o.data.materials.append(M["mask_covered"])
    gi = len(o.material_slots) - 1
    rot = o.matrix_world.to_3x3().normalized()
    for poly in o.data.polygons:
        if abs((rot @ poly.normal).z) > 0.8:
            poly.material_index = gi

# ---- conservative bodies for footprints without an embedded STEP model ---------
# These are package solids only, not invented markings or vendor geometry. Their
# positions, rotations and through-hole pin locations come from the native PCB.
import re  # noqa: E402

BOARD_TOP_MM = job.get("board_top_mm", 1.55692)
M["led"] = new_mat("led_lens", srgb(0.78, 0.82, 0.57), 0.0, 0.28)
M["marking"] = new_mat("laser_marking", srgb(0.64, 0.65, 0.64), 0.0, 0.65)
components = json.load(open(job["components"]))["footprints"] if job.get("components") else []


def box(name, centre, dims, material, angle=0.0, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=tuple(v * MM for v in centre))
    ob = bpy.context.object
    ob.name = name
    ob.dimensions = tuple(v * MM for v in dims)
    ob.rotation_euler.z = -math.radians(angle)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    ob.data.materials.append(material)
    if bevel:
        mod = ob.modifiers.new("moulded_edge", "BEVEL")
        mod.width = bevel * MM
        mod.segments = 2
    return ob


def local_box(fp, suffix, dx, dy, z, sx, sy, sz, material, bevel=0.0):
    a = math.radians(fp["rotation"])
    x = fp["x"] + math.cos(a) * dx - math.sin(a) * dy
    y = fp["y"] + math.sin(a) * dx + math.cos(a) * dy
    return box(f'{fp["ref"]}_{suffix}', (x, -y, z), (sx, sy, sz), material,
               fp["rotation"], bevel)


def chip(fp, size, body_material, terminals=True):
    w, d, h = size
    local_box(fp, "body", 0, 0, BOARD_TOP_MM + 0.025 + h / 2,
              w, d, h, body_material, min(0.06, h * 0.12))
    if terminals:
        for side in (-1, 1):
            local_box(fp, f"terminal_{side}", side * (w / 2 - 0.08), 0,
                      BOARD_TOP_MM + 0.02 + h * 0.36, 0.24, d * 0.94,
                      h * 0.70, M["tin"], 0.025)


def header(fp):
    """Vertical header body from its pad envelope, never its pin-1 origin.

    Pads are transformed back into footprint-local coordinates so both single-
    and dual-row bodies get the correct centre and span. The existing -rotation
    transform maps KiCad's Y-down frame into Blender without mirroring the part.
    Pins continue to use their unmodified board-space pad positions.
    """
    angle = math.radians(fp["rotation"])
    local = []
    for pad in fp["pads"]:
        dx, dy = pad["x"] - fp["x"], pad["y"] - fp["y"]
        local.append((math.cos(angle) * dx + math.sin(angle) * dy,
                      -math.sin(angle) * dx + math.cos(angle) * dy))
    xs, ys = [p[0] for p in local], [p[1] for p in local]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    width, depth = max(xs) - min(xs) + 2.54, max(ys) - min(ys) + 2.54
    world_cx = fp["x"] + math.cos(angle) * cx - math.sin(angle) * cy
    world_cy = fp["y"] + math.sin(angle) * cx + math.cos(angle) * cy
    pad_cx = (min(p["x"] for p in fp["pads"]) + max(p["x"] for p in fp["pads"])) / 2
    pad_cy = (min(p["y"] for p in fp["pads"]) + max(p["y"] for p in fp["pads"])) / 2
    assert math.hypot(world_cx - pad_cx, world_cy - pad_cy) < 1e-6
    print("HEADER_BODY", fp["ref"], "size_mm", round(width, 3), round(depth, 3),
          "centre_mm", round(world_cx, 5), round(world_cy, 5))
    local_box(fp, "housing", cx, cy, BOARD_TOP_MM + 1.27,
              width, depth, 2.54, M["black"], 0.08)
    for i, pad in enumerate(fp["pads"]):
        box(f'{fp["ref"]}_pin_{i}', (pad["x"], -pad["y"], BOARD_TOP_MM + 1.5),
            (0.64, 0.64, 9.0), M["gold"], bevel=0.025)


generated = []
for fp in components:
    ref, fpid = fp["ref"], fp["fpid"]
    if not ref or fp.get("dnp") or fp["models"] or fp["layer"] != "Top Layer":
        continue
    if ref.startswith("TP_"):
        continue
    if ref in ("J_BCK_5V", "J_PVDD", "P4", "P7", "P1", "P_L2", "J_VCC_PSOC", "P5", "J_BCK_3V3"):
        header(fp)
    elif ref == "J_USB1":
        # Micro-USB receptacle: nickel shell with a dark recessed mouth and tongue.
        local_box(fp, "shell", 0, 0, BOARD_TOP_MM + 1.25, 5.0, 7.0, 2.5, M["nickel"], 0.16)
        local_box(fp, "mouth", 0, -3.505, BOARD_TOP_MM + 1.25, 4.35, 0.025, 1.75, M["black"], 0.08)
        local_box(fp, "tongue", 0, -3.53, BOARD_TOP_MM + 1.15, 3.25, 0.035, 0.48, M["ferrite"], 0.03)
    elif ref == "U3":
        chip(fp, (3.0, 4.0, 0.9), M["epoxy"], False)
    elif ref == "U4":
        chip(fp, (3.0, 3.0, 0.85), M["epoxy"], False)
    elif ref == "U7":
        chip(fp, (5.0, 5.0, 0.85), M["epoxy"], False)
    elif ref == "U8":
        chip(fp, (9.0, 9.0, 0.90), M["epoxy"], False)
    elif ref == "Q2":
        chip(fp, (2.0, 2.0, 0.75), M["epoxy"], False)
    elif ref == "L2":
        chip(fp, (4.8, 4.8, 2.8), M["molded"], False)
    elif ref == "C5":
        bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=2.65 * MM, depth=5.5 * MM,
            location=(fp["x"] * MM, -fp["y"] * MM, (BOARD_TOP_MM + 2.78) * MM))
        ob = bpy.context.object
        ob.name = "C5_polymer_can"
        ob.data.materials.append(M["alu"])
        for poly in ob.data.polygons:
            poly.use_smooth = len(poly.vertices) == 4
    elif ref.startswith(("DS", "D1", "D4")):
        chip(fp, (1.6, 0.8, 0.65), M["led"])
    elif ref in ("D2", "D3"):
        chip(fp, (1.2, 0.8, 0.55), M["epoxy"])
    elif ref == "DVDD0":
        chip(fp, (1.6, 0.8, 0.80), M["ceramic"])
    elif ref.startswith("R") and "RESC1005" in fpid:
        chip(fp, (1.0, 0.5, 0.38), M["res_body"])
    elif ref.startswith("R") and "RESC1608" in fpid:
        chip(fp, (1.6, 0.8, 0.50), M["res_body"])
    elif ref.startswith("R") and "CG0603" in fpid:
        chip(fp, (1.6, 0.8, 0.55), M["res_body"])
    elif ref.startswith("C") and any(s in fpid for s in ("CAPC0603X33",)):
        chip(fp, (0.6, 0.3, 0.30), M["ceramic"])
    elif ref.startswith("C") and any(s in fpid for s in ("CAP0402", "CAPC0402", "CL05A", "CL05B")):
        chip(fp, (1.0, 0.5, 0.50), M["ceramic"])
    elif ref.startswith("C") and any(s in fpid for s in ("CAP0603", "CAPC0603", "CAPC1608")):
        chip(fp, (1.6, 0.8, 0.80), M["ceramic"])
    elif ref.startswith("C") and any(s in fpid for s in ("CAP0805", "CAPC0805", "CAPC2013")):
        chip(fp, (2.0, 1.25, 1.05), M["ceramic"])
    elif ref.startswith("C") and "CAP1210" in fpid:
        chip(fp, (3.2, 2.5, 1.90), M["ceramic"])
    elif ref.startswith("L") and any(s in fpid for s in ("0805", "0603", "1608", "INDC1608")):
        chip(fp, (1.6, 0.8, 0.85), M["ferrite"])
    else:
        generated.append((ref, fpid))

print("UNMODELLED_LEFT", generated)

# U1's footprint origin is offset from its pad array. Align the render-only model
# to the pad-array centre (which also validates the embedded model's own origin);
# the KiCad source is not changed. Markings use that same physical package centre.
u1fp = next((item for item in components if item["ref"] == "U1"), None)
u1root = bpy.data.objects.get("U1")
if u1fp and u1root:
    body = next((ob for ob in u1root.children_recursive if ob.type == "MESH" and ob.name == "2"), None)
    if body:
        points = [body.matrix_world @ v.co for v in body.data.vertices]
        centre = Vector(((min(p.x for p in points) + max(p.x for p in points)) / 2,
                         (min(p.y for p in points) + max(p.y for p in points)) / 2, 0))
        pad_x = (min(p["x"] for p in u1fp["pads"]) + max(p["x"] for p in u1fp["pads"])) / 2
        pad_y = (min(p["y"] for p in u1fp["pads"]) + max(p["y"] for p in u1fp["pads"])) / 2
        u1root.location.x += pad_x * MM - centre.x
        u1root.location.y += -pad_y * MM - centre.y
        bpy.context.view_layer.update()

# Only source-known part identification is printed. The Q1 model's fused white
# artwork was suppressed above; its replacement text is the actual value field.
def part_marking(ref, text, size, z):
    fp = next((item for item in components if item["ref"] == ref), None)
    if not fp:
        return
    curve = bpy.data.curves.new(f"{ref}_{text}_marking", "FONT")
    curve.body = text
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.size = size * MM
    curve.extrude = 0
    ob = bpy.data.objects.new(curve.name, curve)
    scene.collection.objects.link(ob)
    if fp["pads"]:
        x = (min(p["x"] for p in fp["pads"]) + max(p["x"] for p in fp["pads"])) / 2
        y = (min(p["y"] for p in fp["pads"]) + max(p["y"] for p in fp["pads"])) / 2
    else:
        x, y = fp["x"], fp["y"]
    ob.location = (x * MM, -y * MM, z * MM)
    curve.materials.append(M["marking"])
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.convert(target="MESH")


part_marking("U1", "MA12070P", 1.20, BOARD_TOP_MM + 1.065)
part_marking("Q1", "IRFHM830", 0.46, BOARD_TOP_MM + 1.035)

# Terminal blocks are one fused solid each: pick out the metal.  Up-facing faces
# that form small islands sunk below the housing top are the screw heads at the
# pocket floors; faces below the board surface are the pins.
import bmesh  # noqa: E402

BOARD_TOP = job.get("board_top_mm", 1.555) * MM
for o in list(scene.objects):
    if o.type != "MESH" or not o.name.startswith("PLASTIC_housing"):
        continue
    o.data.materials.append(M["nickel"])
    o.data.materials.append(M["tin"])
    i_ni, i_sn = len(o.data.materials) - 2, len(o.data.materials) - 1
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bm.faces.ensure_lookup_table()
    mw, rot = o.matrix_world, o.matrix_world.to_3x3().normalized()
    zmax = max((mw @ v.co).z for v in bm.verts)
    up = {f.index for f in bm.faces if (rot @ f.normal).z > 0.95
          and BOARD_TOP + 1.0 * MM < (mw @ f.calc_center_median()).z < zmax - 0.8 * MM}
    seen, screws, pins = set(), 0, 0
    for f0 in up:
        if f0 in seen:
            continue
        island, stack = [], [f0]
        seen.add(f0)
        while stack:
            f = bm.faces[stack.pop()]
            island.append(f)
            for e in f.edges:
                for g in e.link_faces:
                    if g.index in up and g.index not in seen:
                        seen.add(g.index)
                        stack.append(g.index)
        area = sum(f.calc_area() for f in island) * (mw.median_scale ** 2)
        if area < 9e-6:                                    # < 9 mm^2: a screw head
            for f in island:
                f.material_index = i_ni
            screws += 1
    for f in bm.faces:
        if (mw @ f.calc_center_median()).z < BOARD_TOP - 0.05 * MM:
            f.material_index = i_sn
            pins += 1
    bm.to_mesh(o.data)
    bm.free()
    print("TERMINAL", part(o), "screw heads", screws, "pin faces", pins)

# Mounting holes carry no paste: their rings stay bare ENIG.
hole_xy = job.get("holes", [])
if not hole_xy:
    hole_xy = [[fp["x"], fp["y"]] for fp in components if not fp["ref"] and fp["pads"]]
HOLES = [(x * MM, -y * MM) for x, y in hole_xy]
for o in scene.objects:
    if o.type == "MESH" and any(sl.material == M["solder"] for sl in o.material_slots):
        o.data.materials.append(M["enig"])
        gi = len(o.material_slots) - 1
        mw, n = o.matrix_world, 0
        for poly in o.data.polygons:
            p = mw @ poly.center
            if any(math.hypot(p.x - hx, p.y - hy) < job.get("ring_r", 2.35) * MM for hx, hy in HOLES):
                poly.material_index = gi
                n += 1
        print("ENIG faces", o.name, n)


def cap_vent(ref, rotation=0):
    """Model the shallow three-arm pressure-relief score in an electrolytic can."""
    root = bpy.data.objects.get(ref)
    if not root:
        return
    verts = [c.matrix_world @ v.co for c in root.children_recursive
             if c.type == "MESH" for v in c.data.vertices]
    if not verts:
        return
    ztop = max(p.z for p in verts)
    # The rolled can wall is brighter and more directional than its stamped lid.
    for ob in root.children_recursive:
        if ob.type != "MESH":
            continue
        ob.data = ob.data.copy()
        ob.data.materials.append(M["alu_top"])
        gi = len(ob.material_slots) - 1
        mw = ob.matrix_world
        rot = mw.to_3x3().normalized()
        for poly in ob.data.polygons:
            if (rot @ poly.normal).z > 0.80 and (mw @ poly.center).z > ztop - 0.08 * MM:
                poly.material_index = gi
    top = [p for p in verts if p.z > ztop - 0.04 * MM]
    x0, x1 = min(p.x for p in top), max(p.x for p in top)
    y0, y1 = min(p.y for p in top), max(p.y for p in top)
    radius = min(x1 - x0, y1 - y0) / 2
    if radius < 1.5 * MM:
        return
    centre = Vector(((x0 + x1) / 2, (y0 + y1) / 2, ztop + 0.003 * MM))
    cu = bpy.data.curves.new(f"vent_{ref}", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = 0.013 * MM
    cu.bevel_resolution = 2
    for arm in range(3):
        angle = math.radians(rotation + arm * 120)
        direction = Vector((math.cos(angle), math.sin(angle), 0))
        spline = cu.splines.new("POLY")
        spline.points.add(1)
        for point, distance in zip(spline.points, (0.10 * radius, 0.60 * radius)):
            p = centre + direction * distance
            point.co = (*p, 1)
    ob = bpy.data.objects.new(cu.name, cu)
    scene.collection.objects.link(ob)
    cu.materials.append(M["vent"])


for i, ref in enumerate(("CSUP1", "CSUP2", "CSUP3", "CSUP4", "C17", "C25")):
    cap_vent(ref, 20 + i * 17)


# ---- extent -----------------------------------------------------------------------
bpy.context.view_layer.update()
meshes = [o for o in scene.objects if o.type == "MESH"]
pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
lo = Vector([min(p[i] for p in pts) for i in range(3)])
hi = Vector([max(p[i] for p in pts) for i in range(3)])
centre, size = (lo + hi) / 2, (hi - lo).length
flat_coords = [c for p in pts for c in p]
print("EXTENT", [round(v / MM, 2) for v in lo], [round(v / MM, 2) for v in hi])

bpy.ops.mesh.primitive_plane_add(size=size * 40, location=(centre.x, centre.y, lo.z - 0.00002))
floor = bpy.context.active_object
floor.name = "floor"
floor.is_shadow_catcher = True


# ---- camera -------------------------------------------------------------------------
x, _, z = (float(v) for v in job.get("view", {}).get("rotate", "-38,0,62").split(","))
el, az = math.radians(90 - abs(x)), math.radians(-z)
direction = Vector((math.cos(el) * math.sin(az), -math.cos(el) * math.cos(az), math.sin(el)))
cam_data = bpy.data.cameras.new("cam")
cam = bpy.data.objects.new("cam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
cam_data.lens = job.get("lens", 85)
cam_data.clip_start, cam_data.clip_end = size * 0.01, size * 100
cam.location = centre + direction * size * 4
cam.rotation_euler = (-direction).to_track_quat("-Z", "Y").to_euler()
cam_data.dof.use_dof = False
bpy.context.view_layer.update()


def frame(fill, px):
    scene.render.resolution_x, scene.render.resolution_y = 1600, 1000
    for _ in range(2):
        dg = bpy.context.evaluated_depsgraph_get()
        loc, _scale = cam.camera_fit_coords(dg, flat_coords)
        cam.location = loc
        bpy.context.view_layer.update()
        uv = [world_to_camera_view(scene, cam, p) for p in pts]
        w = max(u.x for u in uv) - min(u.x for u in uv)
        h = max(u.y for u in uv) - min(u.y for u in uv)
        aspect = min(max(w * scene.render.resolution_x / (h * scene.render.resolution_y), 0.6), 2.6)
        rx = round(math.sqrt(px * aspect) / 8) * 8
        scene.render.resolution_x, scene.render.resolution_y = rx, round(rx / aspect / 8) * 8
    cam.location = centre + (cam.location - centre) / fill


frame(job.get("fill", 0.64), job.get("px", 16e6))


# ---- light ---------------------------------------------------------------------------
# A light tent: big soft key above-left of the camera, a broad fill from the camera's
# right, a rim from behind for edge highlights, and a white world for everything else.
cam_dir = (cam.location - centre).normalized()
cam_az = math.atan2(cam_dir.y, cam_dir.x)


def softbox(name, rel_az_deg, elev_deg, dist, spread, energy):
    a, e = cam_az + math.radians(rel_az_deg), math.radians(elev_deg)
    d = Vector((math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)))
    data = bpy.data.lights.new(name, "AREA")
    # Energies were tuned on the TAS5825M board (scene diagonal 0.120 m); the lights
    # sit at distances proportional to the scene, so scale by size^2 to light any
    # board alike.
    data.shape = "RECTANGLE"
    data.size = size * spread
    data.size_y = size * spread * (0.28 if name == "rim" else 0.68)
    data.energy = energy * (size / job.get("ref_size", 0.12008)) ** 2
    ob = bpy.data.objects.new(name, data)
    ob.location = centre + d * size * dist
    ob.rotation_euler = (centre - ob.location).to_track_quat("-Z", "Y").to_euler()
    scene.collection.objects.link(ob)
    return ob


L = job.get("lights", {})
# (azimuth from the camera, elevation, distance and size in scene diagonals, watts)
softbox("key", *L.get("key", (-48, 58, 2.2, 1.8, 1.8)))
softbox("fill", *L.get("fill", (55, 32, 2.4, 2.4, 0.36)))
softbox("rim", *L.get("rim", (160, 45, 2.2, 1.7, 0.75)))

world = bpy.data.worlds.new("tent")
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs["Color"].default_value = (1, 1, 1, 1)
bg.inputs["Strength"].default_value = job.get("world", 0.18)
scene.world = world


# ---- render ----------------------------------------------------------------------------
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"


def pick_gpu(want):
    if want == "cpu":
        return "CPU (asked for)"
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
    except Exception as err:                                # noqa: BLE001
        return f"CPU ({err})"
    for backend in ("OPTIX", "CUDA", "HIP", "ONEAPI"):
        try:
            prefs.compute_device_type = backend
            prefs.get_devices()
        except Exception:                                   # noqa: BLE001
            continue
        gpus = [d for d in prefs.devices if d.type == backend]
        if not gpus:
            continue
        for d in prefs.devices:
            d.use = d.type == backend or (d.type == "CPU" and want != "gpu")
        scene.cycles.device = "GPU"
        return f"{backend}: " + " + ".join(d.name for d in prefs.devices if d.use)
    return "CPU (no usable GPU)"


print("DEVICE", pick_gpu(job.get("device", "auto")))
scene.cycles.use_denoising = True
scene.cycles.use_adaptive_sampling = True
scene.cycles.adaptive_threshold = job.get("adaptive", 0.008)
scene.cycles.max_bounces = 12
scene.cycles.glossy_bounces = 6
scene.cycles.transmission_bounces = 8
scene.cycles.transparent_max_bounces = 16
scene.render.film_transparent = True
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.image_settings.color_depth = "16"
scene.view_settings.view_transform = job.get("view_transform", "Khronos PBR Neutral")
scene.view_settings.look = "None"
scene.view_settings.exposure = job.get("exposure", -0.6)   # the white backdrop is added later
scene.render.threads_mode = "AUTO"

scene.cycles.samples = job.get("samples", 320)
scene.render.filepath = job["beauty"]
bpy.ops.render.render(write_still=True)
print("BEAUTY", scene.render.resolution_x, scene.render.resolution_y)

if not job.get("skip_matte"):
    floor.hide_render = True
    scene.cycles.samples = 24
    scene.cycles.use_denoising = False
    scene.cycles.use_adaptive_sampling = False
    scene.cycles.max_bounces = 0
    scene.render.filepath = job["matte"]
    bpy.ops.render.render(write_still=True)
    print("MATTE done")
