"""#137: wall-only paint bounds, baseline physics, real iframe review captures.

Uses ephemeral synthetic records. Baseline is the merged PR #140 main.
RUNNER_WALL_REVIEW overrides the screenshot directory (default /tmp/runner-137-wall).
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import unittest

import runner_canvas_test as canvas
import runner_session_test as session
from runner_spike_design_test import TRACE, PLANS

ROOT = Path(__file__).resolve().parents[1]
BASE_SHA = 'd2d2f431afc5f467a3cc1def8e671558b6522eca'
EXPORT = '\nexport {drawWall,drawObstacle,renderScene};\n'


class RunnerWallDesignTest(unittest.TestCase):
    setUpClass = classmethod(session.RunnerSessionTest.setUpClass.__func__)
    tearDownClass = classmethod(session.RunnerSessionTest.tearDownClass.__func__)
    tearDown = session.RunnerSessionTest.tearDown

    def setUp(self):
        session.RunnerSessionTest.setUp(self)
        self.out = Path(os.environ.get('RUNNER_WALL_REVIEW', '/tmp/runner-137-wall'))
        self.out.mkdir(parents=True, exist_ok=True)
        self.before = subprocess.check_output(['git', 'show', f'{BASE_SHA}:runner/game.js'], cwd=ROOT, text=True)
        after = (ROOT / 'runner/game.js').read_text()
        self.page.route('**/runner/game.js*', lambda r: r.fulfill(content_type='text/javascript',
            body=(self.before if 'wall-before' in r.request.url else after) + EXPORT))
        self.context.add_init_script('if(window.parent!==window){' + canvas.MANUAL_FRAMES + '(' + canvas.ISOLATION_GUARD + ')();}')
        self.page.evaluate("navigate('runner','test')")
        self.page.frame_locator('iframe').locator('#runner-toggle').wait_for()
        self.frame = self.page.frames[1]
        self.frame.evaluate("""async()=>{
          window.after=await import(document.querySelector('script[type=module]').src);
          window.before=await import('./game.js?wall-before');
          window.image=async src=>{const i=new Image();i.src=src;await i.decode();return i;};
          window.rock=await image(after.OBSTACLE_IMAGE.src);
          window.characters={shiba:{idle:await image('./assets/shiba/idle.webp')}};
          window.reviewState=()=>{const s=after.createRunnerState([]);s.mode='paused';
            s.objects=[{type:'platform',id:100,x:325,width:130,height:90},
              {type:'platform',id:101,x:500,width:130,height:90},
              {type:'obstacle',x:665},{type:'wall',x:835,width:72,height:100}];
            s.crumbling=[{id:101,seconds:.8}];return s;};
          window.reviewPaint=key=>{const c=document.querySelector('#runner-canvas');
            window[key].renderScene(c.getContext('2d'),c,reviewState(),characters,rock);};
          await runnerClock.settle();runnerClock.step(0);
        }""")

    def test_wall_paint_stays_in_every_course_rectangle_and_other_objects_match(self):
        checks = self.frame.evaluate("""()=>{
          const sizes=new Map();
          for(const stage of after.STAGES)for(let v=1;v<=stage.stageVersion;v++)
            for(const o of after.getStage(stage.stageId,v).course)if(o.type==='wall')
              sizes.set(o.width+':'+o.height,[o.width,o.height]);
          const rows=[];
          for(const [w,h] of sizes.values()){
            const c=document.createElement('canvas');c.width=w+20;c.height=h+20;
            const ctx=c.getContext('2d');ctx.translate(10,10-(470-h));
            const wall={x:w/2,width:w,height:h};const saved=ctx.getTransform();
            after.drawWall(ctx,wall);
            const p=ctx.getImageData(0,0,c.width,c.height).data;
            let outside=0,holes=0,yellow=0,cyan=0;
            for(let y=0;y<c.height;y++)for(let x=0;x<c.width;x++){
              const n=(y*c.width+x)*4,inside=x>=10&&x<w+10&&y>=10&&y<h+10;
              if(!inside&&p[n+3])outside++;if(inside&&p[n+3]!==255)holes++;
              if(inside&&p[n]>240&&p[n+1]>180&&p[n+2]<120)yellow++;
              if(inside&&p[n]<230&&p[n+1]>230&&p[n+2]>240)cyan++;
            }
            const restored=ctx.getTransform().toString()===saved.toString();
            rows.push({w,h,outside,holes,yellow,cyan,restored});
          }
          const render=(m,type)=>{const c=document.createElement('canvas');c.width=960;c.height=540;
            const s=reviewState();s.objects=s.objects.filter(o=>o.type===type);
            m.renderScene(c.getContext('2d'),c,s,characters,rock);return c.toDataURL();};
          return {rows,otherObjectsMatch:['platform','obstacle'].every(t=>render(before,t)===render(after,t))};
        }""")
        self.assertGreater(len(checks['rows']), 5)
        for row in checks['rows']:
            with self.subTest(size=(row['w'], row['h'])):
                self.assertEqual((row['outside'], row['holes']), (0, 0))
                self.assertTrue(row['restored'])
                self.assertGreater(row['yellow'], 50)
                self.assertGreater(row['cyan'], 20)
        self.assertTrue(checks['otherObjectsMatch'])
        self.frame.evaluate("""()=>{const c=document.createElement('canvas');c.id='review-sizes';
          c.width=1300;c.height=580;document.body.append(c);const x=c.getContext('2d');
          x.fillStyle='#e8f2ec';x.fillRect(0,0,1300,580);x.font='22px sans-serif';
          for(const [cx,base,w,h] of [[55,260,40,180],[180,260,96,220],[440,260,340,80],[650,540,1240,90]]){
            x.fillStyle='#202337';x.fillText(w+' x '+h,cx-w/2,base-h-12);
            x.save();x.translate(0,base-470);after.drawWall(x,{x:cx,width:w,height:h});x.restore();
          }
        }""")
        data=self.frame.evaluate("document.querySelector('#review-sizes').toDataURL().split(',')[1]")
        (self.out/'wall-sizes.png').write_bytes(base64.b64decode(data))
        (self.out/'paint-metrics.json').write_text(json.dumps(checks, indent=2)+'\n')

    def test_published_courses_all_frame_snapshots_and_refresh_rates_match(self):
        results = {}
        for key in ['before','after']:
            self.frame.evaluate('key=>window.runnerModel=window[key]',key)
            actual = self.frame.evaluate(TRACE, PLANS)
            for row in actual['rows']:
                row['frames'] = len(row['trace'])
                row['sha256'] = hashlib.sha256('\n'.join(row.pop('trace')).encode()).hexdigest()
                self.assertEqual((row['reason'], row['score'], row['lives']) if row['path']=='clear'
                    else (row['reason'],row['lives']), ('clear',100,2) if row['path']=='clear' else ('collision',0))
            results[key] = actual
        self.assertEqual(results['before'],results['after'])
        for id in ['S01','S05','S06']:
            for path in ['clear','hit']:
                rows=[r for r in results['after']['rows'] if r['id']==id and r['path']==path]
                self.assertEqual(len({(r['reason'],r['score'],r['lives']) for r in rows}),1)
        (self.out/'physics-results.json').write_text(json.dumps({'source':BASE_SHA,**results},indent=2)+'\n')

    def scroll_to_game(self):
        box=self.frame.locator('#runner-canvas').bounding_box()
        self.page.evaluate("""y=>{const h=document.querySelector('main > header');
          const inset=getComputedStyle(h).position==='sticky'?h.getBoundingClientRect().height:0;
          scrollTo(0,scrollY+y-inset-16);}""",box['y'])

    def test_real_iframe_comparisons_gameplay_touch_rotation_and_overlay(self):
        metrics=[]
        self.assertTrue(self.page.evaluate("formalRunner.select('S05','shiba')"))
        for w,h in [(390,844),(844,390),(1024,768)]:
            self.page.set_viewport_size(dict(width=w,height=h))
            self.frame.evaluate('async()=>{await runnerClock.settle();runnerClock.step(0);}')
            self.scroll_to_game()
            for key in ['before','after']:
                self.frame.evaluate('key=>reviewPaint(key)',key)
                c=self.frame.locator('#runner-canvas');box=c.bounding_box()
                metrics.append(dict(viewport=[w,h],key=key,canvas=box,wallCSSWidth=72*box['width']/960))
                c.screenshot(path=str(self.out/f'{key}-{w}x{h}-canvas.png'))
            f=self.page.frame_locator('iframe');f.locator('#runner-toggle').click()
            self.page.wait_for_function("formalRunner.session?.view.state.mode==='running'")
            f.locator('#runner-jump').dispatch_event('pointerdown',dict(pointerType='touch',isPrimary=True,button=0))
            self.assertIsNone(self.page.evaluate('formalRunner.session.view.state.supportId'))
            f.locator('#runner-toggle').click()
            # Actual S05 route; use the same representative successful jump inputs.
            self.page.evaluate("""async plans=>{
              const c=formalRunner.session;let n=plans.filter(t=>t<c.view.state.elapsed).length;
              await c.resume();while(c.view.state.elapsed<5.5){
                if(n<plans.length&&c.view.state.elapsed+1e-9>=plans[n]){await c.jump();n++;}
                await c.advance(Math.min(1/60,5.5-c.view.state.elapsed));
              }await c.pause();
            }""",PLANS['S05'])
            self.assertEqual(self.page.evaluate('formalRunner.session.view.state.mode'),'paused')
            self.assertTrue(self.page.evaluate("formalRunner.session.view.state.objects.some(o=>o.type==='wall')"))
            self.frame.evaluate('()=>runnerClock.step(0)');self.scroll_to_game()
            self.page.screenshot(path=str(self.out/f'game-s05-{w}x{h}.png'))
            self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),w)
        self.frame.evaluate("""()=>{const c=document.querySelector('#runner-canvas');c.width=960;c.height=540;
          reviewPaint('after');const ctx=c.getContext('2d');
          const wall=reviewState().objects.find(o=>o.type==='wall'),b=after.wallBounds(wall);
          ctx.strokeStyle='#ff3ad4';ctx.lineWidth=2;ctx.setLineDash([8,5]);ctx.strokeRect(b.left,b.top,b.width,b.height);
        }""")
        self.frame.locator('#runner-canvas').screenshot(path=str(self.out/'collision-overlay.png'))
        (self.out/'canvas-metrics.json').write_text(json.dumps(metrics,indent=2)+'\n')
