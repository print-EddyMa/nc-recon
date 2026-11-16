"""Logo reveal for the v4 film: `blender -b -P video/launch/logo_reveal.py -- <look|full> <out_dir> [size]`.

Nine dark metal blocks on black, rim lit. A ring of light sweeps out from the
centre, eight blocks ignite, the ninth is knocked off its foundation and turns
signal orange, and the camera ends straight overhead on the exact logo geometry
(video/launch/logo/make_logo.py). EEVEE, 30 fps, 190 frames.
"""
import math, os, sys
import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
MODE, OUT = argv[0], argv[1]
SIZE = int(argv[2]) if len(argv) > 2 else 1440
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
LAST = 190
sc.frame_start, sc.frame_end = 0, LAST
sc.render.fps = 30

S, P, O, DX, DY, ROT = 0.24, 0.29, 0.07, 0.042, 0.034, 19.0
HIT = (2, 2)
THICK = 0.075

def world(cx, cy):              # logo space (0..1, y down) to world (centred, y up)
    return cx - 0.5, 0.5 - cy

def smooth(a, b, x):
    k = max(0.0, min(1.0, (x - a) / (b - a)))
    return k * k * (3 - 2 * k)

def material(name, base, metal, rough, emit=(1, 1, 1)):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*base, 1)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    b.inputs["Emission Color"].default_value = (*emit, 1)
    b.inputs["Emission Strength"].default_value = 0.0
    return m, b

# ground: black, slightly glossy, so the ring and blocks reflect
bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 0, 0))
g = bpy.context.object
gm, gb = material("ground", (0.004, 0.004, 0.005), 0.4, 0.5)
g.data.materials.append(gm)

blocks = []
ORDER = []
for r in range(3):
    for c in range(3):
        cx, cy = O + c * P + S / 2, O + r * P + S / 2
        x, y = world(cx, cy)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, THICK / 2))
        o = bpy.context.object
        o.scale = (S, S, THICK)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        mod = o.modifiers.new("b", "BEVEL"); mod.width = 0.006; mod.segments = 3
        m, b = material(f"tile{r}{c}", (0.03, 0.03, 0.032), 0.95, 0.24)
        o.data.materials.append(m)
        hit = (r, c) == HIT
        d = math.hypot(x, y)
        ORDER.append((d, r, c))
        blocks.append((o, b, x, y, d, hit))

# ring of light on the ground, growing from the centre
bpy.ops.mesh.primitive_torus_add(major_radius=1.0, minor_radius=0.006, major_segments=180, minor_segments=8, location=(0, 0, 0.004))
ring = bpy.context.object
rm, rb = material("ring", (0, 0, 0), 0, 1, (1.0, 0.86, 0.72))
ring.data.materials.append(rm)

def key_ring(f, radius, strength):
    ring.scale = (radius, radius, 1); ring.keyframe_insert("scale", frame=f)
    rb.inputs["Emission Strength"].default_value = strength
    rb.inputs["Emission Strength"].keyframe_insert("default_value", frame=f)

R0, R1 = 36, 96                 # ring sweep frames
for f in range(0, LAST + 1, 3):
    x = (f - R0) / (R1 - R0)
    rad = 0.001 + 1.45 * max(0.0, min(1.0, x)) ** 0.8
    st = 34 * smooth(R0 - 2, R0 + 8, f) * (1 - smooth(R1 - 16, R1 + 2, f))
    key_ring(f, rad, st)

def ignite_frame(d):            # the ring reaches distance d
    return R0 + (R1 - R0) * (d / 1.45) ** (1 / 0.8)

KICK = 108
for o, b, x, y, d, hit in blocks:
    em = b.inputs["Emission Strength"]; col = b.inputs["Emission Color"]
    if not hit:
        f0 = ignite_frame(d)
        for f, v in ((0, 0), (int(f0), 0), (int(f0) + 2, 5.0), (int(f0) + 14, 0.86), (LAST, 0.86)):
            em.default_value = v; em.keyframe_insert("default_value", frame=f)
    else:
        col.default_value = (1.0, 0.102, 0.0137, 1)
        for f, v in ((0, 0), (KICK - 1, 0), (KICK + 1, 6.0), (KICK + 14, 0.95), (LAST, 0.95)):
            em.default_value = v; em.keyframe_insert("default_value", frame=f)
        # knocked: jumps, twists, lands off its foundation, with a small settle
        for f in range(KICK - 2, KICK + 40, 1):
            u = max(0.0, (f - KICK) / 26)
            k = 1 - (1 - min(1.0, u)) ** 3
            lift = 0.11 * math.sin(math.pi * min(1.0, u)) ** 1.2
            wob = 0.05 * math.exp(-max(0, f - KICK - 26) / 5) * math.sin(max(0, f - KICK - 26) * 1.6) if f > KICK + 26 else 0
            o.location = (x + DX * k - x * 0 , y - DY * k, THICK / 2 + lift - THICK / 2)
            o.rotation_euler = (0.5 * math.sin(math.pi * min(1.0, u)) * (1 - k * 0.2) * 0.5, -0.35 * math.sin(math.pi * min(1.0, u)), -math.radians(ROT) * k + wob)
            o.keyframe_insert("location", frame=f); o.keyframe_insert("rotation_euler", frame=f)

# camera: low and close, rising to dead overhead
cam_d = bpy.data.cameras.new("cam"); cam_d.lens = 85; cam_d.sensor_width = 36
cam = bpy.data.objects.new("cam", cam_d); sc.collection.objects.link(cam); sc.camera = cam
tgt = bpy.data.objects.new("t", None); sc.collection.objects.link(tgt)
c = cam.constraints.new("TRACK_TO"); c.target = tgt; c.track_axis = "TRACK_NEGATIVE_Z"; c.up_axis = "UP_Y"
cam_d.dof.use_dof = True; cam_d.dof.focus_object = tgt
DIST_END = 2.0 / (2 * 0.46) * (85 / 36) * 1.0            # the block spans 46% of the frame at the end
for f in range(0, LAST + 1, 2):
    k = smooth(70, 170, f)
    el = math.radians(9 + 80.9 * k)                      # elevation
    az = math.radians(-62 + 62 * k)
    dist = 2.7 + (DIST_END - 2.7) * k - 0.25 * (1 - smooth(0, 70, f))
    cam.location = (dist * math.cos(el) * math.sin(az), -dist * math.cos(el) * math.cos(az), dist * math.sin(el))
    cam.keyframe_insert("location", frame=f)
    cam_d.dof.aperture_fstop = 1.6 + 30 * k
    cam_d.dof.keyframe_insert("aperture_fstop", frame=f)

def area(name, loc, rot, size, energy, color):
    d = bpy.data.lights.new(name, "AREA"); d.size = size; d.color = color; d.energy = energy
    o = bpy.data.objects.new(name, d); o.location = loc; o.rotation_euler = rot
    sc.collection.objects.link(o)
    return d

rim1 = area("rim1", (-3.0, 3.2, 0.7), (math.radians(82), 0, math.radians(-138)), 2.4, 0, (0.72, 0.84, 1.0))
rim2 = area("rim2", (3.4, 2.4, 0.5), (math.radians(84), 0, math.radians(125)), 1.4, 0, (1.0, 0.82, 0.66))
for f, e1, e2 in ((0, 0, 0), (26, 46, 14), (70, 46, 14), (150, 6, 2), (LAST, 0, 0)):
    rim1.energy = e1; rim1.keyframe_insert("energy", frame=f)
    rim2.energy = e2; rim2.keyframe_insert("energy", frame=f)

w = bpy.data.worlds.new("w"); w.use_nodes = True
w.node_tree.nodes["Background"].inputs["Color"].default_value = (0, 0, 0, 1); sc.world = w

sc.render.engine = "BLENDER_EEVEE"
ee = sc.eevee
ee.taa_render_samples = 48
if hasattr(ee, "use_raytracing"):
    ee.use_raytracing = True
sc.view_settings.view_transform = "Standard"
sc.render.resolution_x = sc.render.resolution_y = SIZE
sc.render.image_settings.file_format = "JPEG"; sc.render.image_settings.quality = 94

# bloom
cg = bpy.data.node_groups.new("Comp", "CompositorNodeTree")
cg.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
rl = cg.nodes.new("CompositorNodeRLayers"); gl = cg.nodes.new("CompositorNodeGlare"); out = cg.nodes.new("NodeGroupOutput")
gl.inputs["Type"].default_value = "Fog Glow"
for k, v in (("Threshold", 1.2), ("Size", 0.6), ("Strength", 0.35)):
    if k in gl.inputs:
        gl.inputs[k].default_value = v
cg.links.new(rl.outputs["Image"], gl.inputs["Image"]); cg.links.new(gl.outputs["Image"], out.inputs[0])
sc.compositing_node_group = cg; sc.render.use_compositing = True

os.makedirs(OUT, exist_ok=True)
frames = [18, 60, 96, 118, 190] if MODE == "look" else range(0, LAST + 1)
for f in frames:
    p = os.path.join(OUT, f"{f:04d}.jpg")
    if MODE != "look" and os.path.exists(p) and os.path.getsize(p) > 8000:
        continue
    sc.frame_set(f); sc.render.filepath = p
    bpy.ops.render.render(write_still=True)
print("done")
