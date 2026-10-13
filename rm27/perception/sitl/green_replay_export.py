"""Re-render timestamped RGB inputs from recorded MuJoCo states for green replay.

This is offline reconstruction, not the original delivered camera pixels.
Physics state is consumed by the exporter only, never by the detector.
"""
import argparse
import hashlib
import json
from pathlib import Path

import cv2
import mujoco
import numpy as np

from .mujoco_camera import MujocoCamera
from ...telemetry.recording import open_recording


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def export(run, output, camera_config, start=56., duration=8.):
    run, output, camera_config = map(lambda p: Path(p).resolve(), (run, output, camera_config))
    if not np.isfinite([start, duration]).all() or start < 0 or duration <= 0:
        raise ValueError('finite nonnegative start and positive duration required')
    metadata = json.loads((run / 'metadata.json').read_text())
    scene = Path(metadata['scene'])
    if sha(scene) != metadata['scene_sha256']:
        raise ValueError('recorded scene changed')
    asset_hashes = {}
    audit_path = run / 'route_audit.json'
    if audit_path.is_file():
        audit = json.loads(audit_path.read_text())
        if audit.get('scene_sha256') != metadata['scene_sha256']:
            raise ValueError('recorded asset audit scene mismatch')
        asset_hashes = audit['asset_sha256']
        for path, expected in asset_hashes.items():
            if sha(path) != expected: raise ValueError('recorded scene asset changed: ' + path)
    config = json.loads(camera_config.read_text())
    keys = ('width', 'height', 'fovy_deg', 'body_name', 'offset_body', 'forward_body', 'up_body')
    if config['camera_hz'] <= 0:
        raise ValueError('positive camera frequency required')
    output.mkdir(parents=True, exist_ok=False)
    images = output / 'images'; images.mkdir()
    model = mujoco.MjModel.from_xml_path(str(scene)); data = mujoco.MjData(model)
    frames = []; next_time = start; last = -1.
    with MujocoCamera(model, **{k: config[k] for k in keys}) as camera, open_recording(run / 'frames.jsonl') as source:
        for line in source:
            row = json.loads(line); time = float(row['timestamp'])
            if time <= last:
                raise ValueError('nonmonotonic recorded clock')
            last = time
            if time + 1e-9 >= start + duration: break
            if time + 1e-9 < next_time: continue
            data.qpos[:] = row['all_qpos']; data.qvel[:] = row['all_qvel']
            frame = camera.capture(data, round(time * 1e6))
            filename = f'images/{len(frames):06d}.png'
            if not cv2.imwrite(str(output / filename), cv2.cvtColor(frame.image_rgb, cv2.COLOR_RGB2BGR)):
                raise RuntimeError('RGB image save failed')
            frames.append(dict(sequence=len(frames), timestamp_us=frame.timestamp_us,
                               image=filename, sha256=sha(output / filename)))
            next_time += 1. / config['camera_hz']
    if not frames: raise ValueError('no recorded frames in requested interval')
    manifest = dict(schema_version=1, pixel_format='RGB888', clock_domain='mujoco_simulation',
                    nominal_fps=config['camera_hz'], width=config['width'], height=config['height'],
                    frames=frames, reconstruction='Recorded qpos/qvel rendered with configured camera; original delivered RGB not archived',
                    detector_truth_input=False, original_run=str(run), scene_sha256=sha(scene),
                    source_assets_verified=bool(asset_hashes), source_asset_sha256=asset_hashes,
                    metadata_sha256=sha(run / 'metadata.json'), camera_configuration=config,
                    camera_configuration_sha256=sha(camera_config), recording_sha256=sha(run / 'frames.jsonl'))
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    summary = dict(passed=True, run_type='recorded-state RGB reconstruction', frames=len(frames),
                   start_time_us=frames[0]['timestamp_us'], end_time_us=frames[-1]['timestamp_us'],
                   manifest_sha256=sha(output / 'manifest.json'), camera_configuration_sha256=sha(camera_config))
    summary['source_assets_verified'] = bool(asset_hashes)
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--start', type=float, default=56.)
    parser.add_argument('--duration', type=float, default=8.)
    a = parser.parse_args(); export(a.run, a.output, a.config, a.start, a.duration)


if __name__ == '__main__': main()
