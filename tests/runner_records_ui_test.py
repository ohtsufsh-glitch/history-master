"""#114: 最高得点一覧。独立context内の合成記録だけを使用。"""
import json
import os
from pathlib import Path
import unittest
import runner_integration_test as integration


class RunnerRecordsUITest(unittest.TestCase):
    setUpClass = classmethod(integration.RunnerIntegrationTest.setUpClass.__func__)
    tearDownClass = classmethod(integration.RunnerIntegrationTest.tearDownClass.__func__)
    setUp = integration.RunnerIntegrationTest.setUp
    tearDown = integration.RunnerIntegrationTest.tearDown
    enter = integration.RunnerIntegrationTest.enter

    def seed(self):
        self.page.evaluate("""async()=>{
          const at='2020-01-01T00:00:00.000Z';
          for(const [id,characterId,score,stageId,profile] of [
            ['zero','shiba',0,'S01','student'],['high','goldfish',100,'S01','student'],
            ['stage','sloth',42,'S02','student'],['test','goldfish',70,'S01','test']]) {
            const p={id,profile,game:'runner',schemaVersion:1,stageId,characterId,stageVersion:1,
              startedAt:at,updatedAt:at,status:'finished',score,result:{reason:'clear',at,livesRemaining:1}};
            validateRunnerPlays([p]);await runnerTransaction(['runnerPlays'],tx=>tx.objectStore('runnerPlays').put(p));
          }
        }""")

    def test_layout(self):
        self.seed();self.enter()
        self.page.locator('[data-choice="goldfish"]').click()
        phase=os.environ.get('RECORDS_PHASE','after')
        out=Path(os.environ.get('RECORDS_OUTPUT','/tmp/records-114'));out.mkdir(parents=True,exist_ok=True)
        measurements={}
        for w,h in [(1180,820),(1024,768),(820,1180),(390,844)]:
            self.page.set_viewport_size(dict(width=w,height=h))
            self.page.evaluate('document.fonts.ready')
            details=self.page.locator('#runner-stage-bests').locator('..')
            details.evaluate('e=>e.open=true')
            d=self.page.evaluate("""()=>{
              const list=document.querySelector('#runner-character-bests');
              const dt=[...list.querySelectorAll('dt')].find(e=>e.textContent.includes('金魚'));
              const dd=dt.nextElementSibling;
              const range=document.createRange();range.selectNodeContents(dt.querySelector('.runner-record-name')||dt);
              if(!dt.querySelector('.runner-record-name'))range.setStart(dt.firstChild,dt.textContent.indexOf('金魚'));
              const name=range.getBoundingClientRect();range.selectNodeContents(dd);const score=range.getBoundingClientRect();
              return {width:list.getBoundingClientRect().width,gap:score.left-name.right,
                overflow:document.documentElement.scrollWidth>innerWidth,
                clipped:[...document.querySelectorAll('.runner-character-bests dt,.runner-character-bests dd')].some(e=>e.scrollWidth>e.clientWidth+1)};
            }""")
            measurements[f'{w}x{h}']=d
            self.assertFalse(d['overflow']);self.assertFalse(d['clipped'])
            if phase!='before':self.assertLessEqual(d['width'],500)
            if w in [1180,390]:
                self.page.locator('#runner-records-heading').locator('..').screenshot(path=str(out/f'{phase}-{w}x{h}.png'))
        (out/f'{phase}.json').write_text(json.dumps(measurements,indent=2)+'\n')

    def test_selection_records_stage_profile_and_keyboard(self):
        self.seed();self.enter()
        names=['しば犬','なまけもの','金魚','オオサンショウウオ']
        for char,name in [('goldfish','金魚'),('sloth','なまけもの'),('shiba','しば犬')]:
            self.page.locator(f'[data-choice="{char}"]').click()
            self.assertEqual(self.page.locator('#runner-character-bests .runner-record-name').all_text_contents(),names)
            self.assertEqual(self.page.locator('#runner-character-bests .is-selected dt').inner_text(),name+'\n選択中')
            self.assertEqual(self.page.locator('#runner-character-bests .runner-record-selected').count(),1)
            self.assertIn(name+' 選択中',self.page.locator('#runner-character-bests').aria_snapshot())
        self.assertEqual(self.page.locator('#runner-character-bests dd').all_text_contents(),['0点','記録なし','100点','記録なし'])
        self.assertNotIn('▶',self.page.locator('#runner-character-bests').inner_text())
        self.assertNotIn('ゆにこ',self.page.locator('#runner').inner_text())
        self.assertIn('100点',self.page.locator('#runner-stage-best').inner_text())
        self.page.locator('[data-choice="S02"]').click()
        self.assertIn('42点',self.page.locator('#runner-stage-best').inner_text())
        self.assertEqual(self.page.locator('#runner-character-bests dd').all_text_contents(),['記録なし','42点','記録なし','記録なし'])
        summary=self.page.locator('#runner-stage-bests').locator('..').locator('summary')
        summary.focus();summary.press('Enter')
        self.assertTrue(self.page.locator('#runner-stage-bests').is_visible())
        summary.press('Space');self.assertFalse(self.page.locator('#runner-stage-bests').is_visible())
        self.assertTrue(self.page.locator('#runner-character-bests').evaluate("e=>[...e.children].every(row=>row.children[0].tagName==='DT'&&row.children[1].tagName==='DD')"))
        self.page.evaluate("navigate('runner','test')")
        self.assertIn('70点',self.page.locator('#runner-stage-best').inner_text())
        self.assertNotIn('100',self.page.locator('#runner-character-bests').inner_text())
        self.page.evaluate("navigate('runner','student')")
        self.assertIn('100点',self.page.locator('#runner-stage-best').inner_text())
