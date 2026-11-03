# What crosses the Grid room, as real models: dark faces, every hard edge a line of light. Renders on transparent; tools/finish_sprites.py adds the glow.
#   blender -b -P render/grid_sprites.py -- <out dir>
import math
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

OUT = sys.argv[sys.argv.index('--') + 1]


def srgb(h):
    def f(c):
        c /= 255
        return c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4
    return (f((h >> 16) & 255), f((h >> 8) & 255), f(h & 255))


def clear():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)


def link(o):
    bpy.context.scene.collection.objects.link(o)
    return o


def shine(name, color, power):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (0, 0, 0, 1)
    b.inputs['Emission Color'].default_value = (*color, 1)
    b.inputs['Emission Strength'].default_value = power
    return m


def faceted(name, color, power, floor=.3):
    """A face's brightness depends only on which way it points, so hard shapes read as hard shapes."""
    m = shine(name, color, power)
    nt = m.node_tree
    g = nt.nodes.new('ShaderNodeNewGeometry')
    d = nt.nodes.new('ShaderNodeVectorMath')
    d.operation = 'DOT_PRODUCT'
    d.inputs[1].default_value = Vector((-.35, -.8, .5)).normalized()
    mx = nt.nodes.new('ShaderNodeMath')
    mx.operation = 'MAXIMUM'
    mx.inputs[1].default_value = floor
    k = nt.nodes.new('ShaderNodeMath')
    k.operation = 'MULTIPLY'
    k.inputs[1].default_value = power
    nt.links.new(g.outputs['Normal'], d.inputs[0])
    nt.links.new(d.outputs['Value'], mx.inputs[0])
    nt.links.new(mx.outputs[0], k.inputs[0])
    nt.links.new(k.outputs[0], nt.nodes['Principled BSDF'].inputs['Emission Strength'])
    return m


def tube(name, pts, r, material, cyclic=False):
    c = bpy.data.curves.new(name, 'CURVE')
    c.dimensions = '3D'
    c.bevel_depth = r
    c.bevel_resolution = 2
    s = c.splines.new('POLY')
    s.points.add(len(pts) - 1)
    for p, q in zip(s.points, pts):
        p.co = (*q, 1)
    s.use_cyclic_u = cyclic
    c.materials.append(material)
    return link(bpy.data.objects.new(name, c))


def solid(name, verts, faces, material, parent=None, edges=None, edge_r=.012):
    """A flat-shaded solid. With a material for its edges, each edge sharper than a crease gets a line of light."""
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    if edges:
        bm.edges.ensure_lookup_table()
        for i, e in enumerate(bm.edges):
            if len(e.link_faces) < 2 or e.calc_face_angle(0) > math.radians(24):
                tube(f'{name}e{i}', [tuple(e.verts[0].co), tuple(e.verts[1].co)], edge_r, edges)
    bm.free()
    me.materials.append(material)
    return link(bpy.data.objects.new(name, me))


def prism(name, outline, y0, y1, material, edges=None, edge_r=.012):
    """An outline in x, z pushed out along y."""
    n = len(outline)
    verts = [(x, y0, z) for x, z in outline] + [(x, y1, z) for x, z in outline]
    faces = [tuple(range(n)), tuple(range(n, 2 * n))] + [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
    return solid(name, verts, faces, material, edges=edges, edge_r=edge_r)


def arc(cx, cz, r, a0, a1, n):
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)), cz + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def camera(loc, target, ortho):
    d = bpy.data.cameras.new('c')
    d.type = 'ORTHO'
    d.ortho_scale = ortho
    o = link(bpy.data.objects.new('c', d))
    o.location = loc
    o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    bpy.context.scene.camera = o


def render(name, w, h):
    s = bpy.context.scene
    s.render.engine = 'CYCLES'
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'OPTIX'
    prefs.get_devices()
    for d in prefs.devices:
        d.use = d.type != 'CPU'
    s.cycles.device = 'GPU'
    s.cycles.samples = 96
    s.cycles.use_denoising = True
    s.view_settings.view_transform = 'Standard'
    s.render.film_transparent = True
    s.render.resolution_x, s.render.resolution_y = w, h
    s.render.image_settings.file_format = 'PNG'
    s.render.image_settings.color_mode = 'RGBA'
    s.render.filepath = f'{OUT}/{name}.png'
    bpy.ops.render.render(write_still=True)


def gloss(name, color, rough=.24, metal=.1):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*color, 1)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    return m


def spline(pts, each=10, closed=True):
    """A smooth line through points: Catmull-Rom, so a few points make a long clean curve."""
    n = len(pts)
    out = []
    for i in range(n if closed else n - 1):
        p0, p1, p2, p3 = (pts[(i + k) % n] if closed else pts[min(max(i + k, 0), n - 1)] for k in (-1, 0, 1, 2))
        for j in range(each):
            u = j / each
            out.append(tuple(.5 * (2 * p1[c] + (p2[c] - p0[c]) * u + (2 * p0[c] - 5 * p1[c] + 4 * p2[c] - p3[c]) * u * u + (3 * p1[c] - p0[c] - 3 * p2[c] + p3[c]) * u ** 3) for c in (0, 1)))
    return out


def pillow(name, outline, half, round_, material):
    """An outline in x, z made solid, its edges rolled over like moulded plastic."""
    c = bpy.data.curves.new(name, 'CURVE')
    c.dimensions = '2D'
    c.fill_mode = 'BOTH'
    c.extrude = max(half - round_, .001)
    c.bevel_depth = round_
    c.bevel_resolution = 4
    s = c.splines.new('POLY')
    s.points.add(len(outline) - 1)
    for p, q in zip(s.points, outline):
        p.co = (q[0], q[1], 0, 1)
    s.use_cyclic_u = True
    c.materials.append(material)
    o = link(bpy.data.objects.new(name, c))
    o.rotation_euler = (math.pi / 2, 0, 0)
    return o


def cycle(name, coat, rim, dark):
    """One smooth shell sweeping nose to tail over two great disc wheels, the dark machinery showing through the middle."""
    clear()
    R = .47
    FX, RX = 1.1, -1.1
    WZ = R
    M_COAT = gloss(name + 'coat', srgb(coat), .2, .15)
    M_DARK = gloss(name + 'dark', srgb(dark), .16, .3)
    M_TYRE = gloss(name + 'tyre', srgb(0x07080a), .34)
    M_RIM = shine(name + 'rim', srgb(rim), 7)
    M_HUB = gloss(name + 'hub', srgb(0x181a20), .2, .7)

    def circle(cx, cz, r, a0, a1, n):
        return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)), cz + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]

    # the machinery in the middle
    pillow(name + 'core', spline([(1.02, .9), (.3, 1.08), (-.5, 1.12), (-1.12, .96), (-.72, .26), (0, .16), (.72, .26)], 10), .16, .06, M_DARK)
    # the shell: over the top from the nose to the tail, then back underneath, hugging the wheel arches
    A = R + .07
    top = [(1.56, .24), (1.7, .5), (1.58, .82), (1.16, 1.06), (.5, 1.14), (-.26, 1.2), (-.98, 1.2), (-1.5, 1.04), (-1.72, .72), (-1.68, .3), (-1.56, .18)]
    under = circle(RX, WZ, A, 192, 40, 12) + [(-.42, 1.08), (.26, 1.02)] + circle(FX, WZ, A, 140, -14, 12)
    pillow(name + 'shell', spline(top + under, 7), .23, .1, M_COAT)
    # the cockpit, a dark glass hump let into the spine
    pillow(name + 'canopy', spline([(.42, .98), (-.1, 1.06), (-.62, 1.04), (-.68, .74), (-.1, .62), (.4, .68)], 8), .2, .08, gloss(name + 'glass', srgb(0x1a2230), .05, .5))
    for wx, tag in ((FX, 'f'), (RX, 'r')):
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=96, radius1=R, radius2=R, depth=.4)
        bmesh.ops.bevel(bm, geom=bm.edges[:], offset=.03, segments=3, affect='EDGES')
        me = bpy.data.meshes.new(name + tag)
        bm.to_mesh(me)
        bm.free()
        for f in me.polygons:
            f.use_smooth = True
        me.materials.append(M_TYRE)
        o = link(bpy.data.objects.new(name + tag, me))
        o.matrix_world = Matrix.Translation((wx, 0, WZ)) @ Matrix.Rotation(math.pi / 2, 4, 'X')
        for side in (-1, 1):
            ring = [(wx + R * .8 * math.cos(a * math.tau / 96), side * .206, WZ + R * .8 * math.sin(a * math.tau / 96)) for a in range(96)]
            tube(f'{name}{tag}rim{side}', ring, .018, M_RIM, cyclic=True)
            bm = bmesh.new()
            bmesh.ops.create_cone(bm, cap_ends=True, segments=48, radius1=R * .34, radius2=R * .22, depth=.05)
            me = bpy.data.meshes.new(f'{name}{tag}hub{side}')
            bm.to_mesh(me)
            bm.free()
            for f in me.polygons:
                f.use_smooth = True
            me.materials.append(M_HUB)
            o = link(bpy.data.objects.new(f'{name}{tag}hub{side}', me))
            o.matrix_world = Matrix.Translation((wx, side * .22, WZ)) @ Matrix.Rotation(math.pi / 2 * side, 4, 'X')
    # the light it gives off: a line along the underside of the shell
    edge = [(x, -.232, z) for x, z in spline(under, 4, closed=False)]
    tube(name + 'glowline', edge, .011, M_RIM)
    # a studio's worth of light, because the shell is all about its highlights
    w = bpy.data.worlds.new('w')
    w.use_nodes = True
    w.node_tree.nodes['Background'].inputs[0].default_value = (*srgb(0x2a3c58), 1)
    w.node_tree.nodes['Background'].inputs[1].default_value = .55
    bpy.context.scene.world = w
    for lname, loc, size, power, col in (('key', (-2.4, -5, 5), 5, 420, 0xffffff), ('rimlight', (4.5, 2.6, 2.5), 3, 260, 0xbfdcff), ('under', (0, -4, -2.2), 4, 45, 0xffffff)):
        l = bpy.data.lights.new(lname, 'AREA')
        l.size = size
        l.energy = power
        l.color = srgb(col)
        o = link(bpy.data.objects.new(lname, l))
        o.location = loc
        o.rotation_euler = (Vector((0, 0, .6)) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    # three-quarters on and a little above, nose to the right
    camera((3.3, -8.4, 2.1), (.02, 0, .62), 4.15)
    render(name, 1200, 700)


def recognizer():
    """The patrol. Two square legs on wedge feet, two crossbeams, a chamfered body slung between, a pyramid on the top. Black, drawn in red."""
    clear()
    bpy.context.scene.world = None
    M_FACE = shine('rface', srgb(0x5c6e6a), 1)
    nt = M_FACE.node_tree
    g = nt.nodes.new('ShaderNodeNewGeometry')
    d = nt.nodes.new('ShaderNodeVectorMath')
    d.operation = 'DOT_PRODUCT'
    d.inputs[1].default_value = Vector((.72, -.42, .55)).normalized()
    mx = nt.nodes.new('ShaderNodeMath')
    mx.operation = 'MAXIMUM'
    mx.inputs[1].default_value = .012
    k = nt.nodes.new('ShaderNodeMath')
    k.operation = 'MULTIPLY'
    k.inputs[1].default_value = .2
    nt.links.new(g.outputs['Normal'], d.inputs[0])
    nt.links.new(d.outputs['Value'], mx.inputs[0])
    nt.links.new(mx.outputs[0], k.inputs[0])
    nt.links.new(k.outputs[0], nt.nodes['Principled BSDF'].inputs['Emission Strength'])
    M_RED = shine('redge', srgb(0xff2410), 4.2)
    R = .055

    def blk(name, x0, x1, y0, y1, z0, z1):
        v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        f = [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
        return solid(name, v, f, M_FACE, edges=M_RED, edge_r=R)

    def plate(name, front, back, y0, y1):
        """A shape in x, z at the front, a shape at the back, joined up."""
        n = len(front)
        v = [(x, y0, z) for x, z in front] + [(x, y1, z) for x, z in back]
        f = [tuple(range(n)), tuple(range(n, 2 * n))] + [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
        return solid(name, v, f, M_FACE, edges=M_RED, edge_r=R)

    for sx in (-1, 1):
        cx = sx * 5.1
        # the leg, a touch wider at the bottom, standing on its foot
        v = [(cx - .95, -.95, -7.6), (cx + .95, -.95, -7.6), (cx + .95, .95, -7.6), (cx - .95, .95, -7.6), (cx - .82, -.82, -.05), (cx + .82, -.82, -.05), (cx + .82, .82, -.05), (cx - .82, .82, -.05)]
        solid(f'leg{sx}', v, [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)], M_FACE, edges=M_RED, edge_r=R)
        # the wedge foot running forward and in
        v = [(cx - .95, -.95, -7.6), (cx + .95, -.95, -7.6), (cx + .95, -.95, -5.9), (cx - .95, -.95, -5.9), (cx - .75 - sx * .9, -3.5, -7.6), (cx + .75 - sx * .9, -3.5, -7.6)]
        solid(f'foot{sx}', v, [(0, 1, 2, 3), (0, 1, 5, 4), (1, 2, 5), (0, 3, 4), (2, 3, 4, 5)], M_FACE, edges=M_RED, edge_r=R)
        # the short post between the beams, and the stub reaching in to the body
        blk(f'post{sx}', cx - .78, cx + .78, -.74, .74, .42, 2.9)
        x0, x1 = sorted((sx * 3.15, sx * 4.32))
        blk(f'stub{sx}', x0, x1, -.42, .42, 1.25, 1.95)
    blk('lower', -6.25, 6.25, -.92, .92, 0, .42)
    blk('upper', -6.5, 6.5, -1.0, 1.0, 2.9, 3.34)
    # the body: wide and chamfered, hung between the beams
    plate('body', [(-3.5, 2.86), (3.5, 2.86), (3.45, 2.2), (2.5, .46), (-2.5, .46), (-3.45, 2.2)],
          [(-3.2, 2.86), (3.2, 2.86), (3.15, 2.2), (2.25, .46), (-2.25, .46), (-3.15, 2.2)], -1.24, .85)
    plate('visor', [(-2.1, 2.44), (2.1, 2.44), (1.42, 1.58), (-1.42, 1.58)], [(-1.9, 2.3), (1.9, 2.3), (1.3, 1.68), (-1.3, 1.68)], -1.46, -1.22)
    plate('chin', [(-.95, 1.26), (.95, 1.26), (.65, .78), (-.65, .78)], [(-.8, 1.2), (.8, 1.2), (.55, .84), (-.55, .84)], -1.4, -1.22)
    # the keel under the lower beam
    plate('keel', [(-2.15, 0), (2.15, 0), (1.3, -.82), (-1.3, -.82)], [(-1.85, 0), (1.85, 0), (1.05, -.7), (-1.05, -.7)], -.98, .78)
    # the pyramid on the upper beam, with its little head
    plate('roof', [(-3.5, 3.34), (3.5, 3.34), (.78, 4.82), (-.78, 4.82)], [(-3.3, 3.34), (3.3, 3.34), (.6, 4.82), (-.6, 4.82)], -.95, .95)
    plate('headcap', [(-.86, 4.82), (.86, 4.82), (.62, 5.42), (-.62, 5.42)], [(-.7, 4.82), (.7, 4.82), (.48, 5.42), (-.48, 5.42)], -.56, .56)
    plate('window', [(-.9, 4.72), (.9, 4.72), (.56, 3.9), (-.56, 3.9)], [(-.78, 4.62), (.78, 4.62), (.48, 3.92), (-.48, 3.92)], -.82, -.6)
    # looking up at it from the ground, a little off to one side
    d = bpy.data.cameras.new('c')
    d.lens = 62
    d.sensor_width = 36
    o = link(bpy.data.objects.new('c', d))
    o.location = (11.5, -34, -6.2)
    o.rotation_euler = (Vector((0, 0, -1.15)) - Vector(o.location)).to_track_quat('-Z', 'Y').to_euler()
    bpy.context.scene.camera = o
    render('recognizer', 1200, 1200)


cycle('cycle_blue', 0x1f8cff, 0x6adcff, 0x0a0e18)
cycle('cycle_yellow', 0xf79a14, 0xffc24a, 0x120c08)
recognizer()
