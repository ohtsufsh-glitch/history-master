"""Issue #102: 独立DB・合成データで保存/復帰/画像の遅延を検証。"""
import unittest
import runner_session_test as sessions


class RunnerSafariTest(unittest.TestCase):
    setUpClass = classmethod(sessions.RunnerSessionTest.setUpClass.__func__)
    tearDownClass = classmethod(sessions.RunnerSessionTest.tearDownClass.__func__)
    setUp = sessions.RunnerSessionTest.setUp
    tearDown = sessions.RunnerSessionTest.tearDown

    def enter(self):
        self.page.evaluate("navigate('runner')")
        self.page.frame_locator('iframe').locator('#runner-toggle').wait_for()

    def test_scroll_resize_visibility_bfcache_preserve_frame_and_selection(self):
        for width, height in [(390,844),(844,390),(820,1180)]:
            self.page.set_viewport_size(dict(width=width,height=height))
            self.enter()
            self.page.evaluate("""()=>{
              window.originalFrame=formalRunner.frame;
              formalRunner.select('S01','goldfish');
              document.querySelector('#formal-character-cards').scrollIntoView();
              window.originalScroll=scrollY;
              window.dispatchEvent(new Event('resize'));
              window.dispatchEvent(new Event('orientationchange'));
              window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));
              Object.defineProperty(document,'hidden',{configurable:true,value:true});
              document.dispatchEvent(new Event('visibilitychange'));
              Object.defineProperty(document,'hidden',{configurable:true,value:false});
              document.dispatchEvent(new Event('visibilitychange'));
            }""")
            self.page.wait_for_timeout(300)
            self.assertTrue(self.page.evaluate("originalFrame===formalRunner.frame && Math.abs(scrollY-originalScroll)<=1 && formalRunner.bridge.view.state.characterId==='goldfish'"))

    def test_delayed_failed_images_never_draw_generic_character_or_reload_on_refresh(self):
        # Canvas calls distinguish the neutral name label from the orange generic drawing.
        self.page.add_init_script("""
          window.orangeDraws=0;window.names=[];
          const ellipse=CanvasRenderingContext2D.prototype.ellipse;
          CanvasRenderingContext2D.prototype.ellipse=function(...a){if(this.fillStyle==='#e99b45')window.orangeDraws++;return ellipse.apply(this,a);};
          const text=CanvasRenderingContext2D.prototype.fillText;
          CanvasRenderingContext2D.prototype.fillText=function(t,...a){window.names.push(t);return text.call(this,t,...a);};
        """)
        requests=[]
        self.page.route('**/assets/plush/goldfish.webp',lambda r:(requests.append(r.request.url),r.abort()))
        self.enter()
        self.page.evaluate("formalRunner.select('S01','goldfish')")
        child=self.page.frames[-1]
        self.page.wait_for_timeout(150)
        self.assertIn('金魚',child.evaluate('names'))
        count=len(requests)
        self.page.evaluate("async()=>{await formalRunner.refresh();await formalRunner.refresh();}")
        self.assertEqual(len(requests),count)
        self.assertEqual(child.evaluate('orangeDraws'),0)
        # Failed art must not prevent purchase, pause, or free resume.
        self.page.on('dialog',lambda d:d.accept())
        self.page.evaluate('formalRunner.bridge.resume()')
        self.page.evaluate('formalRunner.bridge.pause()')
        self.page.evaluate('formalRunner.bridge.resume()')
        self.assertEqual(self.page.evaluate("async()=>[(await readAll('coinSpends')).length,formalRunner.session.view.state.characterId]"),[1,'goldfish'])

    def test_pending_frames_refresh_once_and_checkpoint_reads_only_key(self):
        self.enter()
        self.assertTrue(self.page.evaluate("""async()=>{
          formalRunner.frame.contentWindow.stopFormalRunner();
          const play=await buy();formalRunner.session=await openRunnerSession('student',play.id,{lifecycle:false});
          await formalRunner.session.resume();
          const original=IDBObjectStore.prototype.getAll;
          IDBObjectStore.prototype.getAll=function(){throw new Error('checkpoint must use get(id)');};
          try{await formalRunner.session.checkpoint();}finally{IDBObjectStore.prototype.getAll=original;}
          const lobby=runnerLobbyData;let calls=0;
          runnerLobbyData=async(...a)=>{calls++;return lobby(...a);};
          try {
            while(formalRunner.session.view.state.mode==='running'){
              const pending=[];
              for(let i=0;i<20&&formalRunner.session.view.state.mode==='running';i++)pending.push(formalRunner.bridge.advance(.05));
              await Promise.all(pending);
            }
            const saved=formalRunner.session.view;
            if(calls!==1||saved.dirty||!formalRunner.bridge.view.result||saved.savedPlay.status!=='finished')return false;
            const at=saved.savedPlay.updatedAt;
            await formalRunner.session.pause();await formalRunner.session.close();
            return formalRunner.session.view.savedPlay.updatedAt===at;
          }finally{runnerLobbyData=lobby;}
        }"""))

    def test_finish_save_failure_never_confirms_result(self):
        self.enter()
        self.assertTrue(self.page.evaluate("""async()=>{
          formalRunner.frame.contentWindow.stopFormalRunner();
          const play=await buy();formalRunner.session=await openRunnerSession('student',play.id,{lifecycle:false});
          await formalRunner.session.resume();
          const original=saveRunnerState;
          saveRunnerState=async(...a)=>{if(a[3].mode==='finished')throw new Error('synthetic quota');return original(...a);};
          try {
            while(formalRunner.session.view.state.mode==='running')await formalRunner.bridge.advance(.05).catch(()=>{});
            return !!formalRunner.session.view.error&&formalRunner.session.view.dirty&&!formalRunner.bridge.view.result&&(await readAll('coinSpends')).length===1;
          }finally{saveRunnerState=original;}
        }"""))

    def test_shiba_animation_delay_uses_same_character_static_then_cached_frames(self):
        self.page.add_init_script("""
          window.drawnImages=[];
          const draw=CanvasRenderingContext2D.prototype.drawImage;
          CanvasRenderingContext2D.prototype.drawImage=function(img,...a){window.drawnImages.push(img.src);return draw.call(this,img,...a);};
        """)
        pending=[]
        self.page.route('**/runner/assets/shiba/*.webp',lambda r:pending.append(r))
        self.enter()
        child=self.page.frames[-1]
        child.wait_for_function("drawnImages.some(s=>s.includes('/assets/plush/shiba.webp'))")
        self.page.evaluate('formalRunner.refresh()')
        self.assertEqual(len(pending),9)
        for route in pending:
            route.continue_()
        child.wait_for_function("drawnImages.some(s=>s.includes('/runner/assets/shiba/idle.webp'))")
        count=len(pending)
        self.page.on('dialog',lambda d:d.accept())
        self.page.evaluate('formalRunner.bridge.resume()')
        self.page.evaluate('formalRunner.bridge.pause()')
        self.page.evaluate('formalRunner.bridge.resume()')
        self.page.evaluate('formalRunner.refresh()')
        self.assertEqual(len(pending),count)
        self.assertEqual(self.page.evaluate("async()=>(await readAll('coinSpends')).length"),1)

    def test_focus_refresh_racing_finish_rechecks_committed_result(self):
        self.enter()
        self.assertTrue(self.page.evaluate("""async()=>{
          formalRunner.frame.contentWindow.stopFormalRunner();
          const p=await buy();formalRunner.session=await openRunnerSession('student',p.id,{lifecycle:false});await formalRunner.session.resume();
          const original=runnerLobbyData;let release,started;
          const ready=new Promise(r=>started=r);
          runnerLobbyData=async(...a)=>{
            const d=await original(...a);
            runnerLobbyData=original;
            started();await new Promise(r=>release=r);return d;
          };
          const refresh=formalRunner.refresh();await ready;
          while(formalRunner.session.view.state.mode==='running')await formalRunner.session.advance(.05);
          release();await refresh;
          return !!formalRunner.bridge.view.result&&!formalRunner.session.view.dirty;
        }"""))

    def test_delayed_initial_frame_does_not_override_user_scroll(self):
        self.page.set_viewport_size(dict(width=390,height=844))
        held=[]
        self.page.route('**/runner/?embedded=1&v=*',lambda route:held.append(route))
        self.page.evaluate("""()=>{
          window.entryScrolls=0;
          const original=Element.prototype.scrollIntoView;
          Element.prototype.scrollIntoView=function(...args){if(this.id==='runner-frame-host')entryScrolls++;return original.apply(this,args);};
        }""")
        self.page.locator('#open-runner').scroll_into_view_if_needed()
        self.page.locator('#open-runner').click()
        self.page.locator('#formal-character-cards button').first.wait_for()
        self.page.wait_for_timeout(100)
        self.assertEqual(len(held),1)
        self.assertEqual(self.page.evaluate('entryScrolls'),1)
        self.page.locator('#formal-character-cards').scroll_into_view_if_needed()
        before=self.page.evaluate('scrollY')
        self.assertGreater(before,300)
        held[0].continue_()
        self.page.frame_locator('iframe').locator('#runner-toggle').wait_for()
        self.page.wait_for_timeout(100)
        self.assertAlmostEqual(self.page.evaluate('scrollY'),before,delta=1)
        self.assertEqual(self.page.evaluate('entryScrolls'),1)

    def test_history_traversal_does_not_apply_entry_scroll(self):
        self.page.set_viewport_size(dict(width=390,height=844))
        self.page.evaluate("""()=>{
          window.entryScrolls=0;
          const original=Element.prototype.scrollIntoView;
          Element.prototype.scrollIntoView=function(...args){if(this.id==='runner-frame-host')entryScrolls++;return original.apply(this,args);};
        }""")
        self.page.locator('#open-runner').scroll_into_view_if_needed()
        home_y=self.page.evaluate('scrollY')
        self.page.locator('#open-runner').click()
        self.page.frame_locator('iframe').locator('#runner-toggle').wait_for()
        self.page.locator('#formal-character-cards').scroll_into_view_if_needed()
        runner_y=self.page.evaluate('scrollY')
        self.page.go_back()
        self.page.locator('#open-runner').wait_for()
        self.page.wait_for_timeout(100)
        self.assertAlmostEqual(self.page.evaluate('scrollY'),home_y,delta=1)
        self.page.go_forward()
        self.page.frame_locator('iframe').locator('#runner-toggle').wait_for()
        self.page.wait_for_timeout(100)
        self.assertAlmostEqual(self.page.evaluate('scrollY'),runner_y,delta=1)
        self.assertEqual(self.page.evaluate('entryScrolls'),1)
