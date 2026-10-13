"""Test a reviewed four-vehicle scene with PX4 without rewriting runtime assets."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import traceback
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

from .flight import run


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(scene, package, vehicle_config, output):
    scene,package,vehicle_config=map(lambda p:Path(p).resolve(),(scene,package,vehicle_config))
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    cfg=json.loads(vehicle_config.read_text())
    info=json.loads((package/'model_info.json').read_text())
    if info['configuration']!=cfg or cfg.get('model')!='cad_v2':
        raise ValueError('Reviewed Ver2 runtime package/configuration mismatch')
    root=ET.parse(scene).getroot()
    # Reserve aircraft group5 for existing range-sensor self/parked-body masking.
    # This generated copy changes display groups only, never source collisions.
    for index in range(1,5):
        body=next((b for b in root.findall('.//body') if b.get('name')==f'drone_{index}'),None)
        if body is None:raise ValueError('Expected four independently named vehicles')
        for geom in body.findall('.//geom'):geom.set('group','5')
    compiler=root.find('compiler')
    for asset in root.findall('asset/*'):
        if asset.get('file'):
            directory='' if compiler is None else compiler.get(
                'meshdir' if asset.tag=='mesh' else 'texturedir',compiler.get('assetdir',''))
            asset.set('file',str((scene.parent/directory/asset.get('file')).resolve()))
    if compiler is not None:
        for key in ('meshdir','texturedir','assetdir'):compiler.attrib.pop(key,None)
    destination=output/'scene.xml';ET.ElementTree(root).write(destination,encoding='unicode')
    model=mujoco.MjModel.from_xml_path(str(destination))
    dynamic=mujoco.MjModel.from_xml_path(str(package/'dynamic/model.xml'))
    for index in range(1,5):
        body=model.body(f'drone_{index}').id
        original=dynamic.body('rm27_drone').id
        np.testing.assert_allclose(model.body_mass[body],dynamic.body_mass[original],atol=1e-12,rtol=0)
        np.testing.assert_allclose(model.body_inertia[body],dynamic.body_inertia[original],atol=1e-12,rtol=0)
        assert sum(model.geom_bodyid==body)==sum(dynamic.geom_bodyid==original)
        for motor in range(4):
            a=model.actuator(f'drone_{index}_motor_{motor}').id
            b=dynamic.actuator(f'rm27_drone_motor_{motor}').id
            for field in ('actuator_gear','actuator_ctrlrange','actuator_dynprm'):
                np.testing.assert_allclose(getattr(model,field)[a],getattr(dynamic,field)[b],atol=1e-12,rtol=0)
            np.testing.assert_allclose(model.site_pos[model.site(f'drone_{index}_rotor_{motor}').id],
                dynamic.site_pos[dynamic.site(f'rm27_drone_rotor_{motor}').id],atol=1e-12,rtol=0)
    e=cfg['engineering_estimates']
    profile=dict(schema_version=1,status='engineering_estimate',evidence=[],
        frame='body axes; principal inertia; COM at model origin',
        values=dict(mass_kg=cfg['mass_kg'],inertia_kg_m2=info['inertia_kg_m2_assumed'],
                    max_rotor_thrust_N=e['max_rotor_thrust_N'],motor_time_constant_s=e['motor_time_constant_s'],
                    yaw_torque_per_thrust_m=e['yaw_torque_per_thrust_m']),
        limitations=cfg['limitations'])
    (output/'dynamics.json').write_text(json.dumps(profile,indent=2)+'\n')
    files=[scene,vehicle_config,package/'model_info.json',package/'dynamic/model.xml',
           package/'README.md',Path(__file__)]
    files.extend(Path(a.get('file')) for a in root.findall('asset/*') if a.get('file'))
    manifest=dict(source_scene=str(scene),package=str(package),command=sys.argv,
        input_sha256={str(p):digest(p) for p in files},scene_sha256=digest(destination),
        aircraft_display_group=5,model=cfg['name'],model_rest_height_m=cfg['com_height_above_bottom_m_assumed'],
        source_assets_modified=False,scope='Model interface check; geometry and dynamics preserved, no hardware calibration')
    (output/'inputs.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return destination,output/'dynamics.json'


def execute(scene,package,vehicle_config,output,*,instance=70,profile='ekf',view=False,speedup=None):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    result=dict(passed=False,autopilot='px4',firmware='v1.17.0',
        run_type=('live-view' if view else 'headless')+' closed-loop SITL',
        scope='Ver2 short takeoff/hover/translate/return/land probe; no full contact or visual qualification')
    try:
        prepared,dynamics=prepare(scene,package,vehicle_config,output/'plant')
        run(prepared,output/'flight',instance,dynamics=dynamics,profile=profile,view=view,speedup=speedup)
        task=json.loads((output/'flight/summary.json').read_text())
        result.update(passed=task.get('passed') is True,task=task)
    except (Exception,KeyboardInterrupt) as exc:
        result['failure']=f'{type(exc).__name__}: {exc}'
        (output/'failure.txt').write_text(traceback.format_exc())
    (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2));return 0 if result['passed'] else 1


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('scene',type=Path)
    p.add_argument('--package',type=Path,required=True)
    p.add_argument('--vehicle-config',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--instance',type=int,default=70)
    p.add_argument('--profile',choices=('ekf','flow','mtf'),default='ekf')
    p.add_argument('--view',action='store_true');p.add_argument('--speedup',type=float)
    a=p.parse_args();return execute(a.scene,a.package,a.vehicle_config,a.output,instance=a.instance,
        profile=a.profile,view=a.view,speedup=a.speedup)


if __name__=='__main__':raise SystemExit(main())
