"""Procedural acoustic guitar model for Three.js.

Run headless:
  blender -b --factory-startup -P blender/make_guitar.py -- --glb public/guitar.glb [--render preview.png]

Coordinate system (Blender, Z up):
  +Y = neck direction, body top plate (soundboard) at z = 0, body back at z = -0.105.
  glTF export converts (x, y, z) -> (x, z, -y).
"""

import bpy
import bmesh
import math
import sys
import os
import traceback
from mathutils import Vector, Matrix

# ---------------------------------------------------------------- constants

SCALE_LEN = 0.648            # bridge <-> nut
JOINT_Y = 0.250              # neck/body joint (body top edge)
NUT_Y = JOINT_Y + SCALE_LEN * (1 - 2 ** (-14 / 12))
BRIDGE_Y = NUT_Y - SCALE_LEN
BODY_DEPTH = 0.105
SOUNDHOLE_R = 0.048
SOUNDHOLE_Y = 0.045

FB_TOP = 0.007               # fretboard top surface
FB_NUT_W = 0.0437
FB_END_Y = 0.270
FB_END_W = 0.0605

HEAD_LEN = 0.175
HEAD_TILT = math.radians(-13)

BRIDGE_X = [-0.0265, -0.0159, -0.0053, 0.0053, 0.0159, 0.0265]
NUT_X = [-0.020, -0.012, -0.004, 0.004, 0.012, 0.020]
STRING_R = [0.0012, 0.0011, 0.0010, 0.0009, 0.0008, 0.0007]
STRING_Z_BRIDGE = 0.016
STRING_Z_NUT = 0.0125
POST_YL = [0.145, 0.095, 0.045, 0.045, 0.095, 0.145]   # bass strings to far posts

HEAD_M = Matrix.Translation((0, NUT_Y, FB_TOP)) @ Matrix.Rotation(HEAD_TILT, 4, "X")


def fret_y(n):
    return NUT_Y - SCALE_LEN * (1 - 2 ** (-n / 12))


def fb_half_w(y):
    t = (NUT_Y - y) / (NUT_Y - FB_END_Y)
    return (FB_NUT_W + (FB_END_W - FB_NUT_W) * t) / 2


def head_half_w(yl):
    return (0.046 + (0.070 - 0.046) * (yl / HEAD_LEN)) / 2


# ---------------------------------------------------------------- scene reset

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.images,
             bpy.data.curves, bpy.data.lights, bpy.data.cameras):
    for block in list(coll):
        try:
            coll.remove(block)
        except Exception:
            pass


# ---------------------------------------------------------------- materials

def principled(name, color, rough=0.5, metal=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    b = mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    return mat


def wood(name, c_dark, c_light, rough=0.45, grain_scale=7.0, stretch=0.25):
    """Procedural wood (wave + noise), later baked into an image for glTF."""
    mat = principled(name, c_light, rough)
    nt = mat.node_tree
    b = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1.0, stretch, 1.0)
    wav = nt.nodes.new("ShaderNodeTexWave")
    wav.wave_type = "BANDS"
    wav.bands_direction = "X"
    wav.inputs["Scale"].default_value = grain_scale
    wav.inputs["Distortion"].default_value = 7.0
    wav.inputs["Detail"].default_value = 3.0
    wav.inputs["Detail Scale"].default_value = 1.4
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.30
    ramp.color_ramp.elements[0].color = (*c_dark, 1.0)
    ramp.color_ramp.elements[1].position = 0.75
    ramp.color_ramp.elements[1].color = (*c_light, 1.0)
    nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], wav.inputs["Vector"])
    nt.links.new(wav.outputs["Color"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    return mat


MAT_SPRUCE = wood("spruce_top", (0.45, 0.27, 0.10), (0.68, 0.46, 0.21), rough=0.40, grain_scale=9.0)
MAT_MAH_BODY = wood("mahogany_body", (0.17, 0.052, 0.026), (0.32, 0.11, 0.05), rough=0.5, grain_scale=6.0)
MAT_MAH_NECK = wood("mahogany_neck", (0.17, 0.052, 0.026), (0.32, 0.11, 0.05), rough=0.5, grain_scale=6.0)
MAT_MAH_HEAD = wood("mahogany_head", (0.17, 0.052, 0.026), (0.32, 0.11, 0.05), rough=0.5, grain_scale=6.0)
MAT_EBONY = wood("ebony", (0.016, 0.011, 0.008), (0.045, 0.030, 0.020), rough=0.55, grain_scale=14.0, stretch=0.35)
MAT_ROSEWOOD = wood("rosewood", (0.045, 0.016, 0.010), (0.085, 0.034, 0.020), rough=0.45, grain_scale=12.0, stretch=0.3)
MAT_HEEL = principled("mahogany_flat", (0.22, 0.075, 0.036), 0.5)
MAT_BONE = principled("bone", (0.86, 0.82, 0.70), 0.32)
MAT_PEARL = principled("pearl", (0.93, 0.94, 0.88), 0.15)
MAT_FRET = principled("fret_metal", (0.72, 0.73, 0.75), 0.28, metal=1.0)
MAT_CHROME = principled("chrome", (0.90, 0.91, 0.93), 0.15, metal=1.0)
MAT_STEEL = principled("steel_string", (0.80, 0.81, 0.83), 0.25, metal=1.0)
MAT_BRONZE = principled("bronze_string", (0.85, 0.58, 0.26), 0.32, metal=1.0)
MAT_ROSETTE_D = principled("rosette_dark", (0.02, 0.014, 0.010), 0.4)
MAT_ROSETTE_L = principled("rosette_light", (0.62, 0.52, 0.38), 0.4)
MAT_TORTOISE = principled("pickguard", (0.05, 0.016, 0.008), 0.22)


# ---------------------------------------------------------------- mesh helpers

def obj_from_bm(name, bm, mat=None):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    if mat:
        ob.data.materials.append(mat)
    return ob


def outline_pts():
    right = [
        (0.000, -0.250), (0.070, -0.242), (0.130, -0.220), (0.175, -0.180),
        (0.1975, -0.120), (0.1975, -0.060), (0.180, -0.010), (0.155, 0.030),
        (0.150, 0.060), (0.158, 0.100), (0.175, 0.145), (0.178, 0.175),
        (0.165, 0.210), (0.130, 0.238), (0.080, 0.250), (0.000, 0.250),
    ]
    pts = list(right)
    pts += [(-x, y) for (x, y) in reversed(right[1:-1])]
    return pts


def offset_pts(pts, d):
    """Inset polygon by d (works for CCW outline, smooth-ish curves)."""
    n = len(pts)
    out = []
    for i in range(n):
        p = Vector(pts[i])
        a = Vector(pts[i - 1])
        b = Vector(pts[(i + 1) % n])

        def nrm(u, v):
            e = v - u
            return Vector((e.y, -e.x)).normalized()

        m = nrm(a, p) + nrm(p, b)
        if m.length < 1e-9:
            m = nrm(a, p)
        m.normalize()
        out.append((p.x - m.x * d, p.y - m.y * d))
    return out


def chaikin(pts, iterations=2):
    """Corner-cutting smoothing for a rounder body silhouette."""
    for _ in range(iterations):
        out = []
        n = len(pts)
        for i in range(n):
            p = Vector(pts[i])
            q = Vector(pts[(i + 1) % n])
            out.append((0.75 * p.x + 0.25 * q.x, 0.75 * p.y + 0.25 * q.y))
            out.append((0.25 * p.x + 0.75 * q.x, 0.25 * p.y + 0.75 * q.y))
        pts = out
    return pts


def extruded_solid(bm, pts2d, z_top, z_bottom):
    verts = [bm.verts.new((x, y, z_top)) for x, y in pts2d]
    face = bm.faces.new(verts)
    ret = bmesh.ops.extrude_face_region(bm, geom=[face])
    new_verts = [e for e in ret["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=new_verts, vec=(0, 0, z_bottom - z_top))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)


def tapered_box_bm(y0, w0, y1, w1, z0, z1, y_extra0=0.0):
    """Box with different widths at y0/y1 (4 side faces + top/bottom)."""
    bm = bmesh.new()
    c = [
        (-w0 / 2, y0 - y_extra0, z0), (w0 / 2, y0 - y_extra0, z0),
        (w0 / 2, y0 - y_extra0, z1), (-w0 / 2, y0 - y_extra0, z1),
        (-w1 / 2, y1, z0), (w1 / 2, y1, z0),
        (w1 / 2, y1, z1), (-w1 / 2, y1, z1),
    ]
    v = [bm.verts.new(p) for p in c]
    faces = [(0, 1, 2, 3), (5, 4, 7, 6), (4, 0, 3, 7), (1, 5, 6, 2), (3, 2, 6, 7), (4, 5, 1, 0)]
    for f in faces:
        bm.faces.new([v[i] for i in f])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def cone_bm(bm, r, depth, M, segments=16):
    try:
        bmesh.ops.create_cone(bm, cap_ends=True, segments=segments, radius1=r, radius2=r,
                              depth=depth, matrix=M)
    except TypeError:
        bmesh.ops.create_cone(bm, cap_ends=True, segments=segments, diameter1=2 * r,
                              diameter2=2 * r, depth=depth, matrix=M)


def cube_bm(bm, sx, sy, sz, M):
    bmesh.ops.create_cube(bm, size=1.0, matrix=M @ Matrix.Diagonal((sx, sy, sz, 1.0)))


def align_matrix(p1, p2):
    """Translation+rotation with local Z along p1->p2 and local X lateral (world X-ish)."""
    d = p2 - p1
    z = d.normalized()
    x = Vector((1, 0, 0))
    x = x - z * x.dot(z)
    if x.length < 1e-6:
        x = Vector((0, 1, 0)) - z * Vector((0, 1, 0)).dot(z)
    x.normalize()
    y = z.cross(x)
    rot = Matrix((x, y, z)).transposed().to_4x4()
    return Matrix.Translation((p1 + p2) / 2) @ rot


def add_bevel(ob, width, segments=3, angle=35):
    mod = ob.modifiers.new("bev", "BEVEL")
    mod.width = width
    mod.segments = segments
    mod.limit_method = "ANGLE"
    mod.angle_limit = math.radians(angle)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.modifier_apply(modifier=mod.name)


def smooth(ob):
    for p in ob.data.polygons:
        p.use_smooth = True


# ---------------------------------------------------------------- body

outline = chaikin(outline_pts(), 2)

bm_body = bmesh.new()
extruded_solid(bm_body, outline, 0.0, -BODY_DEPTH)
body = obj_from_bm("body", bm_body)

# hollow cavity (top plate 3 mm, back 5 mm, sides 4 mm)
bm_cav = bmesh.new()
extruded_solid(bm_cav, offset_pts(outline, 0.004), -0.003, -0.100)
cav = obj_from_bm("_cav", bm_cav)

# soundhole through the top plate only
bm_hole = bmesh.new()
cone_bm(bm_hole, SOUNDHOLE_R, 0.02, Matrix.Translation((0, SOUNDHOLE_Y, -0.004)), segments=48)
hole = obj_from_bm("_hole", bm_hole)

for cutter in (cav, hole):
    mod = body.modifiers.new("bool", "BOOLEAN")
    mod.object = cutter
    mod.operation = "DIFFERENCE"
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.modifier_apply(modifier=mod.name)
for cutter in (cav, hole):
    me = cutter.data
    bpy.data.objects.remove(cutter, do_unlink=True)
    bpy.data.meshes.remove(me)

add_bevel(body, 0.006, segments=4, angle=35)

# boolean modifiers leave an empty slot behind — drop it before assigning
body.data.materials.clear()
body.data.materials.append(MAT_SPRUCE)   # 0
body.data.materials.append(MAT_MAH_BODY)  # 1
for p in body.data.polygons:
    p.material_index = 0 if p.normal.z > 0.93 else 1
print("body slots:", [m.name if m else "None" for m in body.data.materials],
      "indices:", sorted(set(p.material_index for p in body.data.polygons)))


# ---------------------------------------------------------------- neck / fretboard / headstock

bm = tapered_box_bm(NUT_Y, FB_NUT_W - 0.002, 0.300, 0.0570, -0.0245, 0.0, y_extra0=0.002)
neck = obj_from_bm("neck", bm, MAT_MAH_NECK)
add_bevel(neck, 0.008, segments=5, angle=40)

bm = tapered_box_bm(FB_END_Y, FB_END_W, NUT_Y + 0.001, FB_NUT_W, 0.0, FB_TOP, y_extra0=0.004)
fretboard = obj_from_bm("fretboard", bm, MAT_EBONY)
add_bevel(fretboard, 0.0015, segments=2, angle=40)

bm = tapered_box_bm(0.235, 0.056, 0.312, 0.056, -0.070, 0.002)
heel = obj_from_bm("heel", bm, MAT_HEEL)
add_bevel(heel, 0.013, segments=6, angle=40)

bm = tapered_box_bm(0.0, 0.046, HEAD_LEN, 0.070, -0.016, 0.0)
headstock = obj_from_bm("headstock", bm, MAT_MAH_HEAD)
headstock.matrix_world = HEAD_M
add_bevel(headstock, 0.004, segments=3, angle=40)

# nut
bm = tapered_box_bm(NUT_Y - 0.0025, FB_NUT_W, NUT_Y + 0.0025, FB_NUT_W, FB_TOP, 0.0115)
nut = obj_from_bm("nut", bm, MAT_BONE)


# ---------------------------------------------------------------- frets + inlays

for n in range(1, 15):
    y = fret_y(n)
    hw = fb_half_w(y)
    bm = bmesh.new()
    cube_bm(bm, (hw - 0.0012) * 2, 0.0024, 0.0018,
            Matrix.Translation((0, y, FB_TOP + 0.0009)))
    obj_from_bm(f"fret_{n}", bm, MAT_FRET)

for n in (3, 5, 7, 9, 12):
    y = (fret_y(n - 1) + fret_y(n)) / 2
    xs = (0.0,) if n != 12 else (-0.011, 0.011)
    for k, x in enumerate(xs):
        bm = bmesh.new()
        cone_bm(bm, 0.004, 0.002, Matrix.Translation((x, y, FB_TOP - 0.0009)), segments=24)
        obj_from_bm(f"inlay_{n}_{k}", bm, MAT_PEARL)


# ---------------------------------------------------------------- bridge / saddle / pins

bm = bmesh.new()
cube_bm(bm, 0.170, 0.034, 0.009, Matrix.Translation((0, BRIDGE_Y, 0.0045)))
bridge = obj_from_bm("bridge", bm, MAT_ROSEWOOD)
add_bevel(bridge, 0.004, segments=3, angle=40)

bm = bmesh.new()
cube_bm(bm, 0.062, 0.003, 0.006, Matrix.Translation((0, BRIDGE_Y, 0.012)))
saddle = obj_from_bm("saddle", bm, MAT_BONE)

for i, x in enumerate(BRIDGE_X):
    bm = bmesh.new()
    cone_bm(bm, 0.0024, 0.004, Matrix.Translation((x, BRIDGE_Y - 0.011, 0.011)), segments=16)
    obj_from_bm(f"pin_{i}", bm, MAT_BONE)


# ---------------------------------------------------------------- rosette + pickguard

for idx, (r, m) in enumerate(((0.0505, MAT_ROSETTE_D), (0.0545, MAT_ROSETTE_L))):
    bpy.ops.mesh.primitive_torus_add(major_radius=r, minor_radius=0.0015,
                                     major_segments=72, minor_segments=8,
                                     location=(0, SOUNDHOLE_Y, 0.0004))
    ob = bpy.context.active_object
    ob.name = f"rosette_{idx}"
    ob.scale = (1, 1, 0.35)
    ob.data.materials.append(m)
    smooth(ob)

bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=1.0, depth=0.0006,
                                    location=(0.080, 0.005, 0.0002))
pg = bpy.context.active_object
pg.name = "pickguard"
pg.scale = (0.043, 0.072, 1)
pg.data.materials.append(MAT_TORTOISE)


# ---------------------------------------------------------------- tuners

bm_tun = bmesh.new()
for i, yl in enumerate(POST_YL):
    side = -1 if i < 3 else 1
    hw = head_half_w(yl)
    px = side * hw * 0.62
    # post (along headstock normal)
    cone_bm(bm_tun, 0.0032, 0.016, HEAD_M @ Matrix.Translation((px, yl, 0.008)), segments=20)
    # shaft (lateral)
    shaft_M = HEAD_M @ Matrix.Translation((side * (hw + 0.005), yl, -0.007)) @ \
        Matrix.Rotation(math.radians(90), 4, "Y")
    cone_bm(bm_tun, 0.0022, 0.016, shaft_M, segments=12)
    # button
    btn_M = HEAD_M @ Matrix.Translation((side * (hw + 0.014), yl, -0.007))
    cube_bm(bm_tun, 0.006, 0.013, 0.009, btn_M)
tuners = obj_from_bm("tuners", bm_tun, MAT_CHROME)


# ---------------------------------------------------------------- strings

for i in range(6):
    p_bridge = Vector((BRIDGE_X[i], BRIDGE_Y, STRING_Z_BRIDGE))
    p_nut = Vector((NUT_X[i], NUT_Y, STRING_Z_NUT))
    side = -1 if i < 3 else 1
    hw = head_half_w(POST_YL[i])
    p_post = HEAD_M @ Vector((side * hw * 0.62, POST_YL[i], 0.012))

    bm = bmesh.new()
    cone_bm(bm, STRING_R[i], (p_nut - p_bridge).length,
            align_matrix(p_bridge, p_nut), segments=14)
    ob = obj_from_bm(f"string_{i}", bm, MAT_BRONZE if i < 3 else MAT_STEEL)
    smooth(ob)

    bm = bmesh.new()
    cone_bm(bm, STRING_R[i] * 0.9, (p_post - p_nut).length,
            align_matrix(p_nut, p_post), segments=12)
    ob = obj_from_bm(f"stringhead_{i}", bm, MAT_BRONZE if i < 3 else MAT_STEEL)
    smooth(ob)


# ---------------------------------------------------------------- bake wood textures

def ensure_uvs(ob):
    if ob.data.uv_layers:
        return
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.02)
    bpy.ops.object.mode_set(mode="OBJECT")


def img_stats(img, tag):
    px = list(img.pixels[:])
    n = len(px) // 4
    vals = [px[i * 4] for i in range(0, n, 37)]
    mean = sum(vals) / len(vals)
    var = sum((v - mean) ** 2 for v in vals) / len(vals)
    print(f"[bake:{tag}] mean={mean:.4f} std={var ** 0.5:.4f}")
    return mean, var ** 0.5


def deactivate_other_nodes(except_mat):
    """Bakers target every active image node — keep only ours active."""
    for m in bpy.data.materials:
        if not m.use_nodes or m is except_mat:
            continue
        nt = m.node_tree
        if not nt:
            continue
        for n in nt.nodes:
            if n.bl_idname == "ShaderNodeTexImage":
                n.select = False
        if "Principled BSDF" in nt.nodes:
            nt.nodes.active = nt.nodes["Principled BSDF"]


def bake_material(ob, mat, img_name, res=1024):
    """Bake procedural node wood into an image, then wire the image to Base Color."""
    scene = bpy.context.scene
    prev_engine = scene.render.engine
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    try:
        ensure_uvs(ob)
        img = bpy.data.images.new(img_name, res, res, alpha=False)
        nt = mat.node_tree
        node = nt.nodes.new("ShaderNodeTexImage")
        node.image = img
        deactivate_other_nodes(mat)
        for n in nt.nodes:
            n.select = False
        node.select = True
        nt.nodes.active = node

        bpy.ops.object.select_all(action="DESELECT")
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.bake(type="DIFFUSE", pass_filter={"COLOR"}, margin=8, use_clear=True)
        mean, std = img_stats(img, img_name)
        if std < 0.005:
            raise RuntimeError(f"bake produced flat image (mean={mean:.3f} std={std:.4f})")
        img.pack()
        node.select = False

        bsdf = nt.nodes["Principled BSDF"]
        out = nt.nodes["Material Output"]
        nt.links.new(node.outputs["Color"], bsdf.inputs["Base Color"])
        for n in list(nt.nodes):
            if n not in (node, bsdf, out):
                nt.nodes.remove(n)
    except Exception:
        traceback.print_exc()
        # fallback: flat exportable color
        bsdf = mat.node_tree.nodes["Principled BSDF"]
        out = mat.node_tree.nodes["Material Output"]
        for n in list(mat.node_tree.nodes):
            if n not in (bsdf, out):
                mat.node_tree.nodes.remove(n)
        bsdf.inputs["Base Color"].default_value = (0.45, 0.27, 0.10, 1.0)
    finally:
        scene.render.engine = prev_engine


bake_material(body, MAT_SPRUCE, "spruce_top")
bake_material(body, MAT_MAH_BODY, "mahogany_body")
bake_material(neck, MAT_MAH_NECK, "mahogany_neck")
bake_material(headstock, MAT_MAH_HEAD, "mahogany_head")
bake_material(fretboard, MAT_EBONY, "ebony")
bake_material(bridge, MAT_ROSEWOOD, "rosewood")


# ---------------------------------------------------------------- export / render

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
args = dict(zip(argv[::2], argv[1::2]))

glb_path = args.get("--glb", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           "..", "public", "guitar.glb"))
os.makedirs(os.path.dirname(os.path.abspath(glb_path)), exist_ok=True)
bpy.ops.export_scene.gltf(filepath=glb_path, export_format="GLB", export_apply=True)
print("EXPORTED:", os.path.abspath(glb_path))

render_path = args.get("--render")
if render_path:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 48
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 960
    scene.render.resolution_y = 720

    cam_data = bpy.data.cameras.new("cam")
    cam_data.lens = 42
    cam = bpy.data.objects.new("cam", cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = (0.62, -1.35, 1.05)
    direction = Vector((0, 0.27, -0.03)) - cam.location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam

    key_data = bpy.data.lights.new("key", "AREA")
    key_data.energy = 200
    key_data.size = 2.5
    key = bpy.data.objects.new("key", key_data)
    bpy.context.collection.objects.link(key)
    key.location = (1.6, -0.6, 2.6)
    key.rotation_euler = ((Vector((0, 0.2, -0.05)) - key.location).to_track_quat("-Z", "Y").to_euler())

    fill_data = bpy.data.lights.new("fill", "AREA")
    fill_data.energy = 90
    fill_data.size = 3.0
    fill = bpy.data.objects.new("fill", fill_data)
    bpy.context.collection.objects.link(fill)
    fill.location = (-1.8, 0.9, 1.4)
    fill.rotation_euler = ((Vector((0, 0.2, -0.05)) - fill.location).to_track_quat("-Z", "Y").to_euler())

    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.09, 0.095, 0.11, 1)
    scene.world = world

    scene.render.filepath = render_path
    bpy.ops.render.render(write_still=True)
    print("RENDERED:", render_path)

print("DONE")
