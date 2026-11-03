# Basement's rooms as real 3D scenes, rendered offline on the desktop GPU.
#   blender -b -P render/rooms.py -- <out dir> <samples> <percent> <neon|basement|rain|grid|mall>
# Each room renders two light passes of the same frame (room.png: the room's own lights, screen dark;
# tv.png: only the TV's glow, white) and writes where things landed on screen to room.json. A room with a
# window adds plate.png (the world past the glass) and mask.png (alpha: where the glass is actually visible).
# The launcher adds tv.png tinted by the live picture, so a game's light really lands on everything.
import json
import math
import os
import random
import sys

import bmesh
import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector, noise

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
HERE = os.path.dirname(os.path.abspath(__file__)).replace('\\', '/') + '/'
OUT = argv[0] if argv else HERE + 'out'
SAMPLES = int(argv[1]) if len(argv) > 1 else 256
PERCENT = int(argv[2]) if len(argv) > 2 else 100
ROOM = argv[3] if len(argv) > 3 else 'neon'
TEX = HERE + 'tex/'
random.seed({'neon': 1994, 'basement': 1987, 'rain': 2001, 'grid': 1982, 'mall': 1993}[ROOM])

scene = bpy.context.scene
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)
W, H = 1920, 1080
scene.render.resolution_x, scene.render.resolution_y = W, H
scene.render.resolution_percentage = PERCENT
scene.render.engine = 'CYCLES'
scene.cycles.samples = SAMPLES
scene.cycles.use_denoising = True
scene.cycles.max_bounces = 8
scene.cycles.caustics_reflective = False
scene.cycles.caustics_refractive = False
prefs = bpy.context.preferences.addons['cycles'].preferences
for kind in ('OPTIX', 'CUDA'):
    try:
        prefs.compute_device_type = kind
        prefs.get_devices()
        for d in prefs.devices:
            d.use = d.type != 'CPU'
        scene.cycles.device = 'GPU'
        break
    except TypeError:
        continue
scene.view_settings.view_transform = 'Standard'
scene.view_settings.look = 'None'


# ---- materials ---------------------------------------------------------------------------------

def srgb(hexv):
    def f(c):
        c /= 255
        return c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4
    return (f((hexv >> 16) & 255), f((hexv >> 8) & 255), f(hexv & 255))


def mat(name, color=(.5, .5, .5), rough=.5, metal=0., emit=None, strength=0.):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*color, 1)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    if emit is not None:
        b.inputs['Emission Color'].default_value = (*emit, 1)
        b.inputs['Emission Strength'].default_value = strength
    return m


def noisy(name, c1, c2, scale=40., rough=.5, bump=0., stretch=(1, 1, 1)):
    m = mat(name, c1, rough)
    t = m.node_tree
    b = t.nodes['Principled BSDF']
    tc = t.nodes.new('ShaderNodeTexCoord')
    mp = t.nodes.new('ShaderNodeMapping')
    mp.inputs['Scale'].default_value = stretch
    n = t.nodes.new('ShaderNodeTexNoise')
    n.inputs['Scale'].default_value = scale
    n.inputs['Detail'].default_value = 8
    r = t.nodes.new('ShaderNodeValToRGB')
    r.color_ramp.elements[0].position = .35
    r.color_ramp.elements[0].color = (*c1, 1)
    r.color_ramp.elements[1].position = .7
    r.color_ramp.elements[1].color = (*c2, 1)
    t.links.new(tc.outputs['Object'], mp.inputs['Vector'])
    t.links.new(mp.outputs['Vector'], n.inputs['Vector'])
    t.links.new(n.outputs['Fac'], r.inputs['Fac'])
    t.links.new(r.outputs['Color'], b.inputs['Base Color'])
    if bump:
        bp = t.nodes.new('ShaderNodeBump')
        bp.inputs['Strength'].default_value = bump
        bp.inputs['Distance'].default_value = .02
        t.links.new(n.outputs['Fac'], bp.inputs['Height'])
        t.links.new(bp.outputs['Normal'], b.inputs['Normal'])
    return m


def tex_mat(name, file, repeat=1., rough=.6, bump=0., emit=0., height=None):
    """An image wrapped on anything: box-projected in object space, so no UVs needed."""
    m = mat(name, (1, 1, 1), rough)
    t = m.node_tree
    b = t.nodes['Principled BSDF']
    tc = t.nodes.new('ShaderNodeTexCoord')
    mp = t.nodes.new('ShaderNodeMapping')
    mp.inputs['Scale'].default_value = (repeat, repeat, repeat)
    tx = t.nodes.new('ShaderNodeTexImage')
    tx.image = bpy.data.images.load(TEX + file)
    tx.projection = 'BOX'
    tx.projection_blend = .25
    t.links.new(tc.outputs['Object'], mp.inputs['Vector'])
    t.links.new(mp.outputs['Vector'], tx.inputs['Vector'])
    t.links.new(tx.outputs['Color'], b.inputs['Base Color'])
    if emit:
        t.links.new(tx.outputs['Color'], b.inputs['Emission Color'])
        b.inputs['Emission Strength'].default_value = emit
    if bump:
        bp = t.nodes.new('ShaderNodeBump')
        bp.inputs['Strength'].default_value = bump
        bp.inputs['Distance'].default_value = .012
        src = tx
        if height:
            src = t.nodes.new('ShaderNodeTexImage')
            src.image = bpy.data.images.load(TEX + height)
            src.image.colorspace_settings.name = 'Non-Color'
            src.projection = 'BOX'
            src.projection_blend = .25
            t.links.new(mp.outputs['Vector'], src.inputs['Vector'])
        t.links.new(src.outputs['Color'], bp.inputs['Height'])
        t.links.new(bp.outputs['Normal'], b.inputs['Normal'])
    return m


def face_mat(name, file, rough=.45, emit=0.):
    """A picture on the front of a flat box: UVs made in face()."""
    m = mat(name, (1, 1, 1), rough)
    t = m.node_tree
    b = t.nodes['Principled BSDF']
    tx = t.nodes.new('ShaderNodeTexImage')
    tx.image = bpy.data.images.load(TEX + file)
    t.links.new(tx.outputs['Color'], b.inputs['Base Color'])
    if emit:
        t.links.new(tx.outputs['Color'], b.inputs['Emission Color'])
        b.inputs['Emission Strength'].default_value = emit
    return m


# ---- geometry helpers --------------------------------------------------------------------------

def link(o):
    bpy.context.scene.collection.objects.link(o)
    return o


def box(name, size, loc, material, bevel=0., rot=(0, 0, 0), segs=4):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1)
    bmesh.ops.scale(bm, vec=size, verts=bm.verts)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = link(bpy.data.objects.new(name, me))
    o.location = loc
    o.rotation_euler = rot
    me.materials.append(material)
    if bevel:
        m = o.modifiers.new('bevel', 'BEVEL')
        m.width = bevel
        m.segments = segs
        m.limit_method = 'ANGLE'
    for p in me.polygons:
        p.use_smooth = True
    return o


def puffy(name, size, loc, material, rot=(0, 0, 0), lump=.012, level=3):
    """Cushions, couch arms, anything stuffed: a rounded box with some unevenness in it."""
    o = box(name, size, loc, material, rot=rot)
    b = o.modifiers.new('bevel', 'BEVEL')
    b.width = min(size) * .36
    b.segments = 3
    s = o.modifiers.new('sub', 'SUBSURF')
    s.levels = s.render_levels = level
    tx = bpy.data.textures.new(name + 'lump', 'CLOUDS')
    tx.noise_scale = max(size) * .55
    d = o.modifiers.new('lumps', 'DISPLACE')
    d.texture = tx
    d.strength = lump
    d.mid_level = .5
    return o


def face(o, w, h):
    """UVs across a flat box's X and Z, so a picture fills its front."""
    me = o.data
    uv = me.uv_layers.new(name='UV')
    for poly in me.polygons:
        for li in poly.loop_indices:
            v = me.vertices[me.loops[li].vertex_index].co
            uv.data[li].uv = (v.x / w + .5, v.z / h + .5)
    return o


def cyl(name, r, depth, loc, material, rot=(0, 0, 0), verts=48, r2=None):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=verts, radius1=r, radius2=r if r2 is None else r2, depth=depth)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = link(bpy.data.objects.new(name, me))
    o.location = loc
    o.rotation_euler = rot
    me.materials.append(material)
    for p in me.polygons:
        p.use_smooth = len(p.vertices) == 4
    return o


def lathe(name, profile, loc, material, verts=64):
    """Spin [(radius, z), ...] around Z."""
    bm = bmesh.new()
    rings = []
    for r, z in profile:
        rings.append([bm.verts.new((r * math.cos(2 * math.pi * i / verts), r * math.sin(2 * math.pi * i / verts), z)) for i in range(verts)])
    for a, b in zip(rings, rings[1:]):
        for i in range(verts):
            bm.faces.new((a[i], a[(i + 1) % verts], b[(i + 1) % verts], b[i]))
    bm.faces.new(rings[0][::-1])
    bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = link(bpy.data.objects.new(name, me))
    o.location = loc
    me.materials.append(material)
    for p in me.polygons:
        p.use_smooth = True
    return o


def curve(name, pts, radius, material, loc=(0, 0, 0)):
    c = bpy.data.curves.new(name, 'CURVE')
    c.dimensions = '3D'
    c.bevel_depth = radius
    c.bevel_resolution = 4
    c.resolution_u = 16
    s = c.splines.new('NURBS')
    s.points.add(len(pts) - 1)
    for p, v in zip(s.points, pts):
        p.co = (*v, 1)
    s.use_endpoint_u = True
    s.order_u = 4
    o = link(bpy.data.objects.new(name, c))
    o.location = loc
    c.materials.append(material)
    return o


def sheet(name, w, h, nx, ny, fn, loc, material, rot=(0, 0, 0)):
    """A cloth: grid in X/Z, pushed around by fn(u, v) -> (dx, dy, dz)."""
    bm = bmesh.new()
    g = []
    for j in range(ny + 1):
        row = []
        for i in range(nx + 1):
            u, v = i / nx, j / ny
            d = fn(u, v)
            row.append(bm.verts.new(((u - .5) * w + d[0], d[1], (v - .5) * h + d[2])))
        g.append(row)
    for j in range(ny):
        for i in range(nx):
            bm.faces.new((g[j][i], g[j][i + 1], g[j + 1][i + 1], g[j + 1][i]))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = link(bpy.data.objects.new(name, me))
    o.location = loc
    o.rotation_euler = rot
    me.materials.append(material)
    for p in me.polygons:
        p.use_smooth = True
    return o


def ball(name, r, loc, material, segs=32):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=segs // 2, radius=r)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = link(bpy.data.objects.new(name, me))
    o.location = loc
    me.materials.append(material)
    for p in me.polygons:
        p.use_smooth = True
    return o


lights = []
glowing = []  # things that shine by themselves: off in the TV pass


def glow(o):
    glowing.append(o)
    return o


def area(name, loc, size, color, power, target=None, size_y=None):
    l = bpy.data.lights.new(name, 'AREA')
    l.shape = 'RECTANGLE'
    l.size = size
    l.size_y = size_y or size
    l.color = color
    l.energy = power
    o = link(bpy.data.objects.new(name, l))
    o.location = loc
    if target:
        o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    lights.append(o)
    return o


def point(name, loc, color, power, soft=.05, hidden=False):
    l = bpy.data.lights.new(name, 'POINT')
    l.color = color
    l.energy = power
    l.shadow_soft_size = soft
    o = link(bpy.data.objects.new(name, l))
    o.location = loc
    if hidden:
        o.visible_transmission = False
        o.visible_glossy = False
    lights.append(o)
    return o


def spot(name, loc, target, color, power, angle=50, soft=.012):
    l = bpy.data.lights.new(name, 'SPOT')
    l.color = color
    l.energy = power
    l.spot_size = math.radians(angle)
    l.spot_blend = .15
    l.shadow_soft_size = soft
    o = link(bpy.data.objects.new(name, l))
    o.location = loc
    o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    lights.append(o)
    return o


# ---- common materials ---------------------------------------------------------------------------

M_PLASTIC = mat('plastic', srgb(0x17151b), .38)
M_PLASTIC2 = mat('plastic2', srgb(0x26232c), .5)
M_CREAM = mat('cream', srgb(0xcfc6b4), .42)
M_GRAY = mat('gray', srgb(0x8e8c90), .45)
M_RED = mat('red', srgb(0xa81f2c), .34)
M_DARKRED = mat('darkred', srgb(0x5c1420), .4)
M_METAL = mat('metal', srgb(0xb9b9c4), .25, 1)
M_BRASS = mat('brass', srgb(0xb08a3e), .3, 1)
M_BLACK = mat('black', srgb(0x08080a), .45)
M_RUBBER = mat('rubber', srgb(0x0c0b0e), .7)
M_WHITE = mat('white', srgb(0xd8d4cc), .55)
M_PAPER = mat('paper', srgb(0xc8c2b2), .85)
LABELS = [mat(f'label{i}', srgb(c), .5) for i, c in enumerate((0xf0c23c, 0x2fc2bc, 0xd8453c, 0x4a78d8, 0xe0e0d8, 0x8a4ac8, 0x48b050))]
CARTS = [mat(f'cart{i}', srgb(c), .42) for i, c in enumerate((0x8f8f96, 0xc23a2e, 0x263a78, 0x3a3a40, 0x2a7a4a))]
BOOKS = [mat(f'book{i}', srgb(c), r) for i, (c, r) in enumerate((
    (0x7a2a24, .5), (0x24446a, .45), (0x2c5a3c, .5), (0xb88a34, .4), (0x4a2a5c, .5), (0xc8c0ac, .6),
    (0x1c1c22, .4), (0xa4442c, .5), (0x305c70, .45), (0x6a5a3a, .6)))]


# ---- props --------------------------------------------------------------------------------------

def books(prefix, x0, x1, y, z, depth=.2, lo=.17, hi=.27, wmin=.016, wmax=.045):
    """A row of spines standing on a shelf."""
    x = x0
    i = 0
    while x < x1:
        t = random.uniform(wmin, wmax)
        h = random.uniform(lo, hi)
        lean = random.uniform(-.02, .02) if random.random() < .18 else 0
        box(f'{prefix}{i}', (t, depth * random.uniform(.8, 1), h), (x + t / 2, y, z + h / 2), random.choice(BOOKS), bevel=.0015, rot=(0, lean, 0), segs=1)
        if random.random() < .35:
            box(f'{prefix}b{i}', (t * 1.01, .004, h * .08), (x + t / 2, y - depth / 2, z + h * random.uniform(.55, .85)), M_PAPER, rot=(0, lean, 0))
        x += t + random.choice((0, 0, .001))
        if random.random() < .04:
            x += random.uniform(.03, .09)
        i += 1


def bookcase(prefix, x, y, w, h, material, shelves=5, depth=.26):
    box(prefix + 'l', (.024, depth, h), (x - w / 2, y, h / 2 - .75), material)
    box(prefix + 'r', (.024, depth, h), (x + w / 2, y, h / 2 - .75), material)
    box(prefix + 't', (w, depth, .024), (x, y, h - .75), material)
    box(prefix + 'back', (w, .01, h), (x, y + depth / 2, h / 2 - .75), M_BLACK)
    for k in range(shelves):
        z = -.72 + k * h / shelves
        box(f'{prefix}s{k}', (w, depth, .022), (x, y, z), material)
        books(f'{prefix}bk{k}', x - w / 2 + .03, x + w / 2 - .03 - random.uniform(0, .3), y - .015, z + .012, depth=depth * .7, lo=.15, hi=min(.26, h / shelves * .86))


def console(x, y, yaw_deg, body=None, top=None, band=None):
    body = body or M_CREAM
    top = top or M_CREAM
    band = band or M_RED
    yaw = math.radians(yaw_deg)
    c, s = math.cos(yaw), math.sin(yaw)

    def at(dx, dy):
        return x + dx * c - dy * s, y + dx * s + dy * c
    rot = (0, 0, yaw)
    box('con_body', (.42, .30, .065), (*at(0, 0), .036), body, bevel=.012, rot=rot)
    box('con_step', (.26, .16, .032), (*at(.03, .04), .083), top, bevel=.008, rot=rot)
    box('con_band', (.425, .305, .018), (*at(0, 0), .022), band, bevel=.004, rot=rot)
    box('con_btn1', (.03, .018, .01), (*at(-.15, -.10), .072), M_RED, bevel=.002, rot=rot)
    box('con_btn2', (.03, .018, .01), (*at(-.10, -.10), .072), M_CREAM, bevel=.002, rot=rot)
    box('con_port1', (.016, .004, .012), (*at(-.13, -.152), .04), M_BLACK, rot=rot)
    box('con_port2', (.016, .004, .012), (*at(-.09, -.152), .04), M_BLACK, rot=rot)
    box('con_slotlip', (.17, .03, .012), (*at(.04, .04), .102), M_BLACK, rot=rot)
    box('cart_in', (.145, .018, .105), (*at(.04, .04), .15), CARTS[1], bevel=.005, rot=rot)
    box('cart_in_l', (.11, .004, .066), (*at(.04, .03), .155), LABELS[0], rot=rot)
    for i in range(5):
        box(f'con_vent{i}', (.012, .10, .002), (*at(.09 + i * .022, -.09), .0695), M_BLACK, rot=rot)


def cart(i, x, y, z, yaw):
    r = (0, 0, math.radians(yaw))
    box(f'cart{i}', (.145, .105, .02), (x, y, z), random.choice(CARTS), bevel=.004, rot=r)
    box(f'cartl{i}', (.10, .068, .002), (x, y, z + .011), random.choice(LABELS), rot=r)


def pad(x, y, yaw_deg, cable_to, body=None):
    yaw = math.radians(yaw_deg)
    c, s = math.cos(yaw), math.sin(yaw)
    body = body or M_CREAM

    def at(dx, dy):
        return x + dx * c - dy * s, y + dx * s + dy * c
    r = (0, 0, yaw)
    box(f'pad{x}', (.15, .066, .018), (x, y, .012), body, bevel=.006, rot=r)
    box(f'pad_face{x}', (.14, .056, .002), (x, y, .022), M_DARKRED, rot=r)
    box(f'pad_d1{x}', (.03, .009, .004), (*at(-.038, -.002), .025), M_BLACK, rot=r)
    box(f'pad_d2{x}', (.009, .03, .004), (*at(-.038, -.002), .025), M_BLACK, rot=r)
    for d in (.03, .054):
        cyl(f'pad_b{x}{d}', .007, .005, (*at(d, -.004), .025), M_RED)
    box(f'pad_s1{x}', (.012, .004, .003), (*at(-.006, -.006), .025), M_BLACK, rot=r)
    box(f'pad_s2{x}', (.012, .004, .003), (*at(.012, -.006), .025), M_BLACK, rot=r)
    pts = [(*at(0, .036), .012)]
    sx, sy = pts[0][0], pts[0][1]
    for i in range(1, 15):
        t = i / 14
        pts.append((sx + (cable_to[0] - sx) * t + .06 * math.sin(i * 1.9), sy + (cable_to[1] - sy) * t + .05 * math.cos(i * 2.3), .007))
    pts.append((*cable_to, .03))
    curve(f'padcable{x}', pts, .0034, M_RUBBER)


def cables(x0, x1, y0, n=5):
    for k in range(n):
        pts = []
        a = random.uniform(x0, x0 + .3)
        for i in range(11):
            t = i / 10
            pts.append((a + (x1 - a) * t + .05 * math.sin(i * (1.5 + k * .4)),
                        y0 + .09 * math.sin(i * .8 + k) + t * .12, .004 + .004 * (i % 3)))
        curve(f'cable{k}', pts, .0032 if k % 2 else .0042, M_RUBBER if k != 2 else M_RED)


SODAS = {}


def can(name, x, y, brand='zap', z=0., turn=0., fallen=None):
    """Blasto, Gas, Pow or Zap. turn spins the label; fallen is the way the top points once it's on its side."""
    if brand not in SODAS:
        SODAS[brand] = uv_mat('soda' + brand, f'can_{brand}.png', rough=.24)
        SODAS[brand].node_tree.nodes['Principled BSDF'].inputs['Metallic'].default_value = .35
    o = lathe(name, [(.031, 0), (.033, .008), (.033, .108), (.027, .122), (.027, .124)], (x, y, z + .002), SODAS[brand])
    me = o.data
    uv = me.uv_layers.new(name='UV')
    for f in me.polygons:
        us = []
        for li in f.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            us.append((math.atan2(co.x, -co.y) / (2 * math.pi) + .75 + turn, co.z / .124))
        for li, (u, v) in zip(f.loop_indices, us):
            uv.data[li].uv = (u + 1 if max(q for q, _ in us) - u > .5 else u, v)
    t = cyl(name + 't', .018, .001, (x, y, z + .127), M_METAL)
    if fallen is not None:
        d = Vector((math.cos(fallen), math.sin(fallen), 0))
        M = Matrix.Translation((x, y, z + .0355)) @ d.to_track_quat('Z', 'Y').to_matrix().to_4x4() @ Matrix.Translation((0, 0, -.062))
        o.location = (0, 0, 0)
        t.location = (0, 0, .125)
        place(o, M)
        place(t, M)


def puddle(name, x, y, r, z=0., seed=0, stretch=(1, 1), color=0x3a1608):
    """Spilled soda: a thin wobbly pool that rounds off at its edge, and a few strays around it."""
    wet = mat(name, srgb(color), .035)
    wet.node_tree.nodes['Principled BSDF'].inputs['Specular IOR Level'].default_value = .8
    rnd = random.Random(seed)

    def pool(nm, cx, cy, rr, h):
        bm = bmesh.new()
        N, RINGS = 72, 7
        off = Vector((seed * 1.9, seed * .7, 0))
        rings = []
        for k in range(RINGS):
            f = 1 - (k / RINGS) ** 2.2
            row = []
            for i in range(N):
                a = i / N * 2 * math.pi
                w = 1 + noise.noise(Vector((math.cos(a) * 1.7, math.sin(a) * 1.7, 0)) + off) * .62
                row.append(bm.verts.new((cx + math.cos(a) * rr * w * stretch[0] * f, cy + math.sin(a) * rr * w * stretch[1] * f, h * math.sqrt(max(0, 1 - f * f)))))
            rings.append(row)
        for r0, r1 in zip(rings, rings[1:]):
            for i in range(N):
                bm.faces.new((r0[i], r0[(i + 1) % N], r1[(i + 1) % N], r1[i]))
        bm.faces.new(rings[-1])
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        me = bpy.data.meshes.new(nm)
        bm.to_mesh(me)
        bm.free()
        o = link(bpy.data.objects.new(nm, me))
        o.location = (0, 0, z)
        me.materials.append(wet)
        for f_ in me.polygons:
            f_.use_smooth = True
    pool(name, x, y, r, .0022)
    for k in range(6):
        a = rnd.uniform(0, 6.28)
        d = r * rnd.uniform(1.3, 1.9)
        pool(f'{name}{k}', x + math.cos(a) * d * stretch[0], y + math.sin(a) * d * stretch[1], rnd.uniform(.004, .011), .0016)


def mug(name, x, y, color, z=0.):
    m = mat(name, srgb(color), .25)
    lathe(name, [(.036, 0), (.04, .004), (.042, .09), (.038, .092), (.036, .006)], (x, y, z + .001), m)
    cyl(name + 'c', .036, .002, (x, y, z + .07), mat(name + 'c', srgb(0x2a1608), .08))
    pts = [(x + .04, y, z + .072), (x + .068, y, z + .068), (x + .07, y, z + .036), (x + .04, y, z + .024)]
    curve(name + 'h', pts, .0055, m)


def vhs_stack(x, y, n, z=0.):
    for i in range(n):
        o = box(f'vhs{x}{i}', (.19, .105, .027), (x + random.uniform(-.01, .01), y + random.uniform(-.008, .008), z + .016 + i * .029),
                random.choice((M_BLACK, M_PLASTIC2, M_BLACK)), bevel=.002, rot=(0, 0, math.radians(random.uniform(-9, 9))))
        box(f'vhsl{x}{i}', (.14, .002, .017), (o.location[0], o.location[1] - .053, o.location[2]), random.choice(LABELS[:5] + [M_WHITE]), rot=o.rotation_euler)


def magazines(x, y, n, z=0.):
    for i in range(n):
        box(f'mag{x}{i}', (.21, .28, .006), (x + random.uniform(-.02, .02), y + random.uniform(-.02, .02), z + .004 + i * .0062),
            random.choice(BOOKS + LABELS), rot=(0, 0, math.radians(random.uniform(-16, 16))))


def plant(name, x, y, z, height=.62, spread=.34, leaves=26, pot=None):
    pot = pot or mat(name + 'pot', srgb(0xa85a34), .7)
    lathe(name + 'p', [(.05, 0), (.075, .13), (.08, .135), (.08, .15), (.07, .15), (.066, .12), (.03, .12)], (x, y, z), pot)
    cyl(name + 'soil', .068, .004, (x, y, z + .135), mat(name + 'soil', srgb(0x1c120c), .95))
    greens = [noisy(f'{name}g{k}', srgb(c), srgb(d), scale=60, rough=.36) for k, (c, d) in enumerate(((0x1f5a2c, 0x2f7a3a), (0x2a6a30, 0x184a26), (0x3a7a34, 0x25602c)))]
    stem = mat(name + 'stem', srgb(0x35502a), .6)
    for i in range(leaves):
        a = random.uniform(0, 2 * math.pi)
        t = random.uniform(.25, 1)
        reach = spread * t * random.uniform(.6, 1)
        h = height * (t ** .6) * random.uniform(.7, 1)
        tip = Vector((x + math.cos(a) * reach, y + math.sin(a) * reach, z + .15 + h))
        base = Vector((x + random.uniform(-.02, .02), y + random.uniform(-.02, .02), z + .135))
        mid = base.lerp(tip, .55) + Vector((0, 0, h * .18))
        curve(f'{name}st{i}', [tuple(base), tuple(mid), tuple(tip)], .0026, stem)
        # a leaf: long oval, folded along its rib, drooping off the end of the stem
        L = random.uniform(.11, .2)
        Wd = L * random.uniform(.34, .46)
        bm = bmesh.new()
        rows = []
        for j in range(9):
            v = j / 8
            half = Wd * math.sin(v * math.pi) ** .75 + .0005
            droop = -v * v * L * .5
            rows.append([bm.verts.new((v * L, -half, droop - .15 * half)), bm.verts.new((v * L, 0, droop)), bm.verts.new((v * L, half, droop - .15 * half))])
        for j in range(8):
            for k in range(2):
                bm.faces.new((rows[j][k], rows[j][k + 1], rows[j + 1][k + 1], rows[j + 1][k]))
        me = bpy.data.meshes.new(f'{name}lf{i}')
        bm.to_mesh(me)
        bm.free()
        lf = link(bpy.data.objects.new(f'{name}lf{i}', me))
        lf.location = tip
        lf.rotation_euler = (random.uniform(-.25, .25), random.uniform(-.25, .3), a + random.uniform(-.3, .3))
        me.materials.append(random.choice(greens))
        for p in me.polygons:
            p.use_smooth = True


def floor_lamp(name, x, y, power, color, shade_color):
    cyl(name + 'b', .13, .025, (x, y, -.74), M_BRASS)
    cyl(name + 'p', .012, 1.72, (x, y, .12), M_BRASS, verts=16)
    shade = mat(name + 's', srgb(shade_color), .8, emit=srgb(shade_color), strength=3.2)
    glow(lathe(name + 'sh', [(.26, .0), (.15, .30)], (x, y, .84), shade))
    point(name + 'l', (x, y, .98), srgb(color), power, soft=.1, hidden=True)


def poster(name, file, w, h, loc, roll=0., frame=None):
    r = math.radians(roll)
    o = face(box(name, (w, .004, h), loc, face_mat(name, file), rot=(0, r, 0)), w, h)
    if frame:
        for k, (sx, sz, dx, dz) in enumerate(((w + .05, .028, 0, h / 2 + .012), (w + .05, .028, 0, -h / 2 - .012), (.028, h, -w / 2 - .012, 0), (.028, h, w / 2 + .012, 0))):
            box(f'{name}f{k}', (sx, .018, sz), (loc[0] + dx * math.cos(r) + dz * math.sin(r), loc[1] - .004, loc[2] - dx * math.sin(r) + dz * math.cos(r)), frame, rot=(0, r, 0))
    return o


def walls(w_mat, back=3.4, left=-3.3, right=3.5, ceil=1.65, floor_mat=None):
    box('wall', (9, .1, 5), (0, back, 1.0), w_mat)
    box('wallL', (.1, 8, 5), (left, 0, 1.0), w_mat)
    box('wallR', (.1, 8, 5), (right, 0, 1.0), w_mat)
    box('ceiling', (9, 8, .1), (0, 0, ceil + .05), M_WHITE)
    box('floor', (9, 8, .1), (0, 0, -.8), floor_mat or M_BLACK)


def cabinet(material):
    box('cabinet', (6.5, .72, .78), (0, .02, -.39), material, bevel=.006)
    box('cabtop', (6.5, .74, .03), (0, .02, -.012), material, bevel=.004)


def uv_mat(name, file, rough=.9, bump=0., repeat=1.):
    """An image on a mesh that has its own UVs, so it follows the cloth."""
    m = mat(name, (1, 1, 1), rough)
    t = m.node_tree
    b = t.nodes['Principled BSDF']
    uv = t.nodes.new('ShaderNodeUVMap')
    mp = t.nodes.new('ShaderNodeMapping')
    mp.inputs['Scale'].default_value = (repeat, repeat, repeat)
    tx = t.nodes.new('ShaderNodeTexImage')
    tx.image = bpy.data.images.load(TEX + file)
    t.links.new(uv.outputs['UV'], mp.inputs['Vector'])
    t.links.new(mp.outputs['Vector'], tx.inputs['Vector'])
    t.links.new(tx.outputs['Color'], b.inputs['Base Color'])
    if bump:
        bp = t.nodes.new('ShaderNodeBump')
        bp.inputs['Strength'].default_value = bump
        bp.inputs['Distance'].default_value = .01
        t.links.new(tx.outputs['Color'], bp.inputs['Height'])
        t.links.new(bp.outputs['Normal'], b.inputs['Normal'])
    return m


def place(o, M):
    """Move something built around the origin by a whole transform."""
    o.matrix_basis = M @ o.matrix_basis
    return o


def poly(name, pts, radius, material, cyclic=False, loc=(0, 0, 0), rot=(0, 0, 0), res=4):
    c = bpy.data.curves.new(name, 'CURVE')
    c.dimensions = '3D'
    c.bevel_depth = radius
    c.bevel_resolution = res
    sp = c.splines.new('POLY')
    sp.points.add(len(pts) - 1)
    for q, v in zip(sp.points, pts):
        q.co = (*v, 1)
    sp.use_cyclic_u = cyclic
    o = link(bpy.data.objects.new(name, c))
    o.location = loc
    o.rotation_euler = rot
    c.materials.append(material)
    return o


def chaikin(pts, n=3):
    """Round the corners of a bent tube, keeping its ends where they are."""
    for _ in range(n):
        out = [pts[0]]
        for a, b in zip(pts, pts[1:]):
            out.append(tuple(a[i] * .75 + b[i] * .25 for i in range(len(a))))
            out.append(tuple(a[i] * .25 + b[i] * .75 for i in range(len(a))))
        out.append(pts[-1])
        pts = out
    return pts


def cushion(name, w, d, h, loc, material, rot=(0, 0, 0), r=.035, crown=.016, welt=None, sag=0., seed=0, cuts=36):
    """A boxed cushion: rounded edges, a crown, puckers along the seams, piping on both seam lines."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=cuts, use_grid_fill=True)
    hw, hd, hh = w / 2, d / 2, h / 2
    off = Vector((seed * 3.17, seed * 1.73, seed * .61))
    for v in bm.verts:
        q = Vector((v.co.x * w, v.co.y * d, v.co.z * h))
        core = Vector((max(-hw + r, min(hw - r, q.x)), max(-hd + r, min(hd - r, q.y)), max(-hh + r, min(hh - r, q.z))))
        dv = q - core
        if dv.length > 1e-6:
            q = core + dv.normalized() * r
        ux, uy, uz = q.x / hw, q.y / hd, q.z / hh
        q.z += (1 if q.z > 0 else .35) * math.copysign(crown, q.z) * (1 - ux * ux) * (1 - uy * uy)
        q.y += math.copysign(crown * .6, q.y) * (1 - ux * ux) * (1 - uz * uz)
        q.x += math.copysign(crown * .5, q.x) * (1 - uy * uy) * (1 - uz * uz)
        if q.z > 0 and sag:
            q.z -= sag * math.exp(-(ux * ux + uy * uy) * 2.2)
        # lazy dents, then puckers that die away from the seams
        q += Vector((0, 0, 1)) * noise.noise(q * 5 + off) * .010
        edge = min(hw - abs(q.x), hd - abs(q.y))
        pk = math.exp(-max(edge, 0) / .05) * .0035
        q.z += math.sin(q.x * 110 + noise.noise(q * 9 + off) * 7) * pk * (1 if q.z > 0 else 0)
        q.y += math.sin(q.x * 90 + q.z * 40 + noise.noise(q * 8 + off) * 6) * .0016 * (abs(uy) > .96)
        v.co = q
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = link(bpy.data.objects.new(name, me))
    o.location = loc
    o.rotation_euler = rot
    me.materials.append(material)
    for f in me.polygons:
        f.use_smooth = True
    for side in (1, -1):
        z = side * (hh - r * .42)
        rr = r * .9
        ix, iy = hw - r + rr * .72, hd - r + rr * .72
        pts = []
        for cx, cy, a0 in ((ix - rr, iy - rr, 0), (-ix + rr, iy - rr, 90), (-ix + rr, -iy + rr, 180), (ix - rr, -iy + rr, 270)):
            for k in range(7):
                a = math.radians(a0 + k * 15)
                pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a), z))
        poly(name + f'w{side}', pts, .0062, welt or material, cyclic=True, loc=loc, rot=rot, res=2)
    return o


def pillow(name, w, h, t, loc, material, rot=(0, 0, 0), seed=0):
    """A knife-edge throw pillow: full in the middle, pinched at the seam, with four dog ears."""
    bm = bmesh.new()
    N = 34
    off = Vector((seed * 2.3, seed * 1.1, 0))
    for side in (1, -1):
        g = []
        for j in range(N + 1):
            row = []
            for i in range(N + 1):
                u, v = i / N * 2 - 1, j / N * 2 - 1
                x = u * w / 2 * (1 - .085 * (1 - v * v))
                z = v * h / 2 * (1 - .085 * (1 - u * u))
                f = (max(0, 1 - u ** 4) ** .6) * (max(0, 1 - v ** 4) ** .6)
                y = side * t / 2 * f
                y += f * noise.noise(Vector((x, z, side)) * 6 + off) * .016
                row.append(bm.verts.new((x, y, z)))
            g.append(row)
        for j in range(N):
            for i in range(N):
                bm.faces.new((g[j][i], g[j][i + 1], g[j + 1][i + 1], g[j + 1][i]))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=.0008)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = link(bpy.data.objects.new(name, me))
    o.location = loc
    o.rotation_euler = rot
    me.materials.append(material)
    for f in me.polygons:
        f.use_smooth = True
    return o


def couch(prefix, cx, cy, W, D, seats, fabric, seat_top=-.13, back_top=.46, arm_top=.13, welt=None, arm=.22):
    """Built the way a couch is built: frame, rolled arms, seat cushions on a deck, back cushions on those."""
    deck = seat_top - .2
    th = .2
    y_back, y_front = cy + D / 2, cy - D / 2
    box(prefix + 'deck', (W - .02, D, deck + .8), (cx, cy, (deck - .8) / 2), fabric, bevel=.02)
    cushion(prefix + 'backframe', W - .02, th, back_top - deck, (cx, y_back - th / 2, (back_top + deck) / 2), fabric, r=.07, crown=.012, seed=9, welt=welt)
    for side in (-1, 1):
        ax = cx + side * (W / 2 - arm / 2)
        rr = arm * .62
        cushion(f'{prefix}arm{side}', arm * .82, D, arm_top - rr * .6 + .8, (ax, cy, (arm_top - rr * .6 - .8) / 2), fabric, r=.03, crown=.008, seed=7 + side)
        roll = lathe(f'{prefix}roll{side}', [(.001, -D / 2 - .012), (rr * .72, -D / 2 - .012), (rr * .95, -D / 2 + .004), (rr, -D / 2 + .03), (rr, D / 2 - .03), (rr * .9, D / 2), (.001, D / 2)], (ax, cy, arm_top - rr), fabric)
        roll.rotation_euler = (-math.pi / 2, 0, 0)
        ring = [(ax + rr * .86 * math.cos(a * math.pi / 20), y_front - .0135, arm_top - rr + rr * .86 * math.sin(a * math.pi / 20)) for a in range(40)]
        poly(f'{prefix}rollw{side}', ring, .0062, welt or fabric, cyclic=True, res=2)
    inner = W - 2 * arm
    cw = inner / seats
    xs = [cx - inner / 2 + cw * (k + .5) for k in range(seats)]
    tilt = math.radians(12)
    front_of_back = y_back - th
    bh = back_top - seat_top + .0
    bth = .19
    out = []
    for k, x in enumerate(xs):
        c = cushion(f'{prefix}seat{k}', cw + .004, D - th + .025, .2, (x, y_front - .012 + (D - th + .025) / 2, seat_top - .1), fabric, welt=welt, sag=random.uniform(.006, .02), seed=k + 1)
        y = front_of_back - bth / 2 - math.sin(tilt) * bh / 2 + .014
        b = cushion(f'{prefix}back{k}', cw + .002, bth, bh, (x, y, seat_top - .012 + math.cos(tilt) * bh / 2), fabric, rot=(-tilt, 0, 0), r=.045, crown=.02, welt=welt, sag=.0, seed=k + 11)
        out += [c, b]
    return {'xs': xs, 'seat': seat_top, 'front': y_front, 'back_face': front_of_back - bth - .02, 'colliders': out}


def throw(name, w, h, nx, ny, M, material, colliders, frames=70, min_dist=.007):
    """A blanket, dropped: real cloth simulation onto the couch, frozen where it lands."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new('UV')
    g = [[bm.verts.new(((i / nx - .5) * w, (j / ny - .5) * h, 0)) for i in range(nx + 1)] for j in range(ny + 1)]
    for j in range(ny):
        for i in range(nx):
            f = bm.faces.new((g[j][i], g[j][i + 1], g[j + 1][i + 1], g[j + 1][i]))
            for l, (a, b) in zip(f.loops, ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1))):
                l[uv].uv = (a / nx * w, b / ny * w)
    bm.to_mesh(me)
    bm.free()
    o = link(bpy.data.objects.new(name, me))
    o.matrix_basis = M
    me.materials.append(material)
    for f in me.polygons:
        f.use_smooth = True
    for c in colliders:
        m = c.modifiers.new('collide', 'COLLISION')
        c.collision.thickness_outer = .012
        c.collision.cloth_friction = 12
    cl = o.modifiers.new('cloth', 'CLOTH')
    cl.settings.quality = 7
    cl.settings.mass = .25
    cl.settings.tension_stiffness = 12
    cl.settings.compression_stiffness = 12
    cl.settings.bending_stiffness = 2.5
    cl.settings.air_damping = 3
    cl.collision_settings.distance_min = min_dist
    cl.collision_settings.collision_quality = 4
    cl.point_cache.frame_start = 1
    cl.point_cache.frame_end = frames
    scene.frame_start = 1
    scene.frame_end = frames
    for f in range(1, frames + 1):
        scene.frame_set(f)
    dg = bpy.context.evaluated_depsgraph_get()
    baked = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
    world = o.matrix_world.copy()
    o.modifiers.clear()
    o.data = baked
    o.matrix_basis = world
    for c in colliders:
        c.modifiers.clear()
    for f in baked.polygons:
        f.use_smooth = True
    sd = o.modifiers.new('thick', 'SOLIDIFY')
    sd.thickness = .008
    sb = o.modifiers.new('soft', 'SUBSURF')
    sb.levels = sb.render_levels = 1
    scene.frame_set(1)
    return o


def photo_frame(name, file, w, h, x, y, yaw, wood, z0=.0035, lean=9.):
    """A standing picture frame: sits on its bottom edge, leans back on a strut."""
    t = math.radians(lean)
    M = Matrix.Translation((x, y, z0)) @ Matrix.Rotation(math.radians(yaw), 4, 'Z') @ Matrix.Rotation(-t, 4, 'X')
    fw, m = .018, .012
    W_, H_ = w + 2 * (fw + m), h + 2 * (fw + m)
    bars = (((W_, .016, fw), (0, 0, fw / 2)), ((W_, .016, fw), (0, 0, H_ - fw / 2)), ((fw, .016, H_), (-W_ / 2 + fw / 2, 0, H_ / 2)), ((fw, .016, H_), (W_ / 2 - fw / 2, 0, H_ / 2)))
    for k, (sz, lc) in enumerate(bars):
        place(box(f'{name}b{k}', sz, lc, wood, bevel=.002, segs=2), M)
    place(box(name + 'mat', (W_ - fw, .004, H_ - fw), (0, .004, H_ / 2), M_PAPER), M)
    place(box(name + 'back', (W_ - .004, .006, H_ - .004), (0, .01, H_ / 2), wood), M)
    pic = face(box(name + 'pic', (w, .002, h), (0, 0, 0), face_mat(name, file, rough=.2)), w, h)
    pic.location = (0, .0005, H_ / 2)
    place(pic, M)
    # the strut behind it, reaching down to the table
    sl = H_ * .62
    st = box(name + 'strut', (.03, .004, sl), (0, 0, 0), wood)
    sa = t * 2.6
    st.rotation_euler = (sa, 0, 0)
    ztop = sl * math.cos(sa)
    st.location = (0, ztop * math.tan(t) + .02 + math.sin(sa) * sl / 2, ztop / 2)
    place(st, Matrix.Translation((x, y, z0)) @ Matrix.Rotation(math.radians(yaw), 4, 'Z'))


def tack_poster(name, file, w, h, loc, roll=0., tack=None):
    """A poster on the wall with four thumbtacks in it."""
    o = poster(name, file, w, h, loc, roll)
    tack = tack or M_RED
    r = math.radians(roll)
    for k, (dx, dz) in enumerate(((-1, 1), (1, 1), (-1, -1), (1, -1))):
        lx, lz = dx * (w / 2 - .012), dz * (h / 2 - .012)
        tx, tz = lx * math.cos(r) + lz * math.sin(r), -lx * math.sin(r) + lz * math.cos(r)
        cyl(f'{name}t{k}', .0065, .006, (loc[0] + tx, loc[1] - .004, loc[2] + tz), tack, rot=(math.pi / 2, 0, 0), verts=14)
    return o


# single-stroke tube lettering, each letter a list of bent tubes in a 1-high box
LETTERS = {
    'H': (.62, [[(0, 1), (0, 0)], [(0, .52), (.62, .52)], [(.62, 1), (.62, 0)]]),
    'E': (.54, [[(.54, 1), (0, 1), (0, 0), (.54, 0)], [(0, .52), (.44, .52)]]),
    'Y': (.66, [[(0, 1), (.33, .48), (.66, 1)], [(.33, .48), (.33, 0)]]),
    'G': (.66, [[(.62, .82), (.5, 1), (.14, 1), (0, .82), (0, .18), (.14, 0), (.5, 0), (.64, .16), (.64, .46), (.34, .46)]]),
    'A': (.7, [[(0, 0), (.35, 1), (.7, 0)], [(.12, .34), (.58, .34)]]),
    'M': (.82, [[(0, 0), (0, 1), (.41, .3), (.82, 1), (.82, 0)]]),
    'R': (.62, [[(0, 0), (0, 1), (.44, 1), (.62, .84), (.62, .64), (.44, .48), (0, .48)], [(.3, .48), (.64, 0)]]),
}


def neon_word(prefix, word, x, z, size, y, material, gap=.3, radius=.0062):
    """Glass tube on standoffs, the blacked-out jumps between letters and all. Returns (left, right)."""
    total = sum(LETTERS[ch][0] for ch in word) + gap * (len(word) - 1)
    pen = x - total * size / 2
    left = pen
    last = None
    for i, ch in enumerate(word):
        w, strokes = LETTERS[ch]
        for j, st in enumerate(strokes):
            pts = chaikin([(pen + a * size, y, z + b * size) for a, b in st], 3)
            glow(poly(f'{prefix}{i}_{j}', pts, radius, material, res=3))
            for k in (0, -1):
                cyl(f'{prefix}{i}_{j}so{k}', .0034, .03, (pts[k][0], y + .015, pts[k][2]), M_PLASTIC, rot=(math.pi / 2, 0, 0), verts=8)
        if last:
            poly(f'{prefix}j{i}', [last, (pen, y + .006, z + size * .02)], .0028, M_RUBBER, res=2)
        last = (pen + w * size, y + .006, z + size * .02)
        pen += (w + gap) * size
    return left, pen - gap * size


def pizza(prefix, M):
    """An open delivery box, the pie cut in eight and one slice already gone."""
    R = .172
    kraft = tex_mat(prefix + 'kraft', 'kraft.png', 2.4, rough=.82, bump=.15)
    place(box(prefix + 'tray', (.40, .40, .005), (0, 0, .0025), kraft), M)
    for k, (sz, lc) in enumerate((((.40, .004, .03), (0, -.198, .015)), ((.40, .004, .045), (0, .198, .0225)), ((.004, .40, .03), (-.198, 0, .015)), ((.004, .40, .03), (.198, 0, .015)))):
        place(box(f'{prefix}wall{k}', sz, lc, kraft), M)
    # the lid, thrown back on its hinge: plain inside, its rim standing up toward you. The print is on the far side
    H = M @ Matrix.Translation((0, .2, .045)) @ Matrix.Rotation(math.radians(105), 4, 'X')
    place(box(prefix + 'lid', (.408, .404, .004), (0, .202, 0), kraft), H)
    place(box(prefix + 'lidf', (.408, .004, .034), (0, .402, .017), kraft), H)
    place(box(prefix + 'lids0', (.004, .404, .034), (-.202, .202, .017), kraft), H)
    place(box(prefix + 'lids1', (.004, .404, .034), (.202, .202, .017), kraft), H)
    place(box(prefix + 'lidh', (.408, .004, .01), (0, .002, .005), kraft), H)
    M = M @ Matrix.Translation((0, 0, .013))
    cheese = noisy(prefix + 'cheese', srgb(0xf3c75a), srgb(0xc98226), scale=70, rough=.3, bump=.25)
    cheese.node_tree.nodes['Principled BSDF'].inputs['Subsurface Weight'].default_value = .2
    crust = noisy(prefix + 'crust', srgb(0xd29a50), srgb(0x9c5f28), scale=46, rough=.62, bump=.5)
    pep = noisy(prefix + 'pep', srgb(0x9c2416), srgb(0x6c140c), scale=120, rough=.28, bump=.2)
    N = 8
    missing = 1
    rnd = random.Random(8)
    for k in range(N):
        if k == missing:
            continue
        a0 = k * 2 * math.pi / N + .012
        a1 = (k + 1) * 2 * math.pi / N - .012
        bm = bmesh.new()
        rings = [0, .05, .1, .2, .35, .5, .65, .78, .86, .9, .94, .975, 1]
        g = []
        for i, f in enumerate(rings):
            r = f * R
            row = []
            for j in range(11):
                a = a0 + (a1 - a0) * j / 10
                x, y = r * math.cos(a), r * math.sin(a)
                z = .0165 + noise.noise(Vector((x * 26, y * 26, k * .0))) * .0035
                if f > .84:
                    z = .016 + .024 * max(0, math.sin((f - .84) / .16 * math.pi)) ** .7 + noise.noise(Vector((x * 40, y * 40, 3))) * .002
                row.append(bm.verts.new((x, y, z)))
            g.append(row)
        base = [[bm.verts.new((v.co.x, v.co.y, .006)) for v in row] for row in g]
        for i in range(len(rings) - 1):
            for j in range(10):
                f = bm.faces.new((g[i][j], g[i + 1][j], g[i + 1][j + 1], g[i][j + 1]))
                f.material_index = 1 if rings[i] >= .84 else 0
        for i in range(len(rings) - 1):
            bm.faces.new((base[i][0], base[i + 1][0], g[i + 1][0], g[i][0])).material_index = 1
            bm.faces.new((base[i][10], g[i][10], g[i + 1][10], base[i + 1][10])).material_index = 1
        for j in range(10):
            bm.faces.new((base[-1][j], base[-1][j + 1], g[-1][j + 1], g[-1][j])).material_index = 1
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        me = bpy.data.meshes.new(f'{prefix}s{k}')
        bm.to_mesh(me)
        bm.free()
        o = link(bpy.data.objects.new(f'{prefix}s{k}', me))
        me.materials.append(cheese)
        me.materials.append(crust)
        for f in me.polygons:
            f.use_smooth = True
        place(o, M)
        for q in range(2 if k % 2 else 3):
            ra = rnd.uniform(.3, .76) * R
            aa = rnd.uniform(a0 + .12, a1 - .12)
            pr = rnd.uniform(.022, .027)
            pe = lathe(f'{prefix}p{k}{q}', [(.001, 0), (pr, 0), (pr * 1.02, .003), (pr * .8, .0072), (.001, .009)], (ra * math.cos(aa), ra * math.sin(aa), .018), pep, verts=20)
            place(pe, M)
    # a dropped pepperoni where the slice was
    a = (missing + .5) * 2 * math.pi / N
    place(lathe(prefix + 'pd', [(.001, 0), (.021, 0), (.021, .002), (.016, .004), (.001, .0045)], (R * .5 * math.cos(a), R * .5 * math.sin(a), .006), pep, verts=20), M)
    return [M @ Vector((.01, .02, .03))]


# ---- the TV: a big black tube set, turned a little toward the room -------------------------------
TV_X, TV_Y = .56, .02
TV_YAW = math.radians(-13)
TV_W, TV_H, TV_D = .92, .70, .62
tv_parts = []


def tv_box(name, size, loc, material, bevel=0., segs=4):
    o = box(name, size, (TV_X + loc[0], TV_Y + loc[1], loc[2]), material, bevel=bevel, segs=segs)
    tv_parts.append((o, loc))
    return o


tv_box('tv_body', (TV_W, TV_D, TV_H), (0, .04, TV_H / 2 + .022), M_PLASTIC, bevel=.035, segs=6)
tv_box('tv_base', (TV_W * .8, TV_D * .8, .03), (0, .05, .012), M_PLASTIC2, bevel=.008)
tv_box('tv_back', (TV_W * .74, TV_D * .55, TV_H * .78), (0, .48, TV_H * .44), M_PLASTIC, bevel=.05)
FRONT = -.27
SCR_W, SCR_H = .70, .525
SCR_CX, SCR_CZ = -.075, TV_H / 2 + .055
tv_box('tv_bezel_t', (SCR_W + .1, .04, .05), (SCR_CX, FRONT, SCR_CZ + SCR_H / 2 + .024), M_PLASTIC2, bevel=.012)
tv_box('tv_bezel_b', (SCR_W + .1, .04, .05), (SCR_CX, FRONT, SCR_CZ - SCR_H / 2 - .024), M_PLASTIC2, bevel=.012)
tv_box('tv_bezel_l', (.05, .04, SCR_H + .05), (SCR_CX - SCR_W / 2 - .024, FRONT, SCR_CZ), M_PLASTIC2, bevel=.012)
tv_box('tv_bezel_r', (.05, .04, SCR_H + .05), (SCR_CX + SCR_W / 2 + .024, FRONT, SCR_CZ), M_PLASTIC2, bevel=.012)
CX = SCR_CX + SCR_W / 2 + .105
for i in range(9):
    tv_box(f'tv_grill{i}', (.1, .012, .006), (CX, FRONT - .002, TV_H - .08 - i * .017), M_BLACK)
for i, z in enumerate((.335, .205)):
    o = cyl(f'tv_knob{i}', .033, .03, (0, 0, 0), M_PLASTIC2, rot=(math.pi / 2, 0, 0))
    o2 = box(f'tv_knobmark{i}', (.005, .006, .026), (0, 0, 0), M_CREAM)
    tv_parts += [(o, (CX, FRONT - .03, z)), (o2, (CX, FRONT - .048, z + .012))]
tv_box('tv_power', (.03, .012, .018), (CX, FRONT - .012, .105), M_RED, bevel=.002)
led = mat('led', (0, 0, 0), .4, emit=srgb(0x46ff96), strength=14)
glow(tv_box('tv_led', (.009, .006, .009), (CX + .035, FRONT - .012, .105), led))
tv_box('tv_earbase', (.13, .08, .022), (SCR_CX + .1, .08, TV_H + .034), M_PLASTIC2, bevel=.006)
for name, tip in (('l', (-.34, .05, .62)), ('r', (.27, .14, .52))):
    o = curve('ear' + name, [(0, 0, 0), (tip[0] * .5, tip[1] * .5, tip[2] * .5), tip], .0035, M_METAL)
    tv_parts.append((o, (SCR_CX + .1, .08, TV_H + .042)))

M_GLASS = mat('glass', srgb(0x0b0c10), .12)
M_GLOW = mat('glow', (0, 0, 0), .2, emit=(1, 1, 1), strength=11)
bm = bmesh.new()
NX, NZ = 40, 30
grid = []
for j in range(NZ + 1):
    row = []
    for i in range(NX + 1):
        u, v = i / NX * 2 - 1, j / NZ * 2 - 1
        row.append(bm.verts.new((u * SCR_W / 2, -(1 - .5 * (u * u + v * v)) * .018, v * SCR_H / 2)))
    grid.append(row)
for j in range(NZ):
    for i in range(NX):
        bm.faces.new((grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]))
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
screen_mesh = bpy.data.meshes.new('screen')
bm.to_mesh(screen_mesh)
bm.free()
for p in screen_mesh.polygons:
    p.use_smooth = True
screen_mesh.materials.append(M_GLASS)
screen = link(bpy.data.objects.new('screen', screen_mesh))
tv_parts.append((screen, (SCR_CX, FRONT - .004, SCR_CZ)))

pivot = Vector((TV_X, TV_Y, 0))
c, s = math.cos(TV_YAW), math.sin(TV_YAW)
for o, loc in tv_parts:
    x, y = loc[0], loc[1]
    o.location = (pivot.x + x * c - y * s, pivot.y + x * s + y * c, loc[2])
    o.rotation_euler = (o.rotation_euler[0], o.rotation_euler[1], TV_YAW)


LAMP_LOW, LAMP_TOP = .066, .031


def wrap_uv(o):
    """Cylindrical UVs for something spun around Z, so a picture goes around it."""
    me = o.data
    uv = me.uv_layers.new(name='UV')
    for f in me.polygons:
        us = []
        for li in f.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            us.append((math.atan2(co.x, -co.y) / (2 * math.pi) + .5, co.z * 1.55))
        for li, (u, v) in zip(f.loop_indices, us):
            uv.data[li].uv = (u + 1 if max(q for q, _ in us) - u > .5 else u, v)


def lava_lamp(x, y):
    """The real shape: hourglass base and cone cap in the loud print, a tapered bottle of purple between them."""
    print_ = uv_mat('lamp_print', 'lamp_memphis.png', rough=.3)
    wrap_uv(lathe('lamp_base', [(.001, 0), (.084, 0), (.085, .006), (.066, .05), (.044, .1), (.043, .112), (.056, .15), (.074, .186), (.072, .192), (.001, .192)], (x, y, .002), print_))
    wrap_uv(lathe('lamp_cap', [(.03, .52), (.0305, .525), (.0185, .615), (.001, .618)], (x, y, .002), print_))
    g = mat('lampglass', srgb(0x5a12c8), .03, emit=srgb(0x5208c8), strength=.62)
    g.node_tree.nodes['Principled BSDF'].inputs['Transmission Weight'].default_value = .6
    g.node_tree.nodes['Principled BSDF'].inputs['IOR'].default_value = 1.33
    glow(lathe('lamp_glass', [(LAMP_LOW, .19), (.06, .26), (LAMP_TOP, .52)], (x, y, .002), g))
    point('lampglow', (x, y - .02, .3), srgb(0xa030ff), 4, hidden=True)
    return x, y


# ---- camera (the same in every room, so the TV lands where the layout expects it) ----------------
cam_data = bpy.data.cameras.new('cam')
cam_data.lens = 34
cam_data.shift_x = .155
cam_data.shift_y = -.092
cam_data.dof.use_dof = True
cam_data.dof.aperture_fstop = 3.2
cam_data.dof.focus_distance = 2.95
cam = link(bpy.data.objects.new('cam', cam_data))
cam.location = (-.62, -2.75, .46)
aim = Vector((-.62, .4, .365))
cam.rotation_euler = (aim - Vector(cam.location)).to_track_quat('-Z', 'Y').to_euler()
scene.camera = cam

extras = {}


# ================================================================================================
# NEON: a kid's bedroom at night. Streetlight through blinds, lava lamp, posters, the bed behind.
# ================================================================================================
def neon():
    wall = noisy('wall', srgb(0x4a2a7a), srgb(0x3a1e66), scale=90, rough=.82, bump=.03)
    walls(wall, back=2.5, left=-3.6, right=3.2, ceil=3.1)
    cabinet(noisy('cab', srgb(0x1c0f10), srgb(0x2e1a12), scale=14, rough=.42, stretch=(.12, 1, 1)))
    console(-.92, -.02, -12)
    pad(-.62, -.16, 24, (-.78, -.14))
    cart(0, -1.5, -.12, .012, 21)
    cart(1, -1.44, .06, .012, -32)
    cart(2, -1.48, .03, .036, -18)
    cart(3, -.42, -.22, .012, 38)
    cables(-1.1, TV_X - .2, .08)
    vhs_stack(-1.26, .22, 4)
    can('can1', -.47, .03, 'pow', turn=.13)
    can('can2', -.54, .11, 'zap', turn=-.19)
    magazines(-1.72, .14, 5)
    extras['lamp'] = lava_lamp(-.24, .08)
    # the room behind: a bed along the wall, desk, shelf of junk, posters everywhere
    box('bedframe', (2.1, 1.0, .22), (-1.5, 1.9, -.62), M_PLASTIC2, bevel=.02)
    sheets = tex_mat('sheets', 'sheets.png', 1.4, rough=.85, bump=.2)
    sheet('blanket', 2.1, 1.05, 60, 30, lambda u, v: (0, .07 * math.sin(u * 17 + v * 5) * math.sin(v * 3.14) + .05 * math.sin(u * 7 - v * 9), .045 * math.sin(u * 13 + v * 8)),
          (-1.5, 1.42, -.27), sheets, rot=(math.radians(84), 0, 0))
    puffy('pillow1', (.5, .16, .32), (-.72, 2.2, -.22), M_WHITE, rot=(math.radians(-18), 0, 0), lump=.02)
    puffy('pillow2', (.5, .16, .32), (-.2, 2.28, -.2), noisy('pl', srgb(0x8a4ac8), srgb(0x6a3aa8), scale=30, rough=.8), rot=(math.radians(-14), 0, math.radians(8)), lump=.02)
    for k, z in enumerate((.72, 1.12)):
        box(f'wshelf{k}', (1.5, .22, .02), (-1.55, 2.36, z), M_METAL)
        books(f'wb{k}', -2.25, -1.25 + k * .2, 2.34, z + .012, depth=.16, lo=.14, hi=.26)
    for i, (x, h, col) in enumerate(((-.95, .2, 0xd84a3c), (-.82, .14, 0x4a78d8))):
        box(f'trophy{i}', (.06, .06, h), (x, 2.34, .73 + h / 2), mat(f't{i}', srgb(col), .3), bevel=.006)
    poster('p_a', 'poster_memphis.png', .78, 1.08, (-2.42, 2.44, .72), 2.4)
    poster('p_b', 'poster_ferret.png', .6, .825, (-.4, 2.44, .86), -2.6)
    poster('p_c', 'poster_sunset.png', .86, 1.2, (1.72, 2.44, .9), 1.8)
    poster('p_d', 'poster_read.png', .576, .88, (2.76, 2.44, .86), -1.4)
    poster('p_e', 'poster_believe.png', .6, .818, (.36, 2.44, .86), 3.2)
    box('desk', (1.5, .6, .04), (2.5, 2.1, -.02), noisy('desk', srgb(0x2a1a2a), srgb(0x3a2430), scale=20, rough=.4))
    box('deskleg', (1.46, .56, .7), (2.5, 2.12, -.4), M_PLASTIC2)
    ball('globe', .13, (2.2, 2.1, .2), noisy('globe', srgb(0x1e4a8a), srgb(0x2a7a4a), scale=9, rough=.25))
    books('deskb', 2.5, 3.0, 2.2, 0, depth=.16)
    # streetlight through venetian blinds
    wo = spot('window', (-3.0, -2.3, 2.5), (-.1, 1.8, .8), srgb(0xff1ec8), 6400)
    d = (Vector((-.1, 1.8, .8)) - Vector(wo.location)).normalized()
    sx = d.cross(Vector((0, 0, 1))).normalized()
    sy = sx.cross(d).normalized()
    tilt = math.radians(9)
    sx, sy = sx * math.cos(tilt) + sy * math.sin(tilt), sy * math.cos(tilt) - sx * math.sin(tilt)
    for i in range(-22, 23):
        o = box(f'slat{i}', (3.0, .003, .021), Vector(wo.location) + d * .7 + sy * (i * .036), M_BLACK)
        o.rotation_euler = Matrix((sx, d, sy)).transposed().to_euler()
        o.visible_camera = False
    area('fill', (-2.2, -1.4, 1.2), 3.0, srgb(0x5a24ff), 30, (-.5, 1.6, .3))
    area('ceil', (0, .4, 1.7), 3.5, srgb(0x6a2cff), 16, (0, .6, 0))
    area('kick', (2.8, -.3, 1.1), 1.0, srgb(0x22d6ff), 16, (.8, 0, .4))
    area('rim', (.5, 1.0, 1.4), .9, srgb(0xff2ec8), 20, (.6, .1, .6))
    area('backlit', (-.8, 1.2, -.2), 1.8, srgb(0x3a60ff), 7, (-1.3, 2.4, .2))


# ================================================================================================
# BASEMENT: walnut sheet paneling, drop ceiling, plaid couch, neon, Christmas lights.
# ================================================================================================
def basement():
    BACK = 2.62
    WALL = BACK - .05
    panel = tex_mat('panel', 'paneling.png', 1 / 2.4, rough=.34, bump=.7, height='paneling_h.png')
    walls(panel, back=BACK, left=-3.4, right=3.6, ceil=1.42, floor_mat=noisy('carpet', srgb(0x3a2a1a), srgb(0x5a4228), scale=240, rough=1, bump=.8))
    wood = noisy('frame', srgb(0x20140a), srgb(0x2e1c0e), scale=30, rough=.5)
    box('crown', (9, .03, .055), (0, WALL - .015, 1.365), wood)
    # acoustic drop ceiling, grid and tiles, one fluorescent troffer
    tile = noisy('tile', srgb(0xbdb6a6), srgb(0xa8a092), scale=200, rough=.95, bump=.5)
    for i in range(14):
        for j in range(9):
            box(f'tile{i}_{j}', (.595, .595, .012), (-3.6 + i * .61, -2.2 + j * .61, 1.40), tile)
    for i in range(15):
        box(f'gridx{i}', (.018, 7, .022), (-3.9 + i * .61, .8, 1.39), M_WHITE)
    for j in range(10):
        box(f'gridy{j}', (9, .018, .022), (0, -2.5 + j * .61, 1.39), M_WHITE)
    tube = mat('tube', srgb(0xfff0d0), .3, emit=srgb(0xffeac0), strength=3)
    glow(box('troffer', (1.2, .6, .01), (-1.2, 1.5, 1.385), tube))
    area('troffer_l', (-1.2, 1.5, 1.36), 1.2, srgb(0xffe2b0), 30, (-1.2, 1.5, 0), size_y=.6)
    cabinet(noisy('cab', srgb(0x3a2212), srgb(0x5a3a1e), scale=11, rough=.34, bump=.1, stretch=(.1, 1, 1)))
    console(-1.0, -.03, -10, body=M_GRAY, top=M_GRAY, band=M_PLASTIC2)
    pad(-.7, -.17, 18, (-.86, -.16), body=M_GRAY)
    cart(0, -1.56, -.1, .012, 15)
    cart(1, -1.5, .1, .012, -26)
    cables(-1.15, TV_X - .2, .1, n=4)
    vhs_stack(-1.3, .2, 5)
    can('can1', -.33, .03, 'blasto', turn=.17)
    can('can2', -.4, -.05, 'gas', turn=-.06)
    can('can4', -.13, .17, 'pow', turn=-.2)
    # the Zap didn't make it
    can('can3', -.2, -.1, 'zap', turn=.31, fallen=math.radians(-28))
    puddle('spill', -.075, -.19, .05, z=.0032, seed=4, stretch=(1.45, .85))
    magazines(-1.76, -.04, 3, z=.004)
    # the couch, plaid since before you were born
    plaid = tex_mat('plaid', 'plaid.png', 2.2, rough=.92, bump=.35)
    weltm = mat('plaidwelt', srgb(0x4a2c18), .8)
    cc = couch('c_', -1.36, WALL - .03 - .46, 2.5, .92, 3, plaid, welt=weltm)
    afghan = uv_mat('afghan', 'afghan.png', rough=.97, bump=.5, repeat=2.2)
    throw('afghan', 1.05, 1.2, 44, 50, Matrix.Translation((-1.6, WALL - .36, .62)) @ Matrix.Rotation(math.radians(8), 4, 'Z'), afghan, cc['colliders'])
    pil = mat('pil', srgb(0x8a5a2c), .95)
    pillow('c_pil1', .42, .42, .17, (cc['xs'][0] + .02, cc['back_face'] - .06, cc['seat'] + .2), pil, rot=(math.radians(-20), math.radians(5), math.radians(7)), seed=1)
    # dinner, sunk into the cushion a little at the front, turned the way you'd drop it
    # the back of the box rests in the corner where the arm meets the back cushion
    px = cc['xs'][2] + .03
    py = cc['front'] + .17
    M = Matrix.Translation((px, py, cc['seat'] + .017)) @ Matrix.Rotation(math.radians(-45), 4, 'Z')
    extras['steam'] = pizza('pz_', M)
    # the sign: real bent tube, on standoffs, cord running up into the ceiling
    SX = .3
    red = mat('neonred', srgb(0xff3a2a), .3, emit=srgb(0xff2414), strength=30)
    cyan = mat('neoncyan', srgb(0x5af0ff), .3, emit=srgb(0x30e0ff), strength=26)
    neon_word('nh', 'HEY', SX - .12, 1.13, .135, WALL - .035, cyan)
    neon_word('ng', 'GAMER', SX, .925, .165, WALL - .035, red)
    point('sign_r', (SX, WALL - .2, 1.04), srgb(0xff3020), 2.0, soft=.2)
    point('sign_c', (SX - .12, WALL - .22, 1.2), srgb(0x30d8ff), 1.6, soft=.15)
    curve('signcord', [(SX + .4, WALL - .012, 1.0), (SX + .44, WALL - .012, 1.12), (SX + .42, WALL - .012, 1.24), (SX + .46, WALL - .012, 1.36)], .0028, M_RUBBER)
    # the motivational wall
    tack_poster('p_hang', 'poster_hang.png', .52, .71, (-.74, WALL - .004, .9), -3.4)
    poster('p_b', 'poster_read.png', .48, .733, (-1.86, WALL - .01, .85), 1.7, frame=wood)
    spot('posterlight', (-1.3, WALL - 1.2, 1.32), (-1.3, WALL, .86), srgb(0xfff0d8), 11, angle=62, soft=.1)
    box('switch', (.07, .006, .115), (.86, WALL - .002, .28), M_CREAM, bevel=.002, segs=2)
    box('switcht', (.012, .012, .024), (.86, WALL - .007, .28), M_WHITE, bevel=.002, segs=2)
    cyl('dart', .21, .03, (1.06, WALL - .02, .82), tex_mat('dart', 'dart.png', 2.3, rough=.8), rot=(math.pi / 2, 0, 0))
    box('shelfb', (1.0, .2, .025), (-2.65, WALL - .1, .22), wood)
    books('shelfbk', -3.12, -2.3, WALL - .1, .235, depth=.15, lo=.13, hi=.22)
    # Christmas lights stapled along the top of the paneling, left up since 1991
    pts = []
    n = 34
    for i in range(n):
        t = i / (n - 1)
        pts.append((-3.1 + t * 6.0, WALL - .022, 1.34 - abs(math.sin(t * math.pi * 6)) * .055))
    curve('xmaswire', pts, .003, M_RUBBER)
    cols = (0xff4a3c, 0xffc23c, 0x3cff7a, 0x3c9cff)
    bulbs = []
    for i, p in enumerate(pts):
        col = srgb(cols[i % 4])
        at = (p[0], p[1] - .012, p[2] - .018)
        glow(ball(f'bulb{i}', .016, at, mat(f'bulb{i}', col, .3, emit=col, strength=9), segs=12))
        bulbs.append(at)
    extras['bulbs'] = bulbs
    box('endtable', (.5, .5, .55), (-2.85, WALL - .3, -.46), wood, bevel=.005)
    floor_lamp('lamp', -2.82, WALL - .3, 38, 0xffb060, 0xf0c080)
    area('warmfill', (-.5, -.6, 1.3), 4.5, srgb(0xffb878), 22, (-.5, 2, .2))
    area('keytop', (-1.4, -.8, 1.3), 1.0, srgb(0xffc890), 12, (-1.0, -.05, 0))
    area('couchkey', (-.4, .9, 1.25), 1.1, srgb(0xffd8a8), 9, (-.5, 1.9, -.1))
    area('kick', (2.8, -.4, 1.0), .8, srgb(0x60a0ff), 6, (.8, 0, .4))


# ================================================================================================
# RAIN: a front room on a gray Sunday. A real street past the glass, sofa and blanket, lamp on.
# ================================================================================================
outside = []
pane = None


def street():
    """What's past the window, built to scale: houses across the street, bare trees, a lit lamp post."""
    SKY = srgb(0xc4ccd4)

    def far(hexv, dist):
        k = 1 - math.exp(-dist / 130)
        c = srgb(hexv)
        return tuple(c[i] + (SKY[i] - c[i]) * k for i in range(3))

    def out(o):
        outside.append(o)
        return o
    sky = bpy.data.materials.new('sky')
    sky.use_nodes = True
    t = sky.node_tree
    em = t.nodes['Principled BSDF']
    em.inputs['Base Color'].default_value = (0, 0, 0, 1)
    tc = t.nodes.new('ShaderNodeTexCoord')
    n = t.nodes.new('ShaderNodeTexNoise')
    n.inputs['Scale'].default_value = .018
    n.inputs['Detail'].default_value = 7
    rp = t.nodes.new('ShaderNodeValToRGB')
    rp.color_ramp.elements[0].position = .32
    rp.color_ramp.elements[0].color = (.52, .56, .61, 1)
    rp.color_ramp.elements[1].position = .72
    rp.color_ramp.elements[1].color = (.86, .89, .92, 1)
    t.links.new(tc.outputs['Object'], n.inputs['Vector'])
    t.links.new(n.outputs['Fac'], rp.inputs['Fac'])
    t.links.new(rp.outputs['Color'], em.inputs['Emission Color'])
    em.inputs['Emission Strength'].default_value = 1
    out(box('sky', (900, .1, 300), (0, 320, 60), sky))
    out(box('ground', (900, 400, .1), (0, 150, -1.1), mat('gnd', far(0x3a3f3c, 80), .7)))
    for i, (hx, hw, hh, wall_c, roof_c) in enumerate(((-30, 12, 4.2, 0x8f8574, 0x3a3836), (-15.5, 11, 5.8, 0x9fa6a8, 0x34363a), (-3, 10, 4.4, 0xb0a48c, 0x403a36), (9, 12, 6.0, 0x7d8a8c, 0x2e3236), (23, 11, 4.4, 0xa89a90, 0x3a3836))):
        y = 108 + (i % 2) * 4
        d = y
        out(box(f'h{i}', (hw, 8, hh + 1), (hx, y + 4, hh / 2 - .6), mat(f'hw{i}', far(wall_c, d), .85)))
        bm = bmesh.new()
        a = bm.verts.new((-hw / 2 - .5, -4.5, 0))
        b = bm.verts.new((hw / 2 + .5, -4.5, 0))
        c_ = bm.verts.new((hw / 2 + .5, 4.5, 0))
        d_ = bm.verts.new((-hw / 2 - .5, 4.5, 0))
        e = bm.verts.new((-hw / 2 - .5, 0, 2.7))
        f = bm.verts.new((hw / 2 + .5, 0, 2.7))
        for v in ((a, b, f, e), (c_, d_, e, f), (a, e, d_), (b, c_, f)):
            bm.faces.new(v)
        me = bpy.data.meshes.new(f'rf{i}')
        bm.to_mesh(me)
        bm.free()
        ro = out(link(bpy.data.objects.new(f'rf{i}', me)))
        ro.location = (hx, y + 4, hh - .1)
        me.materials.append(mat(f'rm{i}', far(roof_c, d), .6))
        for k, wx in enumerate((-.34, -.1, .14, .36)):
            for fl in range(1 if hh < 5 else 2):
                lit = (i * 3 + k * 5 + fl) % 3 == 0
                wm = mat(f'w{i}{k}{fl}', far(0x30343a, d), .12, emit=srgb(0xffb868) if lit else None, strength=3.4 if lit else 0)
                out(box(f'win{i}{k}{fl}', (1.2, .06, 1.35), (hx + wx * hw, y - .02, .9 + fl * 2.5), wm))
                out(box(f'wt{i}{k}{fl}', (1.34, .05, .1), (hx + wx * hw, y - .03, 1.62 + fl * 2.5), mat(f'wt{i}{k}{fl}', far(0xd8d4cc, d), .6)))

    def tree(prefix, x, y, height, seed):
        r = random.Random(seed)
        c = bpy.data.curves.new(prefix, 'CURVE')
        c.dimensions = '3D'
        c.bevel_depth = 1
        c.bevel_resolution = 2
        c.resolution_u = 2

        def grow(p, dirn, L, rad, depth):
            sp = c.splines.new('POLY')
            pts = [Vector(p)]
            d = Vector(dirn)
            for _ in range(4):
                d = (d + Vector((r.uniform(-.28, .28), r.uniform(-.28, .28), r.uniform(-.12, .22)))).normalized()
                pts.append(pts[-1] + d * L / 4)
            sp.points.add(len(pts) - 1)
            for k, q in enumerate(pts):
                sp.points[k].co = (*q, 1)
                sp.points[k].radius = rad * (1 - .32 * k / 4)
            if depth > 0:
                for _ in range(r.choice((2, 3, 3))):
                    nd = (d + Vector((r.uniform(-.9, .9), r.uniform(-.9, .9), r.uniform(-.25, .7)))).normalized()
                    grow(pts[-1], nd, L * r.uniform(.6, .78), rad * .62, depth - 1)
        grow((x, y, -1.1), (0, 0, 1), height * .36, height * .011, 7)
        o = out(link(bpy.data.objects.new(prefix, c)))
        c.materials.append(mat(prefix, far(0x1a1816, y), .8))
        return o
    tree('t1', -13, 48, 13, 3)
    tree('t2', 2, 55, 15, 8)
    tree('t3', -24, 62, 15, 12)
    tree('t4', 10, 50, 12.5, 21)
    tree('t5', -6, 74, 16, 34)
    # the street lamp's already on at three in the afternoon
    out(cyl('pole', .07, 6.2, (-3.4, 38, 2.0), mat('pole', far(0x24262a, 38), .4), verts=12))
    out(box('arm', (1.3, .08, .08), (-4.0, 38, 5.05), mat('arm', far(0x24262a, 38), .4)))
    out(ball('lampglow', .24, (-4.55, 38, 4.92), mat('lamp', (0, 0, 0), .4, emit=srgb(0xffd090), strength=34), segs=16))


def rain():
    global pane
    plaster = noisy('plaster', srgb(0x9a9c90), srgb(0x8a8d84), scale=120, rough=.9, bump=.06)
    walls(plaster, back=3.4, left=-3.6, right=3.6, ceil=1.72, floor_mat=noisy('oak', srgb(0x6a4a2a), srgb(0x8a6236), scale=20, rough=.3, stretch=(.1, 1, 1)))
    cabinet(noisy('cab', srgb(0x7a5228), srgb(0x9a6e3a), scale=9, rough=.36, bump=.08, stretch=(.08, 1, 1)))
    console(-1.05, -.04, -8, body=M_GRAY, top=M_WHITE, band=M_PLASTIC2)
    pad(-.74, -.2, 14, (-.9, -.18), body=M_GRAY)
    cart(0, -1.6, -.12, .012, 11)
    cables(-1.2, TV_X - .2, .12, n=3)
    mug('mug', -.47, -.03, 0xd8d0c0)
    extras['steam'] = [(-.47, -.03, .092)]
    extras['steam_size'] = .58
    box('remote', (.05, .17, .018), (-.26, -.2, .011), M_PLASTIC, bevel=.003, rot=(0, 0, math.radians(-18)))
    for i in range(12):
        cyl(f'rb{i}', .004, .002, (-.26 + (i % 3 - 1) * .012 + (i // 3 - 1.5) * .004, -.2 + (i // 3 - 1.5) * .022, .021), LABELS[i % 5], verts=8)
    for i, (w, d, col, r) in enumerate(((.42, .28, 0xa83a2a, 4), (.4, .26, 0x2a5a8a, -6), (.36, .24, 0xd8b03c, 9))):
        box(f'game{i}', (w, d, .055), (-1.62, .2, .03 + i * .057), mat(f'gm{i}', srgb(col), .5), bevel=.003, rot=(0, 0, math.radians(r)))
    plant('sp', -1.92, -.1, 0.002, height=.28, spread=.18, leaves=16)
    plant('sp2', -.33, .23, 0.002, height=.34, spread=.2, leaves=18, pot=mat('wp', srgb(0xd0ccc0), .45))
    frame = noisy('frame', srgb(0x3a2412), srgb(0x4a3018), scale=30, rough=.45)
    photo_frame('ph_kid', 'photo_kid.png', .22, .165, -.68, .2, 13, frame)
    photo_frame('ph_cat', 'photo_cat.png', .15, .19, -.015, .07, -19, frame, lean=11)
    # the window. Glass and what's past it get their own passes: the rain runs on that glass at runtime
    WX, WZ, WW, WH = -.75, .42, 2.7, 1.5
    bpy.data.objects.remove(bpy.data.objects['wall'])
    wy = 3.4
    box('wallT', (9, .1, 2), (0, wy, WZ + WH / 2 + 1), plaster)
    box('wallB', (9, .1, 1.2), (0, wy, WZ - WH / 2 - .6), plaster)
    box('wallLeft', (3, .1, WH), (WX - WW / 2 - 1.5, wy, WZ), plaster)
    box('wallRight', (4, .1, WH), (WX + WW / 2 + 2, wy, WZ), plaster)
    white = mat('trim', srgb(0xd4d0c6), .4)
    for dx in (-WW / 2, -WW / 6, WW / 6, WW / 2):
        box(f'mull{dx}', (.05, .1, WH + .05), (WX + dx, wy, WZ), white)
    for dz in (-WH / 2, WH / 6, WH / 2):
        box(f'trans{dz}', (WW + .05, .1, .05), (WX, wy, WZ + dz), white)
    box('sill', (WW + .3, .22, .04), (WX, wy - .1, WZ - WH / 2 - .03), white, bevel=.006)
    pane = box('pane', (WW, .004, WH), (WX, wy, WZ), mat('pane', (0, 0, 0), .4, emit=(1, 1, 1), strength=1))
    street()
    cur = noisy('curtain', srgb(0x9a8a68), srgb(0x8a7c60), scale=70, rough=.9, bump=.12)
    for side, x in ((-1, WX - WW / 2 + .1), (1, WX + WW / 2 - .1)):
        sheet(f'curtain{side}', .62, 2.5, 60, 30, lambda u, v: (.0, .04 * math.sin(u * 44) + .012 * math.sin(u * 11 + v * 3), .0),
              (x, wy - .16, .3), cur)
    box('rod', (WW + 1.1, .02, .02), (WX, wy - .16, 1.56), M_BRASS)
    sofa = noisy('sofa', srgb(0x5e7a80), srgb(0x4e6a70), scale=180, rough=.95, bump=.5)
    welt = mat('sofawelt', srgb(0x3c5258), .85)
    cc = couch('s_', -.72, 2.78, 2.7, .95, 3, sofa, welt=welt)
    knit = uv_mat('knit', 'cableknit.png', rough=.96, bump=.7, repeat=1.8)
    throw('blanket', 1.0, 1.25, 44, 54, Matrix.Translation((cc['xs'][2] + .02, 2.72, .66)) @ Matrix.Rotation(math.radians(-14), 4, 'Z'), knit, cc['colliders'])
    pils = (mat('pl1', srgb(0xc8843a), .95), mat('pl2', srgb(0xcfc8b4), .95), mat('pl3', srgb(0x9a4a2c), .95))
    sz, bf, st = .46, cc['back_face'], cc['seat']
    for k, (xx, lean, yaw, rl, m_) in enumerate(((cc['xs'][0] - .2, -16, 9, 5, pils[0]), (cc['xs'][0] + .36, -25, -8, -4, pils[1]), (cc['xs'][1] + .44, -21, -13, 5, pils[2]))):
        t_ = math.radians(-lean)
        pillow(f's_pil{k}', sz, sz, .17, (xx, bf - .05 - k * .012, st + .012 + math.cos(t_) * sz / 2), m_, rot=(math.radians(lean), math.radians(rl), math.radians(yaw)), seed=k + 3)
    walnut = noisy('walnut', srgb(0x3a2412), srgb(0x54341a), scale=18, rough=.34, bump=.06, stretch=(.1, 1, 1))
    box('coffee', (1.1, .55, .035), (-.85, 1.72, -.32), walnut, bevel=.004)
    for dx in (-.5, .5):
        for dy in (-.22, .22):
            box(f'cl{dx}{dy}', (.03, .03, .4), (-.85 + dx, 1.72 + dy, -.53), walnut)
    magazines(-1.1, 1.68, 4, z=-.3)
    mug('mug2', -.55, 1.76, 0x3a5a7a, z=-.3)
    sheet('openbook', .34, .24, 20, 10, lambda u, v: (0, .018 * math.sin(u * 6.28), 0), (-.78, 1.6, -.295), M_PAPER, rot=(math.pi / 2, 0, math.radians(10)))
    box('side', (.5, .5, .55), (-2.6, 2.6, -.47), walnut, bevel=.004)
    floor_lamp('lamp', -2.72, 2.72, 60, 0xffb878, 0xf4d8a8)
    bookcase('bk', 2.2, 3.18, 1.6, 2.3, walnut, shelves=6)
    plant('big', 1.05, 2.7, -.74, height=1.25, spread=.62, leaves=46, pot=mat('wp2', srgb(0x585048), .6))
    poster('p_a', 'poster_read.png', .49, .75, (-3.15, 3.33, .55), 0, frame=frame)
    dl = area('daylight', (WX, 3.12, WZ), 2.7, srgb(0xb8cce0), 110, (WX, 0, -.2), size_y=1.5)
    dl.visible_camera = False
    area('skybounce', (0, -.6, 1.6), 5, srgb(0xc8d4e0), 40, (-.2, 1.4, 0))
    area('front', (-.8, -1.8, .8), 3, srgb(0xc0ccd8), 20, (-.8, 0, .1))
    area('sofafill', (-.6, 1.2, 1.3), 2, srgb(0xffe0c0), 16, (-.7, 2.6, 0))


# ================================================================================================
# GRID: 1982, from a terminal at the edge of it. Mostly black. Fine lines of light, a long way to the horizon, one tower.
# ================================================================================================
def grid():
    Z = -.6
    CELL = 2.3
    LINE, ICE, BLUE, AMBER, RED = srgb(0x74e4dc), srgb(0xd8f6ff), srgb(0x1a8cff), srgb(0xffb020), srgb(0xff2a18)
    GX = lambda i: i * CELL + .4
    GY = lambda i: 2.2 + i * CELL

    def faded(name, color, power, reach, floor=.0):
        """Light that thins out with distance, as if there's air between you and it."""
        m = mat(name, (0, 0, 0), .9, emit=color, strength=power)
        nt = m.node_tree
        pos = nt.nodes.new('ShaderNodeNewGeometry')
        xyz = nt.nodes.new('ShaderNodeSeparateXYZ')
        by = nt.nodes.new('ShaderNodeMath')
        by.operation = 'DIVIDE'
        by.inputs[1].default_value = -reach
        ex = nt.nodes.new('ShaderNodeMath')
        ex.operation = 'EXPONENT'
        amt = nt.nodes.new('ShaderNodeMath')
        amt.operation = 'MULTIPLY'
        amt.inputs[1].default_value = power
        add = nt.nodes.new('ShaderNodeMath')
        add.inputs[1].default_value = floor
        nt.links.new(pos.outputs['Position'], xyz.inputs[0])
        nt.links.new(xyz.outputs['Y'], by.inputs[0])
        nt.links.new(by.outputs[0], ex.inputs[0])
        nt.links.new(ex.outputs[0], amt.inputs[0])
        nt.links.new(amt.outputs[0], add.inputs[0])
        nt.links.new(add.outputs[0], nt.nodes['Principled BSDF'].inputs['Emission Strength'])
        return m

    def outline(name, pts, material, r=.03, cyclic=False):
        return glow(poly(name, pts, r, material, cyclic=cyclic, res=2))

    # the plain, with fine lines that fade into the distance
    box('plain', (400, 180, .1), (0, 90, Z - .05), mat('plain', srgb(0x060310), .95))
    M_LINE = faded('line', LINE, 3.6, 34., floor=.12)
    for i in range(-50, 51):
        glow(box(f'gx{i}', (.022, 150, .003), (GX(i), GY(0) + 75, Z + .002), M_LINE))
    for i in range(0, 66):
        glow(box(f'gy{i}', (400, .022, .003), (0, GY(i), Z + .002), M_LINE))

    # the sky: deep navy overhead, going to pale blue right down at the horizon
    sky = mat('sky', (0, 0, 0), .9, emit=(1, 1, 1), strength=1)
    nt = sky.node_tree
    pos = nt.nodes.new('ShaderNodeNewGeometry')
    xyz = nt.nodes.new('ShaderNodeSeparateXYZ')
    rise = nt.nodes.new('ShaderNodeMapRange')
    rise.inputs['From Min'].default_value = Z
    rise.inputs['From Max'].default_value = Z + 60
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    cr = ramp.color_ramp
    cr.elements[0].position = 0
    cr.elements[0].color = (*srgb(0xb4d2f4), 1)
    cr.elements[1].position = 1
    cr.elements[1].color = (*srgb(0x081530), 1)
    e = cr.elements.new(.065)
    e.color = (*srgb(0x7ea8de), 1)
    e = cr.elements.new(.18)
    e.color = (*srgb(0x2a4a86), 1)
    e = cr.elements.new(.42)
    e.color = (*srgb(0x10224a), 1)
    nt.links.new(pos.outputs['Position'], xyz.inputs[0])
    nt.links.new(xyz.outputs['Z'], rise.inputs['Value'])
    nt.links.new(rise.outputs[0], ramp.inputs['Fac'])
    nt.links.new(ramp.outputs['Color'], nt.nodes['Principled BSDF'].inputs['Emission Color'])
    glow(box('sky', (700, .1, 200), (0, 172, 60), sky))

    # a far low range: black shapes with a single wire along the tops, no colour of their own
    M_RIDGE = mat('ridge', (0, 0, 0), .9, emit=LINE, strength=2.6)
    M_DARK = mat('rangeblack', srgb(0x010206), .95)
    verts, faces, ridge = [], [], []
    x = -220.
    while x < 220:
        h = random.uniform(.15, 1.) ** 1.5 * 4.4
        verts += [(x, 165, Z), (x, 165, Z + h)]
        ridge.append((x, 164.8, Z + h))
        x += random.uniform(4, 16)
    for i in range(0, len(verts) - 2, 2):
        faces.append((i, i + 2, i + 3, i + 1))
    me = bpy.data.meshes.new('range')
    me.from_pydata(verts, [], faces)
    me.update()
    rg = link(bpy.data.objects.new('range', me))
    rg.data.materials.append(M_DARK)
    outline('rangeline', ridge, M_RIDGE, .09)
    glow(box('horizon', (420, .1, .06), (0, 164.6, Z + .03), mat('hz', (0, 0, 0), .9, emit=LINE, strength=4)))

    # the one tower, a long way off: a black cone ringed in red light, its beam going straight up out of the picture
    TX, TY = 3.3, 128.
    TOP = 21.
    for i, (r, z) in enumerate(((6.2, 0), (4.9, 4.6), (3.6, 9.2), (2.3, 13.8), (1.05, 18.4))):
        pts = [(TX + r * math.cos(a * math.tau / 40), TY + r * math.sin(a * math.tau / 40), Z + z) for a in range(40)]
        outline(f'towerring{i}', pts, mat(f'tr{i}', (0, 0, 0), .9, emit=RED, strength=7), .05, cyclic=True)
    lathe('tower', [(6.2, 0), (.2, TOP)], (TX, TY, Z), mat('towerblack', srgb(0x060104), .9), verts=40)
    glow(cyl('beam', .09, 300, (TX, TY, Z + TOP + 150), mat('beam', (0, 0, 0), .9, emit=ICE, strength=16), verts=10))
    glow(cyl('beamhalo', .34, 300, (TX, TY, Z + TOP + 150), mat('beamh', (0, 0, 0), .9, emit=RED, strength=1.1), verts=12))

    # a long way out to either side, two thin monoliths, drawn only by their edges
    M_EDGE = faded('edge', LINE, 7., 80.)
    for k, (x, y, w, d, h) in enumerate(((-58., 96., 3.8, 3.8, 15.), (-46., 118., 2.6, 2.6, 20.), (58., 88., 3.2, 3.2, 12.))):
        box(f'slab{k}', (w, d, h), (x, y, Z + h / 2), mat(f'slabb{k}', srgb(0x020308), .9))
        fx, fy = x - w / 2, y - d / 2
        outline(f'sl{k}f', [(fx, fy, Z), (fx + w, fy, Z), (fx + w, fy, Z + h), (fx, fy, Z + h)], M_EDGE, .035, cyclic=True)
        side = fx + w if x < 0 else fx
        outline(f'sl{k}s', [(side, fy, Z + h), (side, fy + d, Z + h), (side, fy + d, Z)], M_EDGE, .03)

    # the plan, in grid cells. Light walls and riders stay on the lines and never cross
    WALLS = (
        ('tc', [(-3, 2), (-3, 12), (-6, 12)], BLUE),
        ('te', [(2, 3), (2, 15), (5, 15)], AMBER),
    )
    RIDERS = (
        (0xff74e4dc, .3, [(-22, 22), (-8, 22), (-8, 34), (7, 34), (7, 22), (22, 22)]),
        (0xffffb020, .36, [(2, 44), (2, 26), (-13, 26), (-13, 40)]),
    )

    def legs(path):
        return list(zip(path, path[1:]))

    def touches(a0, a1, b0, b1):
        return max(min(a0[0], a1[0]), min(b0[0], b1[0])) <= min(max(a0[0], a1[0]), max(b0[0], b1[0])) and \
            max(min(a0[1], a1[1]), min(b0[1], b1[1])) <= min(max(a0[1], a1[1]), max(b0[1], b1[1]))

    PASS_ROWS = (18, 20)
    for _, wall, _ in WALLS:
        for r in RIDERS:
            for p0, p1 in legs(r[2]):
                for q0, q1 in legs(wall):
                    assert not touches(p0, p1, q0, q1), f'rider {r[0]:x} crosses a wall at {p0}-{p1}'
        for row in PASS_ROWS:
            for q0, q1 in legs(wall):
                assert not touches((-99, row), (99, row), q0, q1), f'a passer on row {row} crosses a wall at {q0}-{q1}'

    def trail(name, path, color, height):
        m = faded(name, color, 1.9, 60.)
        top = faded(name + 't', ICE, 9., 80.)
        for i, ((x0, y0), (x1, y1)) in enumerate(legs([(GX(x), GY(y)) for x, y in path])):
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            w, d = abs(x1 - x0) + .03, abs(y1 - y0) + .03
            glow(box(f'{name}{i}', (w, d, height), (cx, cy, Z + height / 2), m))
            glow(box(f'{name}t{i}', (w, d, .018), (cx, cy, Z + height), top))

    for name, path, color in WALLS:
        trail(name, path, color, .22)

    extras['runners'] = [{'c': c, 's': s, 'p': [(GX(x), GY(y)) for x, y in path]} for c, s, path in RIDERS]
    extras['runner_step'] = CELL / 2
    extras['passers'] = [
        {'sprite': 'cycle_blue', 'x': (GX(22), GX(-22)), 'y': GY(PASS_ROWS[0]), 'z': Z, 'h': 1.3, 'step': .06, 'every': 47., 'at': 6., 'wall': 0xff1a8cff},
        {'sprite': 'cycle_yellow', 'x': (GX(-22), GX(22)), 'y': GY(PASS_ROWS[1]), 'z': Z, 'h': 1.3, 'step': .07, 'every': 71., 'at': 30., 'wall': 0xffffb020},
        {'sprite': 'recognizer', 'x': (66., -66.), 'y': 74., 'z': Z + .2, 'h': 9.2, 'step': .5, 'every': 120., 'at': 60.},
    ]
    extras['runner_z'] = Z + .02

    # the desk: the terminal's, matte black, its own circuit let into the top
    cabinet(mat('cabmatte', srgb(0x05060c), .62))
    M_THREAD = mat('thread', (0, 0, 0), .9, emit=LINE, strength=3)
    glow(box('edgeline', (6.5, .004, .007), (0, -.341, -.017), M_THREAD))
    for i, (x0, y0, x1, y1) in enumerate(((-3.2, .3, -1.72, .3), (-1.72, .3, -1.72, .34), (-1.72, .34, .06, .34), (1.3, -.26, 3.2, -.26), (1.3, -.26, 1.3, .2), (-3.2, -.2, -2.08, -.2), (-2.08, -.2, -2.08, .02))):
        glow(box(f'trace{i}', (abs(x1 - x0) + .005, abs(y1 - y0) + .005, .001), ((x0 + x1) / 2, (y0 + y1) / 2, .0009), M_THREAD))

    body = mat('conblack', srgb(0x0c0d14), .55)
    console(-1.2, .0, -10, body=body, top=body, band=mat('conband', (0, 0, 0), .9, emit=BLUE, strength=2.4))
    glow(bpy.data.objects['con_band'])
    cart(0, -1.82, -.08, .012, 18)
    cart(1, -1.76, .1, .012, -24)
    cables(-1.3, TV_X - .2, .14, n=3)
    magazines(-2.06, .12, 3)

    # a classic terminal keyboard, wedge-shaped and heavy, its legends lit
    KX, KY, KYAW = -.32, -.07, math.radians(5)
    kc, ks = math.cos(KYAW), math.sin(KYAW)
    KW, KD = .62, .21
    shell = mat('kbshell', srgb(0xa89e88), .58)
    tilt = math.radians(7)

    def kb(dx, dy, dz):
        y2, z2 = dy * math.cos(tilt) - dz * math.sin(tilt), dy * math.sin(tilt) + dz * math.cos(tilt)
        return (KX + dx * kc - y2 * ks, KY + dx * ks + y2 * kc, .024 + z2)
    krot = (tilt, 0, KYAW)
    box('kb_body', (KW, KD, .03), kb(0, 0, 0), shell, bevel=.006, rot=krot)
    box('kb_well', (KW - .05, KD - .05, .006), kb(0, -.006, .014), M_BLACK, rot=krot)
    M_CAP = mat('kbcap', srgb(0xcfc7b2), .5)
    M_CAP2 = mat('kbcap2', srgb(0x7c766a), .5)
    M_LEGEND = mat('kbleg', srgb(0x181612), .6)
    K = .036
    rows = ((-.235, 14, 1.), (-.245, 14, 1.), (-.232, 13, 1.), (-.242, 13, 1.))
    for r, (x0, n, w) in enumerate(rows):
        y = .058 - r * K
        for i in range(n):
            x = x0 + i * K
            edge = i == 0 or i == n - 1
            box(f'kc{r}{i}', (K * .86, K * .86, .012), kb(x, y, .022), M_CAP2 if edge else M_CAP, bevel=.002, rot=krot)
            box(f'kl{r}{i}', (.009, .004, .0006), kb(x - .004, y + .004, .0285), M_LEGEND, rot=krot)
    box('kc_space', (.25, K * .86, .012), kb(-.01, .058 - 4 * K, .022), M_CAP, bevel=.002, rot=krot)
    curve('kbcord', [(KX + .05, KY + .1, .01), (KX + .03, KY + .17, .006), (KX - .2, KY + .19, .006), (-.95, .12, .006)], .0038, M_RUBBER)

    area('key', (-.7, -.9, 1.3), 3, srgb(0x9cc4ff), 9, (-.5, -.05, 0))
    area('coldleft', (-2.6, .9, .8), 1.2, BLUE, 12, (-.9, 0, .1))
    rimmed = area('rim', (.5, 1.25, 1.0), .9, LINE, 6, (.5, .1, .4))
    rimmed.visible_camera = False
    cam_data.dof.use_dof = False


# ================================================================================================
# MALL: the back of an arcade on a Saturday night. The set is on the prize counter, the cabinets go back and back.
# ================================================================================================
def mall():
    BACK, FLOOR, TOP = 9.2, -.8, 2.45
    wall = noisy('mallwall', srgb(0x120a24), srgb(0x1c0f33), scale=70, rough=.8, bump=.04)
    box('backwall', (30, .1, 6), (0, BACK, 1.), wall)
    box('mwallL', (.1, 14, 6), (-7.4, 3, 1.), wall)
    box('mwallR', (.1, 14, 6), (6.6, 3, 1.), wall)
    box('mallfloor', (30, 16, .1), (0, 3, FLOOR - .05), tex_mat('carpet', 'carpet.png', .42, rough=.95, emit=.55))
    box('mallceil', (30, 16, .1), (0, 3, TOP + .05), mat('mallceil', srgb(0x08070e), .9))
    for i in range(24):
        box(f'tilex{i}', (.02, 16, .02), (-7 + i * .61, 3, TOP - .01), mat(f'tx{i}', srgb(0x17151f), .7))
    for j in range(16):
        box(f'tiley{j}', (30, .02, .02), (0, -2 + j * .61, TOP - .01), M_PLASTIC2)

    def cab(i, x, y, yaw_deg, game, body=None, dark=False):
        """An upright, its front toward the aisle. game picks a marquee and a screen."""
        yaw = math.radians(yaw_deg)
        c, s = math.cos(yaw), math.sin(yaw)

        def at(dx, dy):
            return x + dx * c - dy * s, y + dx * s + dy * c
        n = f'c{i}'
        side = body or mat(n + 'side', srgb(random.choice((0x14111c, 0x1a1020, 0x101820, 0x201410, 0x0d0d12))), .42)
        rot = (0, 0, yaw)
        box(n + 'low', (.66, .62, .9), (*at(0, .06), FLOOR + .45), side, bevel=.006, rot=rot)
        box(n + 'mid', (.66, .46, .62), (*at(0, .14), FLOOR + 1.21), side, bevel=.006, rot=rot)
        box(n + 'hood', (.68, .6, .24), (*at(0, .07), FLOOR + 1.67), side, bevel=.008, rot=rot)
        # coin door, with its two little red slots
        box(n + 'door', (.3, .012, .36), (*at(0, -.255), FLOOR + .42), M_PLASTIC2, rot=rot)
        for k, dx in enumerate((-.06, .06)):
            glow(box(f'{n}coin{k}', (.022, .006, .045), (*at(dx, -.264), FLOOR + .5), mat(f'{n}cl{k}', (0, 0, 0), .4, emit=srgb(0xff2a18), strength=9), rot=rot))
        # the panel, stick and buttons
        tilt = math.radians(-18)
        box(n + 'panel', (.66, .3, .04), (*at(0, -.2), FLOOR + .98), M_PLASTIC2, bevel=.006, rot=(tilt, 0, yaw))
        cyl(n + 'stick', .0055, .06, (*at(-.17, -.2), FLOOR + 1.03), M_METAL)
        ball(n + 'knob', .015, (*at(-.17, -.2), FLOOR + 1.065), random.choice((M_RED, LABELS[0], LABELS[3])), segs=12)
        for k in range(3):
            cyl(f'{n}b{k}', .016, .012, (*at(.05 + k * .07, -.2 - k * .004), FLOOR + 1.0), random.choice((M_RED, LABELS[1], LABELS[0])))
        # the tube, tipped back in its bezel
        back = math.radians(13)
        box(n + 'bezel', (.56, .03, .47), (*at(0, -.095), FLOOR + 1.27), M_BLACK, rot=(back, 0, yaw))
        if dark:
            box(n + 'scr', (.46, .02, .36), (*at(0, -.112), FLOOR + 1.27), M_GLASS, rot=(back, 0, yaw))
            tape = box(n + 'ooo', (.32, .004, .08), (*at(0, -.13), FLOOR + 1.29), face_mat(n + 'ooom', 'mall_ooo.png', .7), rot=(back, 0, yaw + math.radians(4)))
            face(tape, .32, .08)
        else:
            glow(face(box(n + 'scr', (.46, .02, .36), (*at(0, -.112), FLOOR + 1.27), face_mat(n + 'scrm', f'scr{game}.png', .2, emit=2.4), rot=(back, 0, yaw)), .46, .36))
            hue = random.choice((0x4a7cff, 0xff4ab8, 0x48ffc0, 0xffb040, 0x8a5cff))
            point(n + 'wash', (*at(0, -.55), FLOOR + 1.2), srgb(hue), 1.0, soft=.1, hidden=True)
        # marquee, lit from behind
        glow(face(box(n + 'mq', (.64, .02, .17), (*at(0, -.235), FLOOR + 1.67), face_mat(n + 'mqm', f'mq{game}.png', .3, emit=3.2), rot=rot), .64, .17))

    # two ragged rows and the wall: no two cabinets quite square to each other
    row = (
        (-2.62, 3.5, 3, 7), (-1.9, 3.46, -2, 2, True), (-1.18, 3.52, 2, 0), (-.46, 3.46, -3, 8),
        (-4.9, 5.9, 8, 4), (-4.18, 6.0, 1, 7), (-3.46, 5.94, -2, 9), (-1.2, 5.96, 3, 6), (-.48, 6.02, -1, 5), (.24, 5.94, 2, 1), (.96, 6.0, -4, 3),
        (3.1, 5.9, -6, 5), (3.82, 5.96, 2, 8),
        (-4.2, 8.6, 0, 1), (-3.4, 8.62, 0, 7), (-2.6, 8.58, 0, 3), (-1.8, 8.6, 0, 9), (3.0, 8.6, 0, 2), (3.8, 8.62, 0, 6), (4.6, 8.58, 0, 4),
    )
    for i, r in enumerate(row):
        cab(i, r[0], r[1], r[2], r[3], dark=len(r) > 4)

    # the crane game nobody has ever won
    cx, cy = .08, 1.8
    box('cr_base', (.86, .86, .78), (cx, cy, FLOOR + .39), mat('crbase', srgb(0xb0123c), .35), bevel=.01)
    box('cr_top', (.86, .86, .18), (cx, cy, FLOOR + 1.72), mat('crtop', srgb(0xb0123c), .35), bevel=.01)
    for dx in (-.42, .42):
        for dy in (-.42, .42):
            box(f'cr_post{dx}{dy}', (.03, .03, .85), (cx + dx, cy + dy, FLOOR + 1.21), M_METAL)
    crglass = mat('crglass', (0, 0, 0), .04)
    crglass.node_tree.nodes['Principled BSDF'].inputs['Alpha'].default_value = .1
    box('cr_front', (.82, .005, .84), (cx, cy - .41, FLOOR + 1.21), crglass)
    box('cr_sideR', (.005, .82, .84), (cx + .41, cy, FLOOR + 1.21), crglass)
    box('cr_sideL', (.005, .82, .84), (cx - .41, cy, FLOOR + 1.21), crglass)
    box('cr_rear', (.82, .005, .84), (cx, cy + .41, FLOOR + 1.21), crglass)
    point('cr_bulb', (cx, cy - .05, FLOOR + 1.5), srgb(0xfff2e0), 15, soft=.2, hidden=True)
    glow(box('cr_light', (.78, .78, .012), (cx, cy, FLOOR + 1.62), mat('crlite', (1, 1, 1), .4, emit=srgb(0xfff0d8), strength=3.2)))
    def fur(name, hexv):
        m = noisy(name, srgb(hexv), tuple(c * .78 for c in srgb(hexv)), scale=520, rough=1, bump=.8)
        m.node_tree.nodes['Principled BSDF'].inputs['Sheen Weight'].default_value = .2
        return m

    # stuffed hot dogs, dropped in from above and left wherever they came to rest. The simulation runs on plain capsule-ish
    # stand-ins, then the real toys are put where the stand-ins ended up and the stand-ins go away
    DROPS = 30
    FLOOR_TOP = FLOOR + .78
    INSIDE = .405
    bpy.context.view_layer.update()
    bpy.ops.rigidbody.world_add()
    world_rb = scene.rigidbody_world
    world_rb.substeps_per_frame = 20
    world_rb.solver_iterations = 30
    case = []
    for name, size, at in (
        ('rb_floor', (1.4, 1.4, .2), (cx, cy, FLOOR_TOP - .1)),
        ('rb_front', (1.4, .2, 2.), (cx, cy - INSIDE - .1, FLOOR_TOP + 1)),
        ('rb_rear', (1.4, .2, 2.), (cx, cy + INSIDE + .1, FLOOR_TOP + 1)),
        ('rb_left', (.2, 1.4, 2.), (cx - INSIDE - .1, cy, FLOOR_TOP + 1)),
        ('rb_right', (.2, 1.4, 2.), (cx + INSIDE + .1, cy, FLOOR_TOP + 1)),
    ):
        o = box(name, size, at, M_BLACK)
        bpy.context.view_layer.objects.active = o
        o.select_set(True)
        bpy.ops.rigidbody.object_add(type='PASSIVE')
        o.select_set(False)
        o.rigid_body.collision_shape = 'BOX'
        o.rigid_body.friction = .9
        case.append(o)
    stand_ins = []
    for k in range(DROPS):
        scale = random.uniform(.94, 1.08)
        o = ball(f'rb_dog{k}', 1, (cx + random.uniform(-.24, .24), cy + random.uniform(-.24, .24), FLOOR_TOP + .14 + k * .09), M_BLACK, segs=14)
        o.data.transform(Matrix.Diagonal((.112 * scale, .058 * scale, .048 * scale, 1)))
        o.data.update()
        o.rotation_euler = (random.uniform(0, math.tau), random.uniform(0, math.tau), random.uniform(0, math.tau))
        bpy.context.view_layer.objects.active = o
        o.select_set(True)
        bpy.ops.rigidbody.object_add(type='ACTIVE')
        o.select_set(False)
        rb = o.rigid_body
        rb.collision_shape = 'CONVEX_HULL'
        rb.mass = .12
        rb.friction = .85
        rb.restitution = .02
        rb.linear_damping = .35
        rb.angular_damping = .55
        rb.use_margin = True
        rb.collision_margin = .001
        stand_ins.append((o, scale))
    SETTLE = 360
    world_rb.point_cache.frame_start = 1
    world_rb.point_cache.frame_end = SETTLE
    before = None
    for f in range(1, SETTLE + 1):
        scene.frame_set(f)
        if f == SETTLE - 10:
            bpy.context.view_layer.update()
            before = {o.name: o.matrix_world.translation.copy() for o, _ in stand_ins}
    bpy.context.view_layer.update()
    # did they really land? Every one: its lowest point, whether it has stopped, and what it's touching
    rests = []
    for o, scale in stand_ins:
        M = o.matrix_world.copy()
        vs = [M @ v.co for v in o.data.vertices]
        rests.append((o, scale, M, vs, (M.translation - before[o.name]).length))
    on_floor = sum(min(v.z for v in r[3]) < FLOOR_TOP + .006 for r in rests)
    lowest = min(min(v.z for v in r[3]) for r in rests) - FLOOR_TOP
    outside = sum(max(abs(v.x - cx), abs(v.y - cy)) > INSIDE + .006 for r in rests for v in r[3])
    moving = max(r[4] for r in rests)
    lonely = []
    for i, r in enumerate(rests):
        floored = min(v.z for v in r[3]) < FLOOR_TOP + .006
        near = min((a - b).length for j, q in enumerate(rests) if j != i for a in r[3][::3] for b in q[3][::3])
        if not floored and near > .025:
            lonely.append((r[0].name, round(near, 3)))
    print(f'hot dogs: {len(rests)} settled, {on_floor} on the floor, lowest {lowest:+.4f} from the floor, {outside} verts outside the glass, '
          f'most movement in the last 10 frames {moving:.5f}, top of heap {max(max(v.z for v in r[3]) for r in rests) - FLOOR_TOP:.3f}, floating: {lonely}')
    transforms = [(M, scale) for _, scale, M, _, _ in rests]
    for o, _ in stand_ins:
        bpy.data.objects.remove(o)
    for o in case:
        bpy.data.objects.remove(o)
    bpy.ops.rigidbody.world_remove()
    scene.frame_set(1)

    M_BUN = fur('bun', 0xd9a35a)
    M_DOG = fur('dog', 0xc4502e)
    M_YEL = fur('mustard', 0xf4cc1c)
    M_EYE = mat('dogeye', srgb(0x050505), .15)
    # the one on top of the heap nearest the middle is the claw's: it's rendered alone, and the launcher draws it, so it can leave
    upright = [i for i in range(len(transforms)) if transforms[i][0].col[2].z > .6] or list(range(len(transforms)))
    chosen = max(upright, key=lambda i: transforms[i][0].translation.z - .6 * math.hypot(transforms[i][0].translation.x - cx, transforms[i][0].translation.y - cy))
    for k, (M, scale) in enumerate(transforms):
        root = link(bpy.data.objects.new(f'hotdog{k}', None))
        root.matrix_world = M @ Matrix.Diagonal((scale, scale, scale, 1))
        if k == chosen:
            extras['topdog'] = root

        def lump(part, at, squash, m, segs=18):
            o = ball(f'hd{k}{part}', 1, at, m, segs=segs)
            o.scale = squash
            o.parent = root
            return o
        for side in (-1, 1):
            lump(f'bun{side}', (0, side * .029, -.008), (.098, .029, .038), M_BUN)
            lump(f'eye{side}', (.078, side * .0105, .0345), (.0062, .0062, .0062), M_EYE, segs=10)
        lump('dog', (0, 0, .008), (.112, .0235, .0235), M_DOG)
        squirt = [(-.082 + i * .0164, (.012 if i % 2 else -.012), .0305 + .0035 * math.sin(i / 10 * math.pi)) for i in range(11)]
        o = poly(f'hd{k}must', chaikin(squirt, 2), .0042, M_YEL, res=2)
        o.parent = root

    # the claw is drawn live, on the launcher's time. Here's where it hangs, and where it goes to not win anything
    td = transforms[chosen][0].translation
    extras['claw'] = {'top': FLOOR + 1.61, 'rest': FLOOR + 1.36, 'low': td.z + .08, 'home': (cx + .24, cy + .16), 'over': (td.x, td.y)}

    # the big sign, chase lights all round it, and neon squiggles because it was 1993
    SX, SZ, SW, SH = -1.46, 1.92, 3.1, .78
    glow(face(box('mallsign', (SW, .03, SH), (SX, BACK - .07, SZ), face_mat('mallsign', 'mall_sign.png', .4, emit=2.6)), SW, SH))
    chase = []
    n = 24
    for i in range(n):
        chase.append((SX - SW / 2 - .05 + (SW + .1) * i / (n - 1), BACK - .1, SZ + SH / 2 + .05))
    for i in range(n):
        chase.append((SX - SW / 2 - .05 + (SW + .1) * i / (n - 1), BACK - .1, SZ - SH / 2 - .05))
    for i in range(1, 6):
        chase.append((SX - SW / 2 - .05, BACK - .1, SZ - SH / 2 - .05 + (SH + .1) * i / 6))
        chase.append((SX + SW / 2 + .05, BACK - .1, SZ - SH / 2 - .05 + (SH + .1) * i / 6))
    for i, at in enumerate(chase):
        glow(ball(f'chase{i}', .03, at, mat(f'chase{i}', srgb(0xffe8a0), .3, emit=srgb(0xffd878), strength=6), segs=10))
    extras['bulbs'] = chase
    M_PINK = mat('npink', srgb(0xff3ac0), .3, emit=srgb(0xff1eb0), strength=20)
    M_AQUA = mat('naqua', srgb(0x4af0ff), .3, emit=srgb(0x28e0ff), strength=16)
    zig = [(-6.8 + i * .42, BACK - .06, 2.05 + (.14 if i % 2 else -.14)) for i in range(7)]
    glow(poly('nzig', zig, .017, M_PINK, res=3))
    wav = [(3.3 + i * .16, BACK - .06, 2.0 + .13 * math.sin(i * .9)) for i in range(20)]
    glow(poly('nwave', chaikin(wav, 1), .017, M_AQUA, res=3))
    glow(face(box('tokens', (.72, .02, .36), (-3.6, BACK - .08, 1.95), face_mat('tokens', 'mall_tokens.png', .5, emit=1.4)), .72, .36))
    for k, (x, y, col) in enumerate(((-3.6, 1.6, 0xff1eb0), (.4, 2.4, 0x28e0ff), (-.8, 5.2, 0x8a3cff), (3.0, 4.6, 0xff1eb0), (-5.2, 4.0, 0x28e0ff))):
        tube = mat(f'ctube{k}', (0, 0, 0), .4, emit=srgb(col), strength=5)
        glow(box(f'ctube{k}', (1.6, .03, .02), (x, y, TOP - .05), tube))
        l = area(f'ctubel{k}', (x, y, TOP - .08), 1.6, srgb(col), 22, (x, y, FLOOR), size_y=.3)
        l.visible_camera = False

    # the prize counter, and what's on it
    cabinet(noisy('counter', srgb(0x0e0a16), srgb(0x1c1426), scale=380, rough=.24, bump=.05))
    glow(box('counteredge', (6.5, .004, .008), (0, -.342, -.018), mat('cedge', (0, 0, 0), .4, emit=srgb(0xff3ac0), strength=3)))
    console(-.96, -.03, -9, body=mat('conpurp', srgb(0x2a2438), .36), top=mat('conpurp2', srgb(0x3a3448), .36), band=M_PLASTIC)
    pad(-.68, -.17, 22, (-.82, -.15), body=M_PLASTIC2)
    cart(0, -1.5, -.14, .012, 26)
    cart(1, -1.46, .08, .012, -14)
    cables(-1.12, TV_X - .2, .09, n=4)
    can('can1', -.13, .13, 'gas', turn=.12)
    magazines(-1.78, .1, 3)
    # a paper cup of tokens, and the ones that got away
    wax = mat('cup', srgb(0xe4dcc4), .5)
    lathe('tokencup', [(.034, 0), (.036, .004), (.047, .12), (.049, .124)], (-.36, .1, .001), wax, verts=32)
    M_TOKEN = mat('token', srgb(0xc8a24a), .28, 1)
    for k in range(9):
        a = random.uniform(0, math.tau)
        r = random.uniform(0, .03)
        cyl(f'cuptoken{k}', .0125, .0025, (-.36 + r * math.cos(a), .1 + r * math.sin(a), .118 + k * .001), M_TOKEN, rot=(random.uniform(-.4, .4), random.uniform(-.4, .4), 0), verts=20)
    for k, (x, y) in enumerate(((-.5, -.12), (-.47, -.23), (-.3, -.09), (-.24, -.2), (-.1, -.15), (-.44, -.05), (-.16, -.28))):
        cyl(f'token{k}', .0125, .0025, (x, y, .0028), M_TOKEN, verts=20)
    # the tail of a ticket strip, all the way to the edge
    pink = mat('ticket', srgb(0xe88ab0), .75)
    sheet('tickets', .62, .03, 60, 2, lambda u, v: (0, 0, .004 + .006 * abs(math.sin(u * 19))), (-1.62, -.27, .0), pink, rot=(0, 0, math.radians(-7)))

    area('counterkey', (-.8, -.8, 1.3), 3, srgb(0xffc8e8), 8, (-.7, .1, 0))
    area('counterL', (-2.1, -1.0, .9), 1.2, srgb(0x6a3cff), 10, (-.9, 0, .05))
    area('counterR', (2.6, -.1, .8), 1, srgb(0x28d8ff), 10, (.7, 0, .3))
    behind = area('behindtv', (.5, 1.3, .9), .9, srgb(0xff3ac0), 7, (.5, .1, .4))
    behind.visible_camera = False


{'neon': neon, 'basement': basement, 'rain': rain, 'grid': grid, 'mall': mall}[ROOM]()


# ---- render ------------------------------------------------------------------------------------

def projected(world):
    co = world_to_camera_view(scene, cam, Vector(world))
    return [co.x * W, (1 - co.y) * H]


if 'topdog' in extras:
    # the claw's hot dog in the room's own light, on nothing, then gone from the room so it isn't there twice
    root = extras['topdog']
    parts = [o for o in scene.collection.objects if o.parent is root]
    keep = set(parts) | set(lights) | {root}
    for o in scene.collection.objects:
        o.hide_render = o not in keep
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.cycles.samples = 256
    scene.render.filepath = f'{OUT}/topdog.png'
    bpy.ops.render.render(write_still=True)
    for o in scene.collection.objects:
        o.hide_render = False
    for o in parts:
        bpy.data.objects.remove(o)
    bpy.data.objects.remove(root)
    extras.pop('topdog')
    scene.render.film_transparent = False
    scene.render.image_settings.color_mode = 'RGB'
    scene.cycles.samples = SAMPLES
MODES = ('room', 'tv', 'plate', 'mask') if pane else ('room', 'tv')
everything = list(scene.collection.objects)
interior = [o for o in everything if o not in outside and o is not pane and o not in lights]


def world(color):
    w = bpy.data.worlds.new('w')
    w.use_nodes = True
    w.node_tree.nodes['Background'].inputs[0].default_value = (*color, 1)
    scene.world = w


def set_pass(mode):
    for l in lights:
        l.hide_render = mode != 'room'
    for o in interior:
        o.hide_render = mode == 'plate' or (mode == 'tv' and o in glowing)
        o.is_holdout = mode == 'mask'
    for o in outside:
        o.hide_render = mode != 'plate'
    if pane:
        pane.hide_render = mode != 'mask'
    screen_mesh.materials[0] = M_GLOW if mode == 'tv' else M_GLASS
    world((.62, .66, .7) if mode == 'plate' else (0, 0, 0))
    scene.render.film_transparent = mode == 'mask'
    scene.render.image_settings.color_mode = 'RGBA' if mode == 'mask' else 'RGB'
    scene.cycles.use_denoising = mode != 'mask'
    scene.cycles.samples = 64 if mode == 'mask' else SAMPLES


os.makedirs(OUT, exist_ok=True)
bpy.context.view_layer.update()
corners = []
for u, v in ((-1, 1), (1, 1), (1, -1), (-1, -1)):
    lx, ly, lz = SCR_CX + u * SCR_W / 2, FRONT - .004, SCR_CZ + v * SCR_H / 2
    corners.append(projected((pivot.x + lx * c - ly * s, pivot.y + lx * s + ly * c, lz)))
info = {'screen': corners, 'ledge': projected((0, -.32, 0)), 'w': W, 'h': H}
if 'lamp' in extras:
    LX, LY = extras['lamp']
    lo = projected((LX, LY, .19))
    hi = projected((LX, LY, .52))
    info['lamp'] = [lo + [projected((LX + LAMP_LOW, LY, .19))[0] - lo[0]], hi + [projected((LX + LAMP_TOP, LY, .52))[0] - hi[0]]]
if 'steam' in extras:
    info['steam'] = [projected(p) for p in extras['steam']]
    info['steam_size'] = extras.get('steam_size', 1)
if 'bulbs' in extras:
    info['bulbs'] = [projected(p) for p in extras['bulbs']]
if 'runners' in extras:
    # cut small so perspective stays true, and each point told whether the camera can see it past what's in the way
    depsgraph = bpy.context.evaluated_depsgraph_get()

    def by_step(pts):
        out = []
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            n = max(1, round((abs(x1 - x0) + abs(y1 - y0)) / extras['runner_step']))
            out += [(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n) for i in range(n)]
        return out + [pts[-1]]

    def seen(x, y):
        to = Vector((x, y, extras['runner_z']))
        frm = Vector(cam.location)
        d = to - frm
        hit, *_ = scene.ray_cast(depsgraph, frm, d.normalized(), distance=d.length - .05)
        return not hit
    info['runners'] = []
    for r in extras['runners']:
        pts = by_step(r['p'])
        info['runners'].append({'c': r['c'], 's': r['s'], 'p': [projected((x, y, extras['runner_z'])) for x, y in pts], 'v': [seen(x, y) for x, y in pts]})
if 'claw' in extras:
    k = extras['claw']
    hx, hy = k['home']
    ox, oy = k['over']
    info['claw'] = {
        'home_top': projected((hx, hy, k['top'])), 'home_rest': projected((hx, hy, k['rest'])),
        'over_top': projected((ox, oy, k['top'])), 'over_rest': projected((ox, oy, k['rest'])), 'over_low': projected((ox, oy, k['low'])),
        'unit': projected((ox, oy, k['low'] + .1))[1] - projected((ox, oy, k['low']))[1],
    }
if 'passers' in extras:
    info['passers'] = []
    for r in extras['passers']:
        (x0, x1) = r['x']
        n = max(1, round(abs(x1 - x0) / extras['runner_step']))
        foot = [projected((x0 + (x1 - x0) * i / n, r['y'], r['z'])) for i in range(n + 1)]
        head = projected(((x0 + x1) / 2, r['y'], r['z'] + r['h']))
        low = projected(((x0 + x1) / 2, r['y'], r['z']))
        info['passers'].append({'sprite': r['sprite'], 'p': foot, 'h': low[1] - head[1], 'step': r['step'], 'every': r['every'], 'at': r['at'], 'wall': r.get('wall', 0), 'plane': r['y']})
json.dump(info, open(OUT + '/room.json', 'w'), indent=1)
print('corners', corners, 'ledge', info['ledge'])

if 'passers' in extras:
    MIST = ('plain', 'gx', 'gy', 'range', 'horizon', 'sky', 'tower', 'beam')
    for plane in sorted({r['y'] for r in extras['passers']}):
        for mode_o in everything:
            if mode_o.name.startswith(MIST) or mode_o in lights:
                mode_o.hide_render = True
                continue
            ys = [(mode_o.matrix_world @ Vector(c)).y for c in mode_o.bound_box]
            mode_o.hide_render = min(ys) > plane
        screen_mesh.materials[0] = M_BLACK
        world((0, 0, 0))
        scene.render.film_transparent = True
        scene.render.image_settings.file_format = 'PNG'
        scene.render.image_settings.color_mode = 'RGBA'
        scene.cycles.use_denoising = False
        scene.cycles.samples = 16
        scene.render.filepath = f"{OUT}/nearer{plane:.2f}.png"
        bpy.ops.render.render(write_still=True)
        print('rendered nearer than', plane)
    for mode_o in everything:
        mode_o.hide_render = False
    screen_mesh.materials[0] = M_GLASS
    scene.render.film_transparent = False
    scene.render.image_settings.color_mode = 'RGB'
    scene.cycles.use_denoising = True

scene.render.image_settings.file_format = 'PNG'
for name in MODES:
    set_pass(name)
    scene.render.filepath = f'{OUT}/{name}.png'
    bpy.ops.render.render(write_still=True)
    print('rendered', name)
