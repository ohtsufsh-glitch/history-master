#!/usr/bin/env python3
"""Generate static PR maps from the actual definitions and recorded real-input traces.
Requires developer-only matplotlib. Does not write app or fixture data.
"""
import json
from pathlib import Path
import subprocess
import os
os.environ.setdefault('MPLCONFIGDIR','/tmp/history-master-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/screenshots/runner-85-extension'
OUT.mkdir(parents=True,exist_ok=True)
js="""import {getStage} from './runner/stages.js';
console.log(JSON.stringify(['S05','S06'].flatMap(id=>[7,8].map(v=>getStage(id,v)))));"""
courses=json.loads(subprocess.check_output(['node','--input-type=module','-e',js],cwd=ROOT,text=True))
(OUT/'courses.json').write_text(json.dumps(courses,ensure_ascii=False,indent=2)+'\n')

def paint(ax,s,zoom=False):
    ax.set_title(f"{s['stageId']} v{s['stageVersion']} / goal {s['goalDistance']}px",loc='left')
    ax.set_ylim(-50,430);ax.set_ylabel('Height (px)');ax.grid(axis='x',alpha=.2)
    ax.axhline(0,color='#377052',lw=2)
    for h in s.get('holes',[]):ax.add_patch(Rectangle((h['start'],-45),h['end']-h['start'],45,color='#344e67'))
    cr={c['id']:c['seconds'] for c in s['crumbling']}
    for i,e in enumerate(s['course']):
        x=e['at']*200+822;kind=e['type'];h=e.get('height',0)
        if kind=='platform':
            ax.add_patch(Rectangle((x-e['width']/2,h-16),e['width'],16,color='#b47b3c' if i in cr else '#538c61'))
            if zoom and x>=(7000 if s['stageId']=='S05' else 7700):ax.text(x,h+6,f"{x:g}\nh{h} / {cr.get(i,'-')}s",ha='center',fontsize=8)
        elif kind=='wall':ax.add_patch(Rectangle((x-e['width']/2,0),e['width'],h,color='#9366b3'))
        elif kind=='obstacle':ax.plot(x,20,'^',color='#c63232',ms=5)
        elif kind=='star':ax.plot(x,h+43,'*',color='#e4ae00',ms=10)
    for b in s.get('birds',[]):ax.plot(b['x']/1.6,b['height'],'<',color='#375fbb',ms=5)
    for sp in s.get('spikes',[]):
        ax.plot([sp['x']]*2,[sp['height']-sp['amplitude'],sp['height']+sp['amplitude']],color='#c8313d',lw=3)
        ax.scatter([sp['x']],[sp['height']],s=22,color='#c8313d')
    ax.axvline(s['goalDistance'],color='#317c40',ls='--',lw=2)
    ax.set_xlim((6800 if s['stageId']=='S05' else 7400) if zoom else 0,s['goalDistance']+80)
    ax.set_xlabel('World X (px); birds shown at shiba encounter X; red lines = spike motion')

for id in ['S05','S06']:
    fig,axes=plt.subplots(2,1,figsize=(18,7),layout='constrained')
    for ax,s in zip(axes,[s for s in courses if s['stageId']==id]):paint(ax,s)
    fig.suptitle('Green = platform | brown = crumbling | purple = electric wall | gold = star | blue = incoming bird')
    for ext in ['png','svg']:fig.savefig(OUT/f'{id.lower()}-comparison.{ext}',dpi=140)
    plt.close(fig)
fig,axes=plt.subplots(2,1,figsize=(15,8),layout='constrained')
for ax,s in zip(axes,[s for s in courses if s['stageVersion']==8]):paint(ax,s,True)
for ext in ['png','svg']:fig.savefig(OUT/f'extension-detail.{ext}',dpi=140)
plt.close(fig)
route_file=OUT/'route-comparison.json'
if route_file.exists():
    routes=json.loads(route_file.read_text())
    fig,axes=plt.subplots(2,1,figsize=(15,8),layout='constrained')
    for ax,s in zip(axes,[s for s in courses if s['stageVersion']==8]):
        paint(ax,s,True)
        for r in [r for r in routes if r['id']==s['stageId']]:
            ax.plot([p['x'] for p in r['points']],[p['height'] for p in r['points']],
                    color='#167b85' if r['route']=='good' else '#e24f32',label=r['route'],lw=2)
        ax.legend(loc='upper left')
    for ext in ['png','svg']:fig.savefig(OUT/f'route-comparison.{ext}',dpi=140)
    plt.close(fig)
# Matplotlib emits trailing blanks in SVG paths; keep generated review diffs clean.
for svg in OUT.glob('*.svg'):
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
