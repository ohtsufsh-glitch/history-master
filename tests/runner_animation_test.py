"""Issue #104: shared animation, local browser and synthetic states only."""
import unittest
import runner_canvas_test as canvas
import runner_character_ui_test as ui

IDS = ('shiba', 'sloth', 'goldfish', 'salamander', 'secret_yuniko')

class RunnerAnimationTest(unittest.TestCase):
    setUpClass = classmethod(canvas.RunnerCanvasTest.setUpClass.__func__)
    tearDownClass = classmethod(canvas.RunnerCanvasTest.tearDownClass.__func__)
    assert_geometry = canvas.RunnerCanvasTest.assert_geometry
    manual_runner = canvas.RunnerCanvasTest.manual_runner
    model_runner = canvas.RunnerCanvasTest.model_runner
    open_runner = canvas.RunnerCanvasTest.open_runner
    preview_runner = ui.RunnerCharacterUITest.preview_runner
    settle = ui.RunnerCharacterUITest.settle
    select_character = ui.RunnerCharacterUITest.select_character

    def test_assets(self):
        paths=[]
        for id in IDS[1:]:
            files = list((canvas.ROOT / 'runner/assets' / id).glob('*'))
            self.assertEqual(len(files), 9)
            self.assertEqual({p.stem for p in files}, set(canvas.SHIBA_FRAMES))
            for path in files:
                header=path.read_bytes()[:12]
                self.assertEqual((header[:4],header[8:]),(b'RIFF',b'WEBP'))
                paths.append('./assets/'+id+'/'+path.name)
        page, errors, _ = self.model_runner()
        rows=page.evaluate("""async paths=>Promise.all(paths.map(src=>new Promise((resolve,reject)=>{
          const image=new Image();image.onerror=reject;image.onload=()=>{
            const c=document.createElement('canvas');c.width=c.height=512;
            const ctx=c.getContext('2d');ctx.drawImage(image,0,0);
            resolve([image.naturalWidth,image.naturalHeight,ctx.getImageData(0,0,1,1).data[3]]);
          };image.src=src;
        })))""", paths)
        self.assertEqual(rows,[[512,512,0]]*36)
        self.assertEqual(errors,[])

    def test_all_poses_alignment_fallback_and_cache(self):
        page, errors, requests = self.model_runner()
        results = page.evaluate('''async ids => {
          const m=runnerModel, cache={}, results=[];
          const loaded=i=>i.complete&&i.naturalWidth>0;
          for(const id of ids) {
            const images=m.loadCharacterImages(cache,id,()=>{});
            await Promise.all(Object.values(images).filter(Boolean).map(i=>i.complete?null:new Promise(r=>{i.onload=i.onerror=r;})));
            const state=m.createRunnerState([],id), calls=[];
            const context={fillText:t=>calls.push({text:t}),beginPath(){},ellipse(){},fill(){},drawImage:(im,x,y,w,h)=>calls.push({src:im.src,x,y,w,h})};
            for(const pose of Object.keys(m.ANIMATION_SETS[id].frames)) {
              state.mode=pose==='idle'?'ready':'running';state.supportId='ground';state.landingUntil=0;
              if(pose.startsWith('run_')) state.animationTime=(Number(pose.slice(-1))-1)*.1;
              if(pose==='land')state.landingUntil=100;
              if(pose.startsWith('jump_')){state.supportId=null;state.airAction='jump';state.velocityY=pose==='jump_up'?-500:pose==='jump_down'?500:0;}
              if(m.characterPose(state)!==pose)throw Error('pose '+id+pose);
              m.drawCharacter(context,state,cache);
              const call=calls.at(-1),feet=m.ANIMATION_SETS[id].frames[pose].feetRatio;
              if(!call.src.endsWith('/'+id+'/'+pose+'.webp'))throw Error('mixed frame');
              if(id!=='shiba'&&Math.abs(call.y+call.h*feet-state.feetY)>.001)throw Error('floating');
              // Platform uses the same foot anchor.
              state.feetY=390;m.drawCharacter(context,state,cache);state.feetY=470;
              if(id!=='shiba'&&Math.abs(calls.at(-1).y+call.h*feet-390)>.001)throw Error('platform');
            }
            state.mode='running';state.supportId='ground';state.landingUntil=0;state.animationTime=0;
            images.run_1={complete:true,naturalWidth:0};m.drawCharacter(context,state,cache);
            const previous=calls.at(-1).src;
            images.last=null;m.drawCharacter(context,state,cache);const idle=calls.at(-1).src;
            images.idle=null;m.drawCharacter(context,state,cache);const fallback=calls.at(-1).src;
            images.fallback=null;m.drawCharacter(context,state,cache);const name=calls.at(-1).text;
            results.push({id,previous,idle,fallback,name,cached:m.loadCharacterImages(cache,id,()=>{})===images});
          } return results;
        }''', IDS)
        for item in results:
            id = item['id']
            self.assertTrue(item['previous'].endswith(f'/{id}/land.webp'))
            self.assertTrue(item['idle'].endswith(f'/{id}/idle.webp'))
            self.assertTrue(item['fallback'].endswith(f'/plush/{id}.webp'))
            self.assertTrue(item['name'])
            self.assertTrue(item['cached'])
        self.assertEqual(errors, [])

    def test_selected_only_and_switch_reuses_cache(self):
        page, errors, requests = self.preview_runner()
        def sprites():
            return [u for u in requests if '/runner/assets/' in u and 'spike-rock' not in u]
        self.assertEqual(len(sprites()),9)
        self.assertTrue(all('/shiba/' in u for u in sprites()))
        for id in IDS[1:4]:
            self.select_character(page,id)
            self.assertEqual(len([u for u in sprites() if f'/{id}/' in u]),9)
        count=len(sprites())
        self.select_character(page,'shiba');self.select_character(page,'sloth')
        self.assertEqual(len(sprites()),count)
        self.assertFalse(any('secret_yuniko' in u for u in requests))
        self.assertEqual(errors,[])

    def test_timing_pause_and_yuniko_extra_jump_both_rates(self):
        page, errors, requests=self.model_runner()
        page.evaluate('''ids=>{
          const m=runnerModel;
          for(const id of ids) for(const hz of [60,120]) {
            const s=m.createRunnerState([],id);s.mode='running';
            for(let f=0;f<4;f++) {
              if(m.characterPose(s)!=='run_'+(f+1))throw Error('run cycle');
              for(let i=0;i<hz/10;i++)m.updateRunner(s,1/hz);
            }
            s.mode='paused';const frozen=JSON.stringify(s);m.updateRunner(s,1);
            if(JSON.stringify(s)!==frozen)throw Error('pause');
            s.mode='running';m.updateRunner(s,.1);if(s.animationTime<=.4)throw Error('resume');
            m.startJump(s);m.updateRunner(s,.1);
            if(id==='secret_yuniko') {
              if(s.lives!==3||!m.startJump(s)||s.airJumpsRemaining!==0||m.characterPose(s)!=='jump_up')throw Error('extra jump');
            }
          }
        }''',IDS)
        self.assertEqual(errors,[])

    def test_delayed_and_failed_new_sprites_keep_input_and_same_character(self):
        page, errors, requests=self.preview_runner()
        page.evaluate('''()=>{
          window.animationDraws=[];
          const original=CanvasRenderingContext2D.prototype.drawImage;
          CanvasRenderingContext2D.prototype.drawImage=function(im,...a){
            if(im.src.includes('/plush/')||/assets\\/(sloth|goldfish|salamander)\\//.test(im.src))animationDraws.push(im.src);
            return original.call(this,im,...a);
          };
        }''')
        for id in IDS[1:4]:
            held=[]
            page.route(f'**/runner/assets/{id}/*.webp',lambda route:held.append(route))
            page.locator(f'#runner-character-cards [data-choice="{id}"]').click()
            page.wait_for_function('id=>runnerImages.filter(i=>i.src.includes("/runner/assets/"+id+"/")).length===9',arg=id)
            self.settle(page)
            self.assertEqual(len(held),9)
            self.assertTrue(page.evaluate('animationDraws.at(-1)').endswith(f'/plush/{id}.webp'))
            page.locator('#runner-toggle').click();page.evaluate('runnerClock.step(0)')
            page.locator('#runner-jump').dispatch_event('click')
            page.evaluate('runnerClock.advance(100,60)')
            self.assertLess(page.evaluate('runnerPreviewState.feetY'),470)
            self.assertGreater(page.evaluate('runnerPreviewState.distance'),0)
            for route in held:
                route.fulfill(status=404,body='missing')
            page.wait_for_function('runnerImages.every(i=>i.complete)')
            self.settle(page)
            self.assertTrue(page.evaluate('animationDraws.at(-1)').endswith(f'/plush/{id}.webp'))
            page.evaluate("runnerPreviewState.distance=runnerPreviewState.goalDistance-1")
            page.evaluate('runnerClock.advance(50,60)')
            self.settle(page)
            before=len([u for u in requests if f'/runner/assets/{id}/' in u])
            self.select_character(page,'shiba');self.select_character(page,id)
            self.assertEqual(len([u for u in requests if f'/runner/assets/{id}/' in u]),before)
        self.assertEqual(errors,[])


class RunnerSecretAnimationTest(unittest.TestCase):
    # Independent IndexedDB fixture, no real profile data.
    from runner_integration_test import RunnerIntegrationTest as _base
    setUpClass = classmethod(_base.setUpClass.__func__)
    tearDownClass = classmethod(_base.tearDownClass.__func__)
    setUp = _base.setUp
    tearDown = _base.tearDown
    enter = _base.enter

    def test_acquired_only_loads_animation_and_can_air_jump(self):
        requests=[]
        self.page.on('request',lambda r:requests.append(r.url))
        self.context.add_init_script('''window.animationDraws=[];
          const draw=CanvasRenderingContext2D.prototype.drawImage;
          CanvasRenderingContext2D.prototype.drawImage=function(im,...a){animationDraws.push(im.src);return draw.call(this,im,...a);};''')
        self.enter()
        self.page.frame_locator('iframe').locator('#runner-toggle').wait_for()
        self.assertFalse(any('secret_yuniko' in u for u in requests))
        self.assertNotIn('ゆにこ',self.page.locator('#runner').inner_text())
        self.page.evaluate('''async()=>{
          await runnerTransaction(['arcadePrizes'],tx=>tx.objectStore('arcadePrizes').put({id:'secret',profile:'student',prizeId:'secret_yuniko'}));
          await formalRunner.refresh();
        }''')
        self.assertFalse(any('/runner/assets/secret_yuniko/' in u for u in requests))
        self.page.locator('#formal-character-cards [data-choice="secret_yuniko"]').click()
        child=self.page.frames[-1]
        child.wait_for_function("animationDraws.some(s=>s.endsWith('/secret_yuniko/idle.webp'))")
        self.assertEqual(len([u for u in requests if '/runner/assets/secret_yuniko/' in u]),9)
        self.page.once('dialog',lambda d:d.accept())
        self.page.frame_locator('iframe').locator('#runner-toggle').click()
        self.page.wait_for_function("formalRunner.session?.view.state.mode==='running'")
        self.assertEqual(self.page.evaluate('''async()=>{
          await formalRunner.bridge.jump();await formalRunner.bridge.advance(.1);await formalRunner.bridge.jump();
          const s=formalRunner.session.view.state;
          return [s.characterId,s.lives,s.airJumpsRemaining,m.characterPose(s)];
        }'''),['secret_yuniko',3,0,'jump_up'])
        child.wait_for_function("animationDraws.some(s=>s.endsWith('/secret_yuniko/jump_up.webp'))")
