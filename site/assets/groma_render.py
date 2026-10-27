"""Groma line plate. blender -b -P groma.py -- <out_dir> <layer: lines|bronze>"""
import math
import sys

import bpy

out_dir, layer = sys.argv[sys.argv.index("--") + 1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene


def mat(name, kind):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    if kind == "holdout":
        s = nt.nodes.new("ShaderNodeHoldout")
        nt.links.new(s.outputs[0], o.inputs["Surface"])
    else:
        s = nt.nodes.new("ShaderNodeEmission")
        s.inputs["Color"].default_value = (1, 1, 1, 1)
        nt.links.new(s.outputs[0], o.inputs["Surface"])
    return m


HOLD = mat("hold", "holdout")
FLAT = mat("flat", "emit")
wood, iron = [], []


def cyl(r, depth, loc, rot=(0, 0, 0), verts=24, group=wood):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=depth, location=loc, rotation=rot)
    o = bpy.context.object
    group.append(o)
    return o


def cone(r1, r2, depth, loc, group):
    bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=r1, radius2=r2, depth=depth, location=loc)
    group.append(bpy.context.object)


H = 2.0
cyl(0.022, H - 0.18, (0, 0, (H - 0.18) / 2 + 0.18))           # staff
cone(0.0, 0.026, 0.18, (0, 0, 0.09), iron)                      # iron shoe
cyl(0.03, 0.06, (0, 0, H - 0.02), group=iron)                   # ferrule
rost = 0.24                                                      # rostrum: bracket arm off the staff
cyl(0.016, rost, (rost / 2, 0, H + 0.03), rot=(0, math.pi / 2, 0))
cyl(0.012, 0.09, (rost, 0, H + 0.075), verts=16, group=iron)    # pivot pin
cx, cz, arm = rost, H + 0.12, 0.46
for a in (0, math.pi / 2):                                       # the cross (stella)
    cyl(0.014, 2 * arm, (cx, 0, cz), rot=(0, math.pi / 2, a))
cyl(0.03, 0.03, (cx, 0, cz), group=iron)
drop = 0.62
for k in range(4):
    a = k * math.pi / 2 + math.pi / 4 * 0
    x, y = cx + arm * math.cos(a), arm * math.sin(a)
    cyl(0.0035, drop, (x, y, cz - drop / 2), verts=8)           # plumb line
    cone(0.0, 0.032, 0.09, (x, y, cz - drop - 0.03), iron)      # bob (point down)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.032, location=(x, y, cz - drop + 0.012), segments=20, ring_count=10)
    iron.append(bpy.context.object)

for o in wood + iron:
    bpy.ops.object.shade_smooth() if False else None
    o.data.materials.append(HOLD if layer == "lines" or o in wood else FLAT)

bpy.ops.object.camera_add(location=(3.6, -4.4, 2.6))
cam = bpy.context.object
cam.data.type = "ORTHO"
cam.data.ortho_scale = 2.55
sc.camera = cam
tgt = bpy.data.objects.new("t", None)
tgt.location = (0.12, 0, 1.18)
sc.collection.objects.link(tgt)
c = cam.constraints.new("TRACK_TO")
c.target = tgt

r = sc.render
r.engine = "BLENDER_EEVEE"
r.resolution_x, r.resolution_y = 900, 1200
r.film_transparent = True
sc.view_settings.view_transform = "Standard"
r.image_settings.file_format = "PNG"
r.image_settings.color_mode = "RGBA"
if layer == "lines":
    r.use_freestyle = True
    r.line_thickness_mode = "ABSOLUTE"
    r.line_thickness = 2.4
    vl = sc.view_layers[0]
    vl.use_freestyle = True
    ls = vl.freestyle_settings.linesets[0]
    ls.select_by_visibility = True
    ls.visibility = "VISIBLE"
    ls.select_silhouette = ls.select_border = ls.select_crease = True
    if ls.linestyle is None:
        ls.linestyle = bpy.data.linestyles.new("ink")
    ls.linestyle.color = (1, 1, 1)
    ls.linestyle.thickness = 2.4
r.filepath = f"{out_dir}/{layer}.png"
bpy.ops.render.render(write_still=True)
