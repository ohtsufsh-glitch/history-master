"""Issue #87: 描画のみの被弾反応と縦画面操作。既存の手動RAFで検証。"""
import unittest
import runner_preview_test as preview
from runner_character_ui_test import RunnerCharacterUITest


class RunnerHitFeedbackTest(unittest.TestCase):
    setUpClass = classmethod(preview.RunnerPreviewTest.setUpClass.__func__)
    tearDownClass = classmethod(preview.RunnerPreviewTest.tearDownClass.__func__)
    snapshot = preview.RunnerPreviewTest.snapshot
    toggle = preview.RunnerPreviewTest.toggle
    tap = preview.RunnerPreviewTest.tap
    preview_runner = preview.RunnerPreviewTest.preview_runner
    settle = preview.RunnerPreviewTest.settle
    state = preview.RunnerPreviewTest.state
    select_stage = preview.RunnerPreviewTest.select_stage
    advance_to_collision = preview.RunnerPreviewTest.advance_to_collision
    assert_hearts = preview.RunnerPreviewTest.assert_hearts
    assert_isolated = RunnerCharacterUITest.assert_isolated

    def test_portrait_stack_scroll_and_landscape_unchanged(self):
        for suffix in ('', '?stagePreview=1'):
            for width, height in ((320,568),(390,844),(844,390),(768,1024)):
                for enlarged in (False, True) if width <= 390 else (False,):
                    with self.subTest(suffix=suffix, size=(width,height), enlarged=enlarged):
                        page, errors, requests = self.preview_runner(suffix, width, height)
                        if enlarged:
                            page.add_style_tag(content='html { font-size: 200%; }')
                            self.settle(page)
                        jump=page.locator('#runner-jump')
                        toggle=page.locator('#runner-toggle')
                        a,b=jump.bounding_box(),toggle.bounding_box()
                        self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),width)
                        if width <= 390:
                            self.assertLessEqual(a['y']+a['height'], b['y'])
                            self.assertAlmostEqual(a['x'],b['x'],delta=1)
                            self.assertGreaterEqual(a['width'],width-33)
                            self.assertAlmostEqual(a['width'],b['width'],delta=1)
                            self.assertGreaterEqual(page.locator('#runner-stage').bounding_box()['height'],159)
                            viewport=page.locator('#runner-viewport').bounding_box()
                            self.assertLessEqual(viewport['y']+viewport['height'],a['y'])
                        elif width==844 and suffix:
                            self.assertAlmostEqual(a['y'],b['y'],delta=1)
                            self.assertLess(a['x'],b['x'])
                        for button in (toggle,jump):
                            button.scroll_into_view_if_needed()
                            box=button.bounding_box()
                            self.assertGreaterEqual(box['height'],44)
                            self.assertGreaterEqual(box['y'],0)
                            self.assertLessEqual(box['y']+box['height'],height+1)
                            page.touchscreen.tap(box['x']+box['width']/2,box['y']+box['height']/2)
                        self.assertLess(self.state(page)['velocityY'],0)
                        self.assert_isolated(page,errors,requests)
                        page.context.close()

    def test_feedback_draws_expires_and_freezes_with_jump_and_shield(self):
        for character in ('shiba','sloth','goldfish','salamander'):
            for reduced in (False,True):
                with self.subTest(character=character,reduced=reduced):
                    page,errors,requests=self.preview_runner()
                    page.evaluate("""()=>{
                      window.hitDraw={};
                      const p=CanvasRenderingContext2D.prototype;
                      const set=p.setTransform,draw=p.drawImage,arc=p.arc;
                      p.setTransform=function(...args){hitDraw={};return set.apply(this,args)};
                      p.drawImage=function(img,x,y,w,h){
                        if(img.src.includes('/plush/')||img.src.includes('/shiba/')){
                          const t=this.getTransform().transformPoint({x:x+w/2,y});
                          hitDraw.x=t.x*960/this.canvas.width;
                        }
                        return draw.call(this,img,x,y,w,h);
                      };
                      p.arc=function(x,y,r,...args){
                        if(r===58){const t=this.getTransform().transformPoint({x,y});hitDraw.shield=t.x*960/this.canvas.width;}
                        if(this.strokeStyle==='#bd5425')hitDraw.impact=r;
                        return arc.call(this,x,y,r,...args);
                      };
                    }""")
                    page.emulate_media(reduced_motion='reduce' if reduced else 'no-preference')
                    page.locator('#runner-character-select').select_option(character)
                    page.wait_for_function('runnerImages.every(i=>i.complete)', polling=10)
                    self.settle(page)
                    self.toggle(page)
                    page.evaluate('runnerClock.step(0)')
                    self.assertEqual(self.state(page)['hitFeedbackRemaining'],0)
                    hit=self.advance_to_collision(page)
                    self.assertEqual(hit['mode'],'running')
                    self.assertEqual(hit['lives'],hit['initialLives']-1)
                    self.assertGreater(hit['hitFeedbackRemaining'],.22)
                    self.assertGreater(hit['invincibleRemaining'],.98)
                    self.assert_hearts(page,hit['lives'],hit['initialLives'])
                    page.evaluate('runnerClock.advance(80,120)')
                    scene=page.evaluate('hitDraw')
                    center=scene['x']
                    self.assertAlmostEqual(center,186 if reduced else 186-36,delta=7)
                    self.assertAlmostEqual(scene['shield'],center,delta=.001)
                    self.assertIn('impact',scene)
                    self.toggle(page)
                    paused=self.state(page)
                    page.evaluate('runnerClock.advance(10000)')
                    self.assertEqual(self.state(page),paused)
                    self.toggle(page)
                    page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
                    page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,get:()=>true}); document.dispatchEvent(new Event('visibilitychange'))")
                    frozen=self.state(page)
                    page.evaluate('runnerClock.advance(10000)')
                    self.assertEqual(self.state(page),frozen)
                    page.evaluate("delete document.hidden; document.dispatchEvent(new Event('visibilitychange'))")
                    self.settle(page)
                    self.toggle(page)
                    page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
                    self.tap(page)
                    page.evaluate('runnerClock.advance(170,120)')
                    after=self.state(page)
                    self.assertEqual(after['hitFeedbackRemaining'],0)
                    self.assertIsNone(after['hitPoint'])
                    self.assertLess(after['feetY'],470)
                    self.assertEqual(after['lives'],hit['lives'])
                    self.assertAlmostEqual(after['distance'],hit['distance']+hit['speed']*.25,delta=1e-6)
                    self.assertAlmostEqual(after['invincibleRemaining'],hit['invincibleRemaining']-.25,delta=1e-6)
                    self.assertAlmostEqual(page.evaluate('hitDraw.x'),186,delta=.001)
                    self.assertNotIn('impact',page.evaluate('hitDraw'))
                    self.assert_isolated(page,errors,requests)
                    page.context.close()

    def test_feedback_does_not_change_physics_or_collision(self):
        page,_,_=self.preview_runner()
        page.evaluate("async()=>{window.m=await import(document.querySelector('script[type=module]').src)}")
        result=page.evaluate("""()=>{
          const a=m.createRunnerState([]),b=m.createRunnerState([]);
          a.mode=b.mode='running';
          a.objects=[{type:'obstacle',x:220,id:0}];
          b.objects=structuredClone(a.objects);
          m.updateRunner(a,0);m.updateRunner(b,0);
          m.startJump(a);m.startJump(b);
          for(let i=0;i<150;i++){
            b.hitFeedbackRemaining=0;b.hitPoint=null;
            m.updateRunner(a,1/120);m.updateRunner(b,1/120);
            const clean=s=>{const {hitFeedbackRemaining,hitPoint,...rest}=s;return rest};
            if(JSON.stringify(clean(a))!==JSON.stringify(clean(b)))return false;
          }
          return a.hitFeedbackRemaining===0&&a.invincibleRemaining===0;
        }""")
        self.assertTrue(result)
