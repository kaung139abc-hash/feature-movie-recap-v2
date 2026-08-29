#!/usr/bin/env python3
"""
Blender headless script to animate a glTF character's shape keys according to viseme timings
Usage inside blender:
blender --background --python blender_animate.py -- <visemes.json> <character.glb> <narration.mp3> <output.mp4> <fps>

Notes:
- This script requires Blender's Python environment (bpy).
- The character GLB must contain shape keys named to match the viseme mapping below (e.g., viseme_A, viseme_O, viseme_M, etc.).
- The script will create keyframes for shape keys and add the narration audio as a strip; then render the animation to an MP4.
"""

import sys
import json
import os

# The following import only works inside Blender's python (bpy available)
try:
    import bpy
except Exception as e:
    print("This script must be run inside Blender (bpy module not found).", e)
    sys.exit(2)

argv = sys.argv
if "--" not in argv:
    print("Expected args after --: visemes.json character.glb narration.mp3 output.mp4 [fps]")
    sys.exit(2)
idx = argv.index("--")
args = argv[idx+1:]
if len(args) < 4:
    print("Usage: blender --background --python blender_animate.py -- <visemes.json> <character.glb> <narration.mp3> <output.mp4> [fps]")
    sys.exit(2)

viseme_path, character_path, narration_path, output_path = args[0:4]
fps = int(args[4]) if len(args) > 4 else 30

print(f"Visemes: {viseme_path}\nCharacter: {character_path}\nNarration: {narration_path}\nOutput: {output_path}\nFPS: {fps}")

# Load visemes
with open(viseme_path, 'r', encoding='utf-8') as f:
    visemes = json.load(f)

# Clear default scene
bpy.ops.wm.read_factory_settings(use_empty=True)

# Import the character glTF
bpy.ops.import_scene.gltf(filepath=character_path)

# Find the object that has shape keys
shape_obj = None
for obj in bpy.data.objects:
    if obj.type == 'MESH' and obj.data.shape_keys:
        shape_obj = obj
        break
if not shape_obj:
    print('No mesh with shape keys found in the imported glTF. Exiting.')
    sys.exit(3)

# Map rhubarb viseme labels to shape key names in the model
# Adjust this mapping according to the shape key names in your character
VISEME_TO_SHAPE = {
    'A': 'viseme_A',
    'E': 'viseme_E',
    'I': 'viseme_I',
    'O': 'viseme_O',
    'U': 'viseme_U',
    'M': 'viseme_M',
    'L': 'viseme_L',
    'W': 'viseme_W',
    'F': 'viseme_F',
    'TH': 'viseme_TH',
    'rest': 'viseme_rest'
}

# Ensure shape keys exist; create missing as zeroed if needed
shape_keys = shape_obj.data.shape_keys.key_blocks
for label, skname in VISEME_TO_SHAPE.items():
    if skname not in shape_keys:
        print(f"Warning: shape key {skname} not found. Creating a placeholder zeroed key.")
        shape_obj.shape_key_add(name=skname, from_mix=False)

# Prepare scene settings
scene = bpy.context.scene
scene.render.fps = fps
scene.frame_start = 1
# estimate frame_end from visemes and narration length (we'll set a large end and adjust)
# Add audio to sequence editor
bpy.context.scene.sequence_editor_create()
se = bpy.context.scene.sequence_editor
audio_strip = se.sequences.new_sound(name='Narration', filepath=narration_path, channel=1, frame_start=1)

# Get audio length (seconds)
try:
    # Blender provides sound datablock with frame_length when loaded
    audio = audio_strip.sound
    audio_length_seconds = audio.frame_duration / scene.render.fps
except Exception:
    # fallback: estimate 8 minutes
    audio_length_seconds = 8 * 60

frame_end = int(audio_length_seconds * fps) + 10
scene.frame_end = frame_end

# Helper to set shape key value at a frame
def set_shape_value(sk_name, value, frame):
    kb = shape_obj.data.shape_keys.key_blocks.get(sk_name)
    if not kb:
        return
    kb.value = value
    kb.keyframe_insert(data_path='value', frame=frame)

# Reset all shape keys to zero at frame 0
for kb in shape_obj.data.shape_keys.key_blocks:
    kb.value = 0.0
    kb.keyframe_insert(data_path='value', frame=0)

# Viseme entries from Rhubarb format: { "visemes": [ {"start": 0.12, "end": 0.18, "value": "A"}, ... ] }
vis_events = visemes.get('visemes') if isinstance(visemes, dict) else (visemes if isinstance(visemes, list) else [])
if isinstance(vis_events, dict):
    vis_events = vis_events.get('visemes', [])

for ev in vis_events:
    try:
        label = ev.get('value') or ev.get('label')
        start = float(ev.get('start', 0.0))
        end = float(ev.get('end', start + 0.1))
    except Exception:
        continue
    sk = VISEME_TO_SHAPE.get(label, VISEME_TO_SHAPE.get('rest'))
    start_frame = int(start * fps) + 1
    mid_frame = int(((start + end) / 2.0) * fps) + 1
    end_frame = int(end * fps) + 1
    # set shape at mid to 1.0 and back to 0 at end
    set_shape_value(sk, 1.0, mid_frame)
    set_shape_value(sk, 0.0, end_frame + 1)

# Optionally add simple idle body animation or keep static

# Camera setup: if no camera, create one
if not bpy.data.cameras:
    cam_data = bpy.data.cameras.new('Camera')
    cam_obj = bpy.data.objects.new('Camera', cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)
    bpy.context.scene.camera = cam_obj
    cam_obj.location = (0.0, -3.0, 1.6)
    cam_obj.rotation_euler = (1.2, 0, 0)

# Lighting: add a key light
if 'KeyLight' not in bpy.data.lights:
    light_data = bpy.data.lights.new(name='KeyLight', type='AREA')
    light_obj = bpy.data.objects.new(name='KeyLight', object_data=light_data)
    bpy.context.collection.objects.link(light_obj)
    light_obj.location = (2.0, -2.0, 3.0)

# Render settings
scene.render.resolution_x = 1280
scene.render.resolution_y = 720
scene.render.image_settings.file_format = 'FFMPEG'
scene.render.ffmpeg.format = 'MPEG4'
scene.render.ffmpeg.codec = 'H264'
scene.render.ffmpeg.constant_rate_factor = 'HIGH'
scene.render.ffmpeg.audio_codec = 'AAC'
scene.render.filepath = os.path.abspath(output_path)

print('Starting render...')
# Render animation
bpy.ops.render.render(animation=True)
print('Render finished.')
