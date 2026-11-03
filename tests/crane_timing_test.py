"""クレーンの時間設定とCSS同期。公開可能な合成データと一時ブラウザのみ使用。"""

import unittest

import arcade_board_test as board_test


SAMPLE_ANIMATION = """async ({outcome,fallAt,fast})=>{
  const play=await purchaseCranePlay(newArcadePlay(profile));
  play.armX=50;
  const values=outcome==='miss'?[.999]:outcome==='drop'?[0,.999,.5]:[0,0];
  const result=chooseCraneOutcome(play,()=>values.shift()??0);
  if(outcome==='drop')result.fallAt=fallAt;
  arcadePlay=await commitCraneOutcome(play,result);
  await renderArcade();arcadeResumeRequired=false;
  const saved=JSON.stringify(await snapshotAllStores());
  const stage=$('crane-stage'),arm=$('crane-arm');
  const toy=stage.querySelector('[data-slot="3"]');
  await toy.querySelector('img').decode();
  await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
  const number=(el,property)=>parseFloat(getComputedStyle(el)[property]);
  const geometry=()=>{
    const t=toy.getBoundingClientRect(),a=arm.getBoundingClientRect();
    return {armX:a.x+a.width/2,toyX:t.x+t.width/2,toyTop:t.top,
      cable:number(stage.querySelector('.crane-cable'),'height'),
      head:number(stage.querySelector('.crane-head'),'top'),
      claws:[...stage.querySelectorAll('.claw')].map(el=>({
        top:number(el,'top'),tip:el.getBoundingClientRect().bottom})),
      grip:t.top+t.height*.6,bottom:number(toy,'bottom'),
      delivered:toy.classList.contains('delivered'),opacity:number(toy,'opacity')};
  };
  const events=[],phases=[],timer=window.setTimeout;
  const ended=event=>events.push({property:event.propertyName,seconds:event.elapsedTime,
    target:event.target.className});
  stage.addEventListener('transitionend',ended);
  window.setTimeout=(callback,ms,...args)=>{
    // スタイルを確定し、CSSが実際に作ったトランジションを検査する。
    getComputedStyle(toy).bottom;
    const animations=stage.getAnimations({subtree:true}).filter(a=>a.playState!=='finished');
    const phase={ms,stage:stage.className,toy:toy.className,start:geometry(),
      animations:animations.map(a=>({target:a.effect.target.className,
        property:a.transitionProperty,duration:a.effect.getComputedTiming().duration}))};
    if(fast){
      animations.forEach(a=>{a.pause();a.currentTime=a.effect.getComputedTiming().duration/2;});
      phase.middle=geometry();
      animations.forEach(a=>a.finish());
    }
    phases.push(phase);
    return timer(()=>{
      phase.end=geometry();
      if(fast)requestAnimationFrame(()=>requestAnimationFrame(()=>callback(...args)));
      else callback(...args);
    },fast?0:ms);
  };
  try {await animateCraneOutcome(arcadePlay);}
  finally {window.setTimeout=timer;stage.removeEventListener('transitionend',ended);}
  return {phases,events,end:geometry(),result,
    unchanged:saved===JSON.stringify(await snapshotAllStores()),
    armInline:arm.style.transitionDuration,toyInline:toy.style.transitionDuration};
}"""


class CraneTimingTest(unittest.TestCase):
    # 共通サーバー・ブラウザ管理のみ再利用し、既存テスト自体は継承しない。
    setUpClass = classmethod(board_test.ArcadeBoardTest.setUpClass.__func__)
    tearDownClass = classmethod(board_test.ArcadeBoardTest.tearDownClass.__func__)
    setUp = board_test.ArcadeBoardTest.setUp
    tearDown = board_test.ArcadeBoardTest.tearDown
    ready = board_test.ArcadeBoardTest.ready
    on_dialog = board_test.ArcadeBoardTest.on_dialog
    install = board_test.ArcadeBoardTest.install

    def sample(self, outcome='win', fall_at=.5, fast=True):
        self.install()
        return self.page.evaluate(SAMPLE_ANIMATION,
                                  {'outcome': outcome, 'fallAt': fall_at, 'fast': fast})

    def assert_duration(self, phase, target, prop, expected):
        matches = [a['duration'] for a in phase['animations']
                   if target in a['target'].split() and a['property'] == prop]
        self.assertEqual(matches, [expected], (phase, target, prop))

    def assert_vertical_sync(self, sample):
        self.assertAlmostEqual(sample['cable'] - sample['head'], 7, delta=.1)
        for claw in sample['claws']:
            self.assertAlmostEqual(claw['top'] - sample['head'], 19, delta=.1)

    def test_config_total_and_pre_catch_sweep_remain_two_and_half_seconds(self):
        self.install()
        actual = self.page.evaluate("""async()=>{
          await startCrane();stopCraneSweep();
          const config={...CRANE_CONFIG},positions=[];
          const raf=window.requestAnimationFrame,cancel=window.cancelAnimationFrame;
          let next;
          window.requestAnimationFrame=callback=>{next=callback;return 1;};
          window.cancelAnimationFrame=()=>{};
          try {
            arcadePlay.armX=12;arcadeDirection=1;startCraneSweep();
            for(let ms=0;ms<=2500;ms+=50){
              next(ms);
              if(ms===0||ms===1250||ms===2500)positions.push(arcadePlay.armX);
            }
            return {config,positions,transition:getComputedStyle($('crane-arm')).transitionDuration};
          } finally {stopCraneSweep();window.requestAnimationFrame=raf;window.cancelAnimationFrame=cancel;}
        }""")
        config = actual['config']
        self.assertEqual([config[k] for k in ['dropMs', 'liftMs', 'transportMs', 'releaseMs']],
                         [1520, 2000, 2000, 480])
        self.assertEqual(sum(config[k] for k in ['dropMs', 'liftMs', 'transportMs', 'releaseMs']), 6000)
        self.assertEqual(config['oneWaySeconds'], 2.5)
        for position, expected in zip(actual['positions'], [12, 50, 88]):
            self.assertAlmostEqual(position, expected, delta=.0001)
        self.assertEqual(actual['transition'], '0s')

    def test_css_phases_share_js_times_and_lift_stays_attached_at_midpoint(self):
        animation = self.sample()
        drop, lift, travel, release = animation['phases']
        self.assertEqual([p['ms'] for p in animation['phases']], [1520, 2000, 2100, 480])
        for phase, duration in [(drop, 1520), (lift, 2000)]:
            self.assert_duration(phase, 'crane-cable', 'height', duration)
            self.assert_duration(phase, 'crane-head', 'top', duration)
            self.assertEqual([a['duration'] for a in phase['animations']
                              if 'claw' in a['target'].split() and a['property'] == 'top'],
                             [duration, duration])
            self.assert_vertical_sync(phase['middle'])
        self.assert_duration(lift, 'crane-toy', 'bottom', 2000)
        for claw in lift['middle']['claws']:
            self.assertAlmostEqual(claw['tip'], lift['middle']['grip'], delta=1.5)
        self.assert_duration(travel, 'crane-arm', 'left', 2000)
        self.assert_duration(travel, 'crane-toy', 'left', 2000)
        self.assertAlmostEqual(travel['middle']['armX'], travel['middle']['toyX'], delta=1)
        self.assertFalse(travel['start']['delivered'])
        self.assertAlmostEqual(release['start']['toyX'], travel['end']['toyX'], delta=1)
        for prop in ['bottom', 'opacity', 'transform']:
            self.assert_duration(release, 'crane-toy', prop, 480)
        self.assertEqual(animation['end']['opacity'], 0)
        self.assertTrue(animation['unchanged'])
        self.assertEqual((animation['armInline'], animation['toyInline']), ('', ''))

    def test_partial_transport_preserves_fall_location_and_scales_duration(self):
        for fraction in [.1, .5, .95]:
            with self.subTest(fraction=fraction):
                animation = self.sample('drop', fraction)
                travel, fall = animation['phases'][2:]
                duration = round(2000 * fraction)
                self.assertEqual(travel['ms'], duration + 100)
                self.assert_duration(travel, 'crane-arm', 'left', duration)
                self.assert_duration(travel, 'crane-toy', 'left', duration)
                self.assertAlmostEqual(travel['middle']['armX'], travel['middle']['toyX'], delta=1)
                # ページ上の絶対座標ではなく、CSSの同じ%座標を確認する。
                positions = self.page.evaluate("""()=>({
                  arm:parseFloat($('crane-arm').style.left),
                  toy:parseFloat($('crane-prizes').querySelector('[data-slot="3"]').style.left)
                })""")
                self.assertAlmostEqual(positions['arm'], 50 + 42 * fraction)
                self.assertAlmostEqual(positions['toy'], positions['arm'])
                self.assert_duration(fall, 'crane-toy', 'bottom', 550)
                self.assertEqual(fall['ms'], 720)
                self.assertEqual(animation['end']['bottom'], 34)
                self.assertFalse(animation['end']['delivered'])
                self.assertTrue(animation['unchanged'])

    def test_real_success_finishes_each_transition_before_next_phase(self):
        animation = self.sample(fast=False)
        drop, lift, travel, release = animation['phases']
        for claw in drop['end']['claws']:
            self.assertAlmostEqual(claw['tip'], drop['end']['grip'], delta=1.5)
        for claw in lift['end']['claws']:
            self.assertAlmostEqual(claw['tip'], lift['end']['grip'], delta=1.5)
        self.assertAlmostEqual(travel['end']['armX'], travel['end']['toyX'], delta=1)
        self.assertEqual(travel['end']['opacity'], 1)
        self.assertFalse(travel['end']['delivered'])
        self.assertTrue(release['start']['delivered'])
        self.assertAlmostEqual(release['start']['toyX'], travel['end']['toyX'], delta=1)
        for target, prop, seconds in [('crane-cable', 'height', 1.52),
                                      ('crane-cable', 'height', 2),
                                      ('crane-arm', 'left', 2),
                                      ('crane-toy', 'left', 2),
                                      ('crane-toy', 'opacity', .48)]:
            self.assertTrue(any(target in event['target'].split() and event['property'] == prop
                                and abs(event['seconds'] - seconds) < .001
                                for event in animation['events']), (target, prop, seconds))
        self.assertEqual(animation['end']['opacity'], 0)
        self.assertTrue(animation['unchanged'])


if __name__ == '__main__':
    unittest.main()
