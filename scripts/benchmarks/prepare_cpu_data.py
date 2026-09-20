"""Deterministic synthetic CPU workload; not a recognition accuracy dataset."""
import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2
import numpy as np


def sign_image(kind, size=160):
    image = np.full((size, size, 3), 235, np.uint8)
    center = size // 2
    if kind == 'speed_40':
        cv2.circle(image, (center, center), int(size*.45), (30, 30, 210), -1)
        cv2.circle(image, (center, center), int(size*.35), (250, 250, 250), -1)
        cv2.putText(image, '40', (int(size*.23), int(size*.65)),
                    cv2.FONT_HERSHEY_SIMPLEX, size/115, (25, 25, 25), max(1, size//35), cv2.LINE_AA)
    elif kind == 'warning':
        points = np.array([[center, 8], [8, size-12], [size-8, size-12]])
        cv2.fillPoly(image, [points], (30, 30, 210))
        points = np.array([[center, 30], [29, size-24], [size-29, size-24]])
        cv2.fillPoly(image, [points], (250, 250, 250))
        cv2.putText(image, '!', (center-12, size-35), cv2.FONT_HERSHEY_SIMPLEX,
                    1.8, (20, 20, 20), 4, cv2.LINE_AA)
    else:
        cv2.rectangle(image, (8, 8), (size-8, size-8), (180, 90, 25), -1)
        cv2.putText(image, 'P', (40, 125), cv2.FONT_HERSHEY_SIMPLEX, 3,
                    (255, 255, 255), 9, cv2.LINE_AA)
    return image


def prepare(output, seconds, fps):
    output.mkdir(parents=True, exist_ok=False)
    for directory in ('frames', 'crops', 'videos'):
        (output / directory).mkdir()
    rng = np.random.default_rng(20260919)
    kinds = ['speed_40', 'warning', 'parking']
    tiles = {kind: sign_image(kind) for kind in kinds}
    for kind, tile in tiles.items():
        for size in (32, 64, 128):
            cv2.imwrite(str(output/'crops'/f'{kind}_{size}.png'), cv2.resize(tile, (size, size)))
    annotations, clips = [], []
    for name, width, height, count in [('empty_720p',1280,720,0),
                                       ('sparse_720p',1280,720,2),
                                       ('dense_1080p',1920,1080,8)]:
        path = output/'videos'/f'{name}.mp4'
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'mp4v'), fps, (width,height))
        if not writer.isOpened():
            raise RuntimeError(f'Video encoder unavailable: {path}')
        texture = rng.integers(-8,9,(height,width,1),dtype=np.int16)
        base = np.full((height,width,3),(190,165,130),np.uint8)
        cv2.rectangle(base,(0,height//2),(width,height),(65,95,65),-1)
        cv2.fillPoly(base,[np.array([[width//2-50,height//2],[width//2+50,height//2],
                                     [width,height],[0,height]])],(75,75,78))
        base = np.clip(base.astype(np.int16)+texture,0,255).astype(np.uint8)
        try:
            for frame_index in range(seconds*fps):
                frame = base.copy()
                boxes=[]
                phase=(frame_index%(fps*3))/(fps*3)
                for i in range(count):
                    size=int(height*(.045+.06*phase))
                    x=int((.08+(i%4)*.25)*width)
                    y=int((.25+(i//4)*.30+.06*phase)*height)
                    kind=kinds[i%len(kinds)]
                    cv2.line(frame,(x+size//2,y+size),(x+size//2,min(height-1,y+size*3)),(150,150,150),3)
                    frame[y:y+size,x:x+size]=cv2.resize(tiles[kind],(size,size))
                    boxes.append({'synthetic_kind':kind,'xyxy':[x,y,x+size,y+size]})
                writer.write(frame)
                if frame_index%fps==0:
                    filename=f'frames/{name}_{frame_index:05d}.png'
                    if not cv2.imwrite(str(output/filename),frame):
                        raise RuntimeError(f'Cannot save {filename}')
                    annotations.append({'file':filename,'clip':name,'frame':frame_index,'objects':boxes})
        finally:
            writer.release()
        capture=cv2.VideoCapture(str(path));decoded=0
        while True:
            ok, image=capture.read()
            if not ok: break
            assert image.shape[:2]==(height,width)
            decoded+=1
        capture.release()
        if decoded!=seconds*fps: raise RuntimeError(f'Incomplete video {path}: {decoded}')
        clips.append({'file':f'videos/{name}.mp4','frames':decoded,'fps':fps,'width':width,'height':height})
    start=datetime(2026,1,1,tzinfo=timezone.utc)
    points=[]
    for i in range(seconds+1):
        stamp=(start+timedelta(seconds=i)).isoformat().replace('+00:00','Z')
        points.append(f'<trkpt lat="{53+i*.0001:.7f}" lon="27.0000000"><ele>200</ele><time>{stamp}</time></trkpt>')
    (output/'synthetic.gpx').write_text('<?xml version="1.0"?><gpx version="1.1" creator="Signer CPU fixture" xmlns="http://www.topografix.com/GPX/1/1"><trk><name>Artificial route</name><trkseg>'+''.join(points)+'</trkseg></trk></gpx>',encoding='utf-8')
    (output/'annotations.json').write_text(json.dumps(annotations,indent=2),encoding='utf-8')
    hashes={str(p.relative_to(output)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(output.rglob('*')) if p.is_file()}
    manifest={'version':1,'seed':20260919,'synthetic':True,'accuracy_evaluation':False,
              'opencv':cv2.__version__,'numpy':np.__version__,'clips':clips,
              'gpx_note':'Artificial route; each clip starts at GPX time zero. No embedded camera GPS.',
              'sha256':hashes}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(f'Prepared and decoded {len(clips)} clips, {len(annotations)} frames, 9 crops: {output}')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('benchmark_data/cpu_synthetic_v1'))
    parser.add_argument('--seconds',type=int,default=6)
    parser.add_argument('--fps',type=int,default=25)
    args=parser.parse_args()
    if args.seconds<1 or args.fps<1: parser.error('seconds and fps must be positive')
    prepare(args.output,args.seconds,args.fps)
