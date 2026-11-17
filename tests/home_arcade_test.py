"""#111: ホーム配置と保存済み実績。独立DBの合成データのみ。"""
import json
import os
from pathlib import Path
import unittest
import runner_session_test as session
import runner_canvas_test as canvas

SIZES = [(1180,820),(1024,768),(1366,1024),(820,1180),(390,844),(844,390),(700,900)]
MEASURE = """() => {
 const rect=s=>{const r=document.querySelector(s).getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,bottom:r.bottom};};
 return {main:rect('main'),cards:['#game-center-home','.runner-home-panel'].map(rect),buttons:['#open-arcade','#open-runner'].map(rect),overflow:document.documentElement.scrollWidth>innerWidth,
 clipped:[...document.querySelectorAll('.arcade-home-panel *')].filter(e=>e.scrollWidth>e.clientWidth+1&&e.clientWidth>0).map(e=>e.className)};
}"""

class HomeArcadeTest(unittest.TestCase):
    setUpClass = classmethod(session.RunnerSessionTest.setUpClass.__func__)
    tearDownClass = classmethod(session.RunnerSessionTest.tearDownClass.__func__)
    setUp = session.RunnerSessionTest.setUp
    tearDown = session.RunnerSessionTest.tearDown

    def test_layout(self):
        phase=os.environ.get('HOME_PHASE','after')
        out=Path('docs/home-111');out.mkdir(parents=True,exist_ok=True)
        measurements={}
        self.page.evaluate('navigateHome()')
        for w,h in SIZES:
            with self.subTest(size=(w,h)):
                self.page.set_viewport_size(dict(width=w,height=h))
                self.page.evaluate('document.fonts.ready');self.page.wait_for_timeout(100)
                d=self.page.evaluate(MEASURE);measurements[f'{w}x{h}']=d
                a,b=d['cards'];ba,bb=d['buttons']
                self.assertFalse(d['overflow']);self.assertFalse(d['clipped'])
                if phase!='before' and w>=1000 and w>h and h>=600:
                    self.assertAlmostEqual(a['y'],b['y'],delta=1)
                    self.assertAlmostEqual(a['width'],b['width'],delta=1)
                    self.assertAlmostEqual(a['bottom'],b['bottom'],delta=1)
                    self.assertAlmostEqual(ba['bottom'],bb['bottom'],delta=1)
                    self.assertTrue(14<=b['x']-a['x']-a['width']<=18)
                else:self.assertGreaterEqual(b['y'],a['bottom'])
                self.assertGreaterEqual(min(ba['height'],bb['height']),44)
                if (w,h) in [(1180,820),(390,844)]:
                    self.page.locator('#game-center-home').scroll_into_view_if_needed()
                    # 両カード全体を撮影。iPhoneは縦長画像にする。
                    box=dict(x=a['x'],y=self.page.evaluate('scrollY')+self.page.locator('#game-center-home').bounding_box()['y'],width=b['x']+b['width']-a['x'],height=b['bottom']-a['y'])
                    self.page.screenshot(path=str(out/f'{phase}-{w}x{h}.png'),clip=box,full_page=True)
        (out/f'{phase}.json').write_text(json.dumps(measurements,ensure_ascii=False,indent=2)+'\n')

    def test_saved_records_profiles_and_reset(self):
        self.page.evaluate('navigateHome()')
        status=lambda:self.page.locator('#runner-home-info').inner_text()
        self.assertEqual(status(),'クリア：0/6ステージ ／ プレイ：0回')
        catcher=self.page.locator('#arcade-home-status').inner_text()
        self.page.evaluate("""async()=>{
          const at='2020-01-01T00:00:00.000Z';
          window.putRecord=async(id,stageId,reason,who='student')=>{
            const p={id,profile:who,game:'runner',schemaVersion:1,stageId,characterId:'shiba',stageVersion:1,startedAt:at,updatedAt:at,status:'finished',score:0,result:{reason,at,livesRemaining:reason==='clear'?1:0}};
            validateRunnerPlays([p]);await runnerTransaction(['runnerPlays'],tx=>tx.objectStore('runnerPlays').put(p));
            await refreshRunnerHome(viewContext());
          };
          for(let i=0;i<3;i++)await putRecord('same'+i,'S01','clear');
        }""")
        self.assertEqual(status(),'クリア：1/6ステージ ／ プレイ：3回')
        self.page.evaluate("putRecord('other','S02','clear')")
        self.page.evaluate("putRecord('over','S02','gameover')")
        self.assertEqual(status(),'クリア：2/6ステージ ／ プレイ：5回')
        self.page.evaluate("async()=>{await buy();await refreshRunnerHome(viewContext());}")
        self.assertEqual(status(),'クリア：2/6ステージ ／ プレイ：5回 ／ 続きから遊べます')
        for w,h in SIZES[:3]:
            self.page.set_viewport_size(dict(width=w,height=h))
            d=self.page.evaluate(MEASURE)
            self.assertFalse(d['overflow']);self.assertFalse(d['clipped'])
            self.assertAlmostEqual(d['buttons'][0]['bottom'],d['buttons'][1]['bottom'],delta=1)
        self.page.evaluate("navigate('home','test')")
        self.assertEqual(status(),'クリア：0/6ステージ ／ プレイ：0回')
        self.page.evaluate("putRecord('test-only','S03','clear','test')")
        self.assertEqual(status(),'クリア：1/6ステージ ／ プレイ：1回')
        self.page.evaluate("navigate('home','student')")
        self.assertEqual(status(),'クリア：2/6ステージ ／ プレイ：5回 ／ 続きから遊べます')
        self.assertEqual(self.page.locator('#arcade-home-status').inner_text(),catcher)
        self.page.reload();self.page.wait_for_function('appReady')
        self.assertEqual(status(),'クリア：2/6ステージ ／ プレイ：5回 ／ 続きから遊べます')
        self.page.evaluate("async()=>{await runnerTransaction(['runnerPlays'],tx=>tx.objectStore('runnerPlays').clear());await navigateHome();}")
        self.assertEqual(status(),'クリア：0/6ステージ ／ プレイ：0回')

    def test_free_preview_does_not_add_records(self):
        self.page.evaluate('navigateHome()')
        before=self.page.locator('#runner-home-info').inner_text()
        preview=self.context.new_page()
        preview.add_init_script(canvas.MANUAL_FRAMES)
        preview.goto(self.url.replace('index.html','runner/?stagePreview=1'))
        preview.locator('#runner-toggle').click()
        preview.evaluate('runnerClock.step(0);runnerClock.advance(60000,60)')
        preview.locator('#runner-result-title').filter(has_text='ゲームオーバー').wait_for()
        preview.close()
        self.page.evaluate('refreshRunnerHome(viewContext())')
        self.assertEqual(self.page.locator('#runner-home-info').inner_text(),before)
        self.assertEqual(self.page.evaluate("async()=>(await readAll('runnerPlays')).length"),0)

    def test_other_screen_widths_and_entry(self):
        self.page.set_viewport_size(dict(width=1180,height=820))
        for screen in ['runner','arcade','admin']:
            self.page.evaluate('(s)=>navigate(s)',screen)
            self.assertEqual(self.page.evaluate("document.querySelector('main').getBoundingClientRect().width"),1030 if screen=='arcade' else 920)
        self.page.evaluate('navigateHome()')
        self.page.locator('#open-runner').click()
        self.page.locator('#formal-stage option').first.wait_for(state='attached')
        self.assertEqual(self.page.evaluate('scrollY'),0)
        self.page.locator('#runner-home').click()
        self.page.locator('#open-arcade').click()
        self.assertFalse(self.page.locator('#arcade').evaluate("e=>e.classList.contains('hidden')"))
