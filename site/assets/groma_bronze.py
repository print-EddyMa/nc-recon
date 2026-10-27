"""The groma in bronze, for the website: `blender -b -P site/assets/groma_bronze.py -- <out.png> [wide|tall]`.

A Roman surveyor's groma as it is reconstructed from the Pompeii find: a
staff with an iron shoe, a bracket arm, a cross of four arms and four plumb
lines with conical bobs. Cast-bronze fittings, a dark wooden staff, rendered
in Cycles against black with a warm key and a cool rim. Transparent film, so
the page's own black sits behind it.
"""
import math
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
out = argv[0]
shape = argv[1] if len(argv) > 1 else "wide"
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene


def principled(name, color, metallic, rough, noise=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Metallic"].default_value = metallic
    b.inputs["Roughness"].default_value = rough
    if noise:
        tex = nt.nodes.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = 140.0
        ramp = nt.nodes.new("ShaderNodeMapRange")
        ramp.inputs["To Min"].default_value = rough - noise
        ramp.inputs["To Max"].default_value = rough + noise
        nt.links.new(tex.outputs["Fac"], ramp.inputs["Value"])
        nt.links.new(ramp.outputs["Result"], b.inputs["Roughness"])
    return m


BRONZE = principled("bronze", (0.80, 0.50, 0.25), 1.0, 0.30, noise=0.08)
DARK_BRONZE = principled("dark_bronze", (0.42, 0.26, 0.13), 1.0, 0.38, noise=0.06)
WOOD = principled("wood", (0.055, 0.035, 0.025), 0.0, 0.55, noise=0.1)
CORD = principled("cord", (0.10, 0.08, 0.06), 0.0, 0.8)


def smooth(o, bevel=0.0):
    for p in o.data.polygons:
        p.use_smooth = True
    if bevel:
        mod = o.modifiers.new("bevel", "BEVEL")
        mod.width = bevel
        mod.segments = 3


def cyl(r, depth, loc, mat, rot=(0, 0, 0), verts=48, bevel=0.003):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=depth, location=loc, rotation=rot)
    o = bpy.context.object
    o.data.materials.append(mat)
    smooth(o, bevel)
    return o


def cone(r1, r2, depth, loc, mat):
    bpy.ops.mesh.primitive_cone_add(vertices=48, radius1=r1, radius2=r2, depth=depth, location=loc)
    o = bpy.context.object
    o.data.materials.append(mat)
    smooth(o, 0.002)
    return o


def sphere(r, loc, mat):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=loc, segments=48, ring_count=24)
    o = bpy.context.object
    o.data.materials.append(mat)
    smooth(o)
    return o


H = 2.0
cyl(0.024, H - 0.2, (0, 0, (H - 0.2) / 2 + 0.2), WOOD, bevel=0.0)
cone(0.0, 0.028, 0.2, (0, 0, 0.1), DARK_BRONZE)
for z in (0.22, H - 0.04):
    cyl(0.031, 0.05, (0, 0, z), BRONZE)
cyl(0.02, 0.07, (0, 0, H + 0.02), BRONZE)                           # pivot under the bracket
rost = 0.26
cyl(0.017, rost, (rost / 2, 0, H + 0.03), BRONZE, rot=(0, math.pi / 2, 0))
cyl(0.012, 0.1, (rost, 0, H + 0.08), DARK_BRONZE, verts=24)
cx, cz, arm = rost, H + 0.13, 0.48
for a in (0, math.pi / 2):
    cyl(0.015, 2 * arm, (cx, 0, cz), BRONZE, rot=(0, math.pi / 2, a))
cyl(0.036, 0.034, (cx, 0, cz), BRONZE)
sphere(0.022, (cx, 0, cz + 0.03), BRONZE)
drop = 0.66
for k in range(4):
    a = k * math.pi / 2
    x, y = cx + arm * math.cos(a), arm * math.sin(a)
    sphere(0.019, (x, y, cz), BRONZE)                                # arm finial
    cyl(0.0028, drop, (x, y, cz - drop / 2), CORD, verts=12, bevel=0)
    cone(0.0, 0.034, 0.1, (x, y, cz - drop - 0.035), BRONZE)
    sphere(0.034, (x, y, cz - drop + 0.012), BRONZE)

# light: warm key, cool rim, soft fill, black world
world = bpy.data.worlds.new("w")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.004, 0.004, 0.005, 1)
sc.world = world


def area(name, loc, rot, size, energy, color):
    d = bpy.data.lights.new(name, "AREA")
    d.size = size
    d.energy = energy
    d.color = color
    o = bpy.data.objects.new(name, d)
    o.location = loc
    o.rotation_euler = rot
    sc.collection.objects.link(o)


area("key", (-2.6, -3.2, 3.8), (math.radians(55), 0, math.radians(-38)), 2.2, 900, (1.0, 0.86, 0.68))
area("rim", (2.4, 2.8, 3.0), (math.radians(-60), 0, math.radians(140)), 1.4, 650, (0.66, 0.78, 1.0))
area("fill", (3.5, -3.0, 1.2), (math.radians(80), 0, math.radians(50)), 3.0, 120, (1.0, 0.95, 0.9))

cam_d = bpy.data.cameras.new("cam")
cam_d.lens = 85
cam_d.dof.use_dof = True
cam_d.dof.aperture_fstop = 5.6
cam = bpy.data.objects.new("cam", cam_d)
sc.collection.objects.link(cam)
sc.camera = cam
tgt = bpy.data.objects.new("t", None)
sc.collection.objects.link(tgt)
if shape == "tall":
    cam.location = (4.6, -6.4, 2.2)
    tgt.location = (0.15, 0, 1.25)
    sc.render.resolution_x, sc.render.resolution_y = 1400, 2000
else:
    cam.location = (3.3, -4.2, 2.75)
    tgt.location = (0.22, 0, 1.78)
    sc.render.resolution_x, sc.render.resolution_y = 2400, 1500
c = cam.constraints.new("TRACK_TO")
c.target = tgt
cam_d.dof.focus_object = tgt

r = sc.render
r.engine = "CYCLES"
sc.cycles.samples = 160
sc.cycles.use_denoising = True
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "METAL"
    prefs.refresh_devices()
    for d in prefs.devices:
        d.use = True
    sc.cycles.device = "GPU"
except Exception:  # noqa: BLE001 - CPU fallback
    pass
r.film_transparent = True
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Medium High Contrast"
r.image_settings.file_format = "PNG"
r.image_settings.color_mode = "RGBA"
r.filepath = out
bpy.ops.render.render(write_still=True)
