"""#137①: image/404 geometry, exact main trajectories and actual iframe review captures.

Only public original sprites and ephemeral synthetic play records are used.
RUNNER_REVIEW_IMAGES overrides the capture directory; no production debug API is added.
"""
import hashlib
import json
import os
from pathlib import Path
import unittest

import runner_canvas_test as canvas
import runner_session_test as session
from runner_balance_cases import INPUTS
from runner_density_test import INPUTS as SIMPLE

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'docs/screenshots/runner-137-spike-rock'
BASE = json.loads((ROOT / 'tests/fixtures/runner137-spike-baseline.json').read_text())
PLANS = {**INPUTS, 'S01': SIMPLE['S01']}

# This same trace was captured from the original main module, not this edited module.
TRACE = """plans=>{const m=runnerModel,rows=[];
 for(const id of ['S01','S05','S06'])for(const hz of [30,60,120])for(const path of ['clear','hit']){
 const s=m.createRunnerState(m.STAGES.find(s=>s.stageId===id));s.mode='running';let n=0;const trace=[];
 while(s.mode==='running'){
 if(path==='clear'&&n<plans[id].length&&s.elapsed+1e-9>=plans[id][n]){m.startJump(s);n++;}
 m.updateRunner(s,1/hz);trace.push(JSON.stringify(m.snapshotRunner(s)));
 }rows.push({id,hz,path,reason:s.reason,score:s.score,lives:s.lives,distance:s.distance,trace});
 }return {geometry:{...m.OBSTACLE_IMAGE,src:null},collision:m.COLLISION,rows};}"""


class RunnerSpikePhysicsTest(unittest.TestCase):
    setUpClass = classmethod(canvas.RunnerCanvasTest.setUpClass.__func__)
    tearDownClass = classmethod(canvas.RunnerCanvasTest.tearDownClass.__func__)
    open_runner = canvas.RunnerCanvasTest.open_runner
    manual_runner = canvas.RunnerCanvasTest.manual_runner
    model_runner = canvas.RunnerCanvasTest.model_runner
    assert_geometry = canvas.RunnerCanvasTest.assert_geometry

    def test_original_main_geometry_and_all_frame_snapshots_match(self):
        p, _, _ = self.model_runner()
        actual = p.evaluate(TRACE, PLANS)
        for row in actual['rows']:
            row['frames'] = len(row['trace'])
            row['sha256'] = hashlib.sha256('\n'.join(row.pop('trace')).encode()).hexdigest()
            if row['path'] == 'clear':
                self.assertEqual((row['reason'], row['score'], row['lives']), ('clear', 100, 2))
            else:
                self.assertEqual((row['reason'], row['lives']), ('collision', 0))
        self.assertEqual(actual, {k: v for k, v in BASE.items() if k != 'source'})


class RunnerSpikeDesignTest(unittest.TestCase):
    setUpClass = classmethod(session.RunnerSessionTest.setUpClass.__func__)
    tearDownClass = classmethod(session.RunnerSessionTest.tearDownClass.__func__)
    tearDown = session.RunnerSessionTest.tearDown

    def setUp(self):
        session.RunnerSessionTest.setUp(self)
        self.out = Path(os.environ.get('RUNNER_REVIEW_IMAGES', '/tmp/runner-137-review'))
        self.out.mkdir(parents=True, exist_ok=True)
        # Instrument the served test copy only; the app has no new export/debug state.
        script = (ROOT / 'runner/game.js').read_text() + '\nexport {drawObstacle,renderScene};\n'
        self.page.route('**/runner/game.js*', lambda r: r.fulfill(content_type='text/javascript', body=script))
        self.context.add_init_script('if(window.parent!==window){' + canvas.MANUAL_FRAMES + '(' + canvas.ISOLATION_GUARD + ')();}')
        self.page.evaluate("navigate('runner','test')")
        self.page.frame_locator('iframe').locator('#runner-toggle').wait_for()
        self.frame = self.page.frames[1]
        self.frame.evaluate("""async()=>{
          window.paint=await import(document.querySelector('script[type=module]').src);
          window.reviewImage=async src=>{const i=new Image();i.src=src;await i.decode();return i;};
          window.reviewCharacters={shiba:{idle:await reviewImage('./assets/shiba/idle.webp')}};
          window.reviewAssets={};
          for(const name of ['current','design-a','design-b'])reviewAssets[name]=await reviewImage('../docs/screenshots/runner-137-spike-rock/'+name+'.webp');
          reviewAssets.final=await reviewImage(paint.OBSTACLE_IMAGE.src);
          window.reviewState=()=>{const s=paint.createRunnerState([]);s.mode='paused';
            s.objects=[{type:'obstacle',x:335},{type:'platform',id:100,x:490,width:130,height:80},
              {type:'platform',id:101,x:665,width:130,height:80},{type:'wall',x:840,width:72,height:100}];
            s.crumbling=[{id:101,seconds:.8}];return s;};
          window.reviewPaint=(key='final')=>{
            const c=document.querySelector('#runner-canvas'),s=reviewState();
            paint.renderScene(c.getContext('2d'),c,s,reviewCharacters,reviewAssets[key]);
          };
          await runnerClock.settle();runnerClock.step(0);
        }""")

    def test_alpha_contact_collision_coverage_and_cache_identifier(self):
        data = self.frame.evaluate("""()=>{
          const pixels=i=>{const c=document.createElement('canvas');c.width=640;c.height=466;
            const x=c.getContext('2d');x.drawImage(i,0,0);return x.getImageData(0,0,640,466).data;};
          const old=pixels(reviewAssets.current),rows=[];
          for(const key of ['design-a','design-b','final']){
            const i=reviewAssets[key],p=pixels(i);let different=0,red=0,minX=640,minY=466,maxX=-1,maxY=-1;
            for(let y=0;y<466;y++)for(let x=0;x<640;x++){
              const n=(y*640+x)*4;if(p[n+3]!==old[n+3])different++;
              if(p[n+3]){minX=Math.min(minX,x);maxX=Math.max(maxX,x);minY=Math.min(minY,y);maxY=Math.max(maxY,y);}
              if(p[n]>180&&p[n+1]<110&&p[n+2]<100&&p[n+3]>240)red++;
            }
            const regions=paint.COLLISION.obstacleRegions.map(r=>{
              let min=255;for(let y=464+r.top*8;y<464+r.bottom*8;y++)
                for(let x=320+r.left*8;x<320+r.right*8;x++)min=Math.min(min,p[(y*640+x)*4+3]);return min;});
            rows.push({key,size:[i.naturalWidth,i.naturalHeight],different,bounds:[minX,minY,maxX+1,maxY+1],regions,red});
          }return {rows,src:reviewAssets.final.src};
        }""")
        for r in data['rows']:
            self.assertEqual(r['size'], [640, 466])
            self.assertEqual(r['bounds'], [1, 3, 638, 464])
            self.assertEqual(r['different'], 0)
            self.assertGreaterEqual(min(r['regions']), 252)
            self.assertGreater(r['red'], 20000)
        self.assertTrue(data['src'].endswith('spike-rock.webp?v=1.7.53'))
        (self.out / 'image-metrics.json').write_text(json.dumps(data['rows'], indent=2) + '\n')

    def scroll_to_game(self):
        self.page.evaluate("""()=>{const host=document.querySelector('#runner-frame-host'),header=document.querySelector('main > header');
          scrollTo(0,scrollY+host.getBoundingClientRect().top-header.getBoundingClientRect().bottom-8);}""")

    def test_actual_iframe_sizes_comparisons_and_touch_rotation(self):
        sizes=[]
        for w,h in [(390,844),(844,390),(1024,768)]:
            self.page.set_viewport_size(dict(width=w,height=h))
            self.frame.evaluate('async()=>{await runnerClock.settle();runnerClock.step(0);}')
            self.scroll_to_game()
            for key in ['current','design-a','design-b','final']:
                self.frame.evaluate('key=>reviewPaint(key)', key)
                c=self.frame.locator('#runner-canvas')
                box=c.bounding_box();sizes.append(dict(viewport=[w,h],key=key,canvas=box,rockCSSWidth=box['width']/12))
                c.screenshot(path=str(self.out / f'{key}-{w}x{h}-canvas.png'))
            self.page.screenshot(path=str(self.out / f'iphone-{w}x{h}.png' if w!=1024 else self.out / 'ipad-1024x768.png'))
            # Normal game controls still operate after resize, using the real paid-play bridge.
            f=self.page.frame_locator('iframe')
            f.locator('#runner-toggle').click()
            self.page.wait_for_function("formalRunner.session?.view.state.mode==='running'")
            f.locator('#runner-jump').dispatch_event('pointerdown',dict(pointerType='touch',isPrimary=True,button=0))
            self.assertIsNone(self.page.evaluate('formalRunner.session.view.state.supportId'))
            f.locator('#runner-toggle').click()
            self.assertEqual(self.page.evaluate('formalRunner.session.view.state.mode'), 'paused')
            self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),w)
            self.page.evaluate("async()=>{const c=formalRunner.session;await c.resume();while(c.view.state.elapsed<3.25)await c.advance(Math.min(.05,3.25-c.view.state.elapsed));await c.pause();}")
            self.frame.evaluate('()=>runnerClock.step(0)')
            self.scroll_to_game()
            self.page.screenshot(path=str(self.out/f'game-s01-{w}x{h}.png'))
        (self.out / 'canvas-metrics.json').write_text(json.dumps(sizes,indent=2)+'\n')

    def test_404_fallback_has_opaque_regions_red_tips_and_same_physics(self):
        self.page.set_viewport_size(dict(width=390,height=844))
        self.page.route('**/runner/assets/spike-rock.webp*', lambda r: r.fulfill(status=404, body='missing'))
        # Regenerate the actual iframe so its own obstacleImage goes through the 404 handler.
        self.page.reload();self.page.wait_for_function("appReady")
        self.page.evaluate("navigate('runner','test')")
        self.page.frame_locator('iframe').locator('#runner-toggle').wait_for()
        frame=self.page.frames[1]
        frame.wait_for_function("runnerImages.some(i=>i.src.includes('spike-rock')&&i.complete&&!i.naturalWidth)")
        frame.evaluate("""async()=>{window.paint=await import(document.querySelector('script[type=module]').src);
          await runnerClock.settle();runnerClock.step(0);runnerClock.advance(3500,60); }""")
        # Draw the production fallback in the real Canvas, with review-only sample objects.
        frame.evaluate("""async()=>{const i=new Image();i.src='./assets/shiba/idle.webp';await i.decode();const c=document.querySelector('#runner-canvas'),s=paint.createRunnerState([]);
          s.mode='paused';s.objects=[{type:'obstacle',x:335}];paint.renderScene(c.getContext('2d'),c,s,{shiba:{idle:i}},null);}""")
        frame.locator('#runner-canvas').screenshot(path=str(self.out/'fallback-390x844.png'))
        checks=frame.evaluate("""()=>{
          const c=document.createElement('canvas');c.width=640;c.height=466;const ctx=c.getContext('2d');
          ctx.scale(8,8);ctx.translate(-280,-412);paint.drawObstacle(ctx,{x:320},null);
          const p=ctx.getImageData(0,0,640,466).data;
          const minima=paint.COLLISION.obstacleRegions.map(r=>{
            let min=255;for(let y=464+r.top*8;y<464+r.bottom*8;y++)for(let x=320+r.left*8;x<320+r.right*8;x++)min=Math.min(min,p[(y*640+x)*4+3]);return min;});
          const tips=[[320,80],[128,180],[512,180]].map(([x,y])=>Array.from(p.slice((y*640+x)*4,(y*640+x)*4+4)));
          return {minima,tips};
        }""")
        self.assertGreaterEqual(min(checks['minima']),252,checks)
        for red,green,blue,alpha in checks['tips']:
            self.assertGreater(red,180);self.assertLess(green,170);self.assertLess(blue,90);self.assertEqual(alpha,255)
        f=self.page.frame_locator('iframe');f.locator('#runner-toggle').click()
        self.page.wait_for_function("formalRunner.session?.view.state.mode==='running'")
        f.locator('#runner-jump').dispatch_event('pointerdown',dict(pointerType='touch',isPrimary=True,button=0))
        self.assertIsNone(self.page.evaluate('formalRunner.session.view.state.supportId'))
        self.page.evaluate("async()=>{while(formalRunner.session?.view.state.mode==='running')await formalRunner.bridge.advance(.05);}")
        self.assertEqual(self.page.evaluate('formalRunner.session.view.state.lives'),0)
        self.assertEqual(self.page.evaluate('formalRunner.session.view.savedPlay.result.reason'),'gameover')
