# The app's logo: one cold weenie, no bun, on nothing. RGBA with its shadow, for tools/make_brand.py.
# blender -b -P render/weenie.py -- <out.png> <samples>
import math
import sys

import bpy

argv = sys.argv[sys.argv.index('--') + 1:]
OUT, SAMPLES = argv[0], int(argv[1])

for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)

LEN, R0, BEND = 3.5, .25, .2
RINGS, SIDES = 260, 72
verts, faces = [], []
for i in range(RINGS + 1):
    t = i / RINGS * 2 - 1
    u = abs(t)
    # a straight casing that rounds off fast, then a little pinched nub where it was tied
    r = R0 * (1 + .012 * math.sin(t * 4.1 + .7))
    if u > .88:
        r *= math.sqrt(max(0, 1 - ((u - .88) / .12) ** 2)) ** .9
    if u > .985:
        r = max(r, .022)
    x = t * LEN / 2
    y = BEND * (1 - t * t) * 1.0
    z = R0 + .02 * math.sin(t * 1.3)
    # slack in the casing: fine wrinkles that only show near the ends
    wr = (max(0, u - .62) / .38) ** 2
    for k in range(SIDES):
        a = k / SIDES * math.tau
        rr = r * (1 + wr * .022 * math.sin(a * 9 + t * 31) + wr * .012 * math.sin(a * 17 - t * 57))
        verts.append((x, y + rr * math.cos(a), z + rr * math.sin(a)))
for i in range(RINGS):
    for k in range(SIDES):
        a, b = i * SIDES + k, i * SIDES + (k + 1) % SIDES
        faces.append((a, b, b + SIDES, a + SIDES))
faces.append(tuple(range(SIDES))[::-1])
faces.append(tuple(RINGS * SIDES + k for k in range(SIDES)))
me = bpy.data.meshes.new('weenie')
me.from_pydata(verts, [], faces)
me.update()
for p in me.polygons:
    p.use_smooth = True
ob = bpy.data.objects.new('weenie', me)
bpy.context.scene.collection.objects.link(ob)

# dull, pale, a day in the fridge: pink-tan casing with mottled fat under it and hardly any shine
m = bpy.data.materials.new('casing')
m.use_nodes = True
nt = m.node_tree
bs = nt.nodes['Principled BSDF']
bs.inputs['Roughness'].default_value = .36
bs.inputs['Subsurface Weight'].default_value = .22
bs.inputs['Subsurface Radius'].default_value = (.5, .22, .14)
bs.inputs['Subsurface Scale'].default_value = .12
co = nt.nodes.new('ShaderNodeTexCoord')
noise = nt.nodes.new('ShaderNodeTexNoise')
noise.inputs['Scale'].default_value = 16
noise.inputs['Detail'].default_value = 4
ramp = nt.nodes.new('ShaderNodeValToRGB')
ramp.color_ramp.elements[0].position = .34
ramp.color_ramp.elements[0].color = (.47, .125, .052, 1)
ramp.color_ramp.elements[1].position = .72
ramp.color_ramp.elements[1].color = (.54, .155, .068, 1)
nt.links.new(co.outputs['Object'], noise.inputs['Vector'])
nt.links.new(noise.outputs['Fac'], ramp.inputs['Fac'])
nt.links.new(ramp.outputs['Color'], bs.inputs['Base Color'])
fine = nt.nodes.new('ShaderNodeTexNoise')
fine.inputs['Scale'].default_value = 90
fine.inputs['Detail'].default_value = 5
bump = nt.nodes.new('ShaderNodeBump')
bump.inputs['Strength'].default_value = .16
bump.inputs['Distance'].default_value = .02
nt.links.new(co.outputs['Object'], fine.inputs['Vector'])
nt.links.new(fine.outputs['Fac'], bump.inputs['Height'])
nt.links.new(bump.outputs['Normal'], bs.inputs['Normal'])
me.materials.append(m)

# what it lies on only shows as a shadow
bpy.ops.mesh.primitive_plane_add(size=40)
floor = bpy.context.object
floor.is_shadow_catcher = True

sun = bpy.data.lights.new('key', 'AREA')
sun.shape = 'RECTANGLE'
sun.size, sun.size_y = 7, 5
sun.energy = 430
kl = bpy.data.objects.new('key', sun)
kl.location = (-1.5, -2.2, 5.5)
kl.rotation_euler = (math.radians(24), math.radians(-14), 0)
bpy.context.scene.collection.objects.link(kl)

w = bpy.data.worlds.new('w')
w.use_nodes = True
w.node_tree.nodes['Background'].inputs['Color'].default_value = (1, 1, 1, 1)
w.node_tree.nodes['Background'].inputs['Strength'].default_value = .5
bpy.context.scene.world = w

cam = bpy.data.cameras.new('c')
cam.lens = 85
co = bpy.data.objects.new('c', cam)
co.location = (0, -8.6, 5.8)
co.rotation_euler = (math.radians(56.5), 0, 0)
bpy.context.scene.collection.objects.link(co)
bpy.context.scene.camera = co

s = bpy.context.scene
s.render.engine = 'CYCLES'
prefs = bpy.context.preferences.addons['cycles'].preferences
prefs.compute_device_type = 'OPTIX'
prefs.get_devices()
for d in prefs.devices:
    d.use = d.type == 'OPTIX'
s.cycles.device = 'GPU'
s.cycles.samples = SAMPLES
s.cycles.use_denoising = True
s.render.film_transparent = True
s.render.resolution_x, s.render.resolution_y = 1600, 900
s.render.image_settings.file_format = 'PNG'
s.render.image_settings.color_mode = 'RGBA'
s.view_settings.view_transform = 'Standard'
s.render.filepath = OUT
bpy.ops.render.render(write_still=True)
