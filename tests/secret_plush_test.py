"""Issue #12。localhost・一時ブラウザ・公開可能な架空履歴だけで検証する。

実行方法・Playwrightの準備はquestion_editor_test.pyと同じ。
確率は乱数列を注入して全区間を検証し、統計的な偶然には依存しない。
"""

import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

import arcade_board_test as board_test
import plush_test


SECRETS = {'secret_koryun': 'こりゅん', 'secret_yuniko': 'ゆにこ', 'secret_kappamaru': 'かっぱまる'}
UNKNOWN = 'assets/plush/secret_unknown.webp'
SLOTS = ['shiba', 'rabbit', 'bear', 'secret_koryun', 'seal', 'cloud', 'star']

HELPERS = """() => {
  window.secretFixture = (ids=[],who='test') => {
    const data=plushFixture(ids,who);
    for(const p of data.arcadePlays) {
      const id=p.prizes[0];
      if(isSecretPlush(id)){p.prizes=Array(7).fill('shiba');p.prizes[0]=id;}
    }
    data.arcadeBoards=['student','test'].map(who=>initialArcadeBoard(who,data.arcadePlays)).filter(Boolean);
    return data;
  };
  window.secretUI = () => ({
    html:document.querySelector('#arcade').outerHTML,
    target:document.querySelector('.crane-toy[data-slot="3"] img')?.getAttribute('src'),
    stage:document.querySelector('#crane-stage').className,
    toy:document.querySelector('.crane-toy[data-slot="3"]')?.className,
    message:document.querySelector('#arcade-message').textContent
  });
  window.fastCrane = () => {
    // 待ち時間だけ短縮。運搬・保存・公開の実関数は実行する。
    const timer=window.setTimeout;
    window.setTimeout=(fn,ms,...args)=>timer(fn,0,...args);
    return ()=>window.setTimeout=timer;
  };
}"""


class SecretPlushTest(unittest.TestCase):
    # 同じテスト用サーバーとブラウザの管理方法を利用。既存テストは継承しない。
    setUpClass = classmethod(board_test.ArcadeBoardTest.setUpClass.__func__)
    tearDownClass = classmethod(board_test.ArcadeBoardTest.tearDownClass.__func__)
    tearDown = board_test.ArcadeBoardTest.tearDown
    on_dialog = board_test.ArcadeBoardTest.on_dialog
    snapshot = board_test.ArcadeBoardTest.snapshot
    board = board_test.ArcadeBoardTest.board

    def setUp(self):
        board_test.ArcadeBoardTest.setUp(self)

    def ready(self):
        board_test.ArcadeBoardTest.ready(self)
        self.page.evaluate(HELPERS)

    def install(self, slots=None, who='test', owned=()):
        self.page.evaluate("""async ({slots,who,owned})=>{
          const data=secretFixture(owned,who);
          data.arcadeBoards.find(b=>b.profile===who).slots=slots;
          await plushInstall(data);profile=who;await openArcade();
        }""", {'slots': slots or SLOTS, 'who': who, 'owned': list(owned)})

    def prepare(self, status='aiming', outcome='win', who='test', secret='secret_koryun'):
        slots = SLOTS[:]
        slots[3] = secret
        self.install(slots, who)
        return self.page.evaluate("""async ({status,outcome})=>{
          arcadePlay=await purchaseCranePlay(newArcadePlay(profile));
          arcadePlay.armX=50;await persistArcadeArm(arcadePlay.id,50,1);
          if(status==='resolving') {
            const values=outcome==='miss'?[.999]:outcome==='drop'?[0,.999,.5]:[0,0];
            arcadePlay=await commitCraneOutcome(arcadePlay,chooseCraneOutcome(arcadePlay,()=>values.shift()??0));
          }
          arcadeResumeRequired=true;await renderArcade();return arcadePlay.id;
        }""", {'status': status, 'outcome': outcome})

    def assert_hidden(self, state=None):
        state = state or self.page.evaluate('secretUI()')
        self.assertEqual(state['target'], UNKNOWN)
        for prize_id, name in SECRETS.items():
            self.assertNotIn(prize_id, state['html'])
            self.assertNotIn(name, state['html'])

    def test_board_probability_exact_ten_percent_equal_types_positions_and_normal_twenty(self):
        result = self.page.evaluate("""()=>{
          const types=Object.fromEntries(SECRET_PLUSH_IDS.map(id=>[id,0]));
          const normal=Object.fromEntries(PLUSH_IDS.map(id=>[id,0]));
          const positions=Array(7).fill(0);let total=0,secret=0,max=0;
          for(let b=0;b<10;b++)for(let t=0;t<3;t++)for(let s=0;s<7;s++)
          for(let n=0;n<20;n++)for(const edge of [.001,.999]) {
            const values=[(b+.5)/10,...Array(7).fill((n+edge)/20),(t+edge)/3,(s+edge)/7];
            const slots=randomArcadePrizes(()=>values.shift());
            let count=0;total++;
            slots.forEach((id,i)=>{if(isSecretPlush(id)){count++;types[id]++;positions[i]++;}else normal[id]++;});
            max=Math.max(max,count);if(count)secret++;
          }
          const boundary=[.099999999,.1].map(value=>{
            let first=true;return randomArcadePrizes(()=>{if(first){first=false;return value;}return .5;}).some(isSecretPlush);
          });
          return {total,secret,max,types,normal,positions,boundary,unknownValid:validPlushId('secret_unknown')};
        }""")
        self.assertEqual((result['total'], result['secret'], result['max']), (8400, 840, 1))
        self.assertEqual(result['types'], dict.fromkeys(SECRETS, 280))
        self.assertEqual(result['positions'], [120] * 7)
        self.assertEqual(result['normal'], dict.fromkeys(plush_test.IDS, 2898))
        self.assertEqual(result['boundary'], [True, False])
        self.assertFalse(result['unknownValid'])

    def test_free_replacement_uses_same_distribution_for_both_profiles_without_spends(self):
        self.install()
        before = self.snapshot()
        result = self.page.evaluate("""async()=>{
          const saved=Math.random,rows=[];
          try {
            for(const who of ['student','test']) {
              let board=await readOne('arcadeBoards',who);
              for(let b=0;b<10;b++)for(let t=0;t<3;t++)for(let s=0;s<7;s++) {
                const values=[(b+.5)/10,...Array(7).fill(.5),(t+.5)/3,(s+.5)/7];
                Math.random=()=>values.shift();board=await replaceCraneBoard(who,board.slots);
                rows.push({who,slots:board.slots});
              }
            }
          } finally {Math.random=saved;}
          return rows;
        }""")
        for who in ['student', 'test']:
            secret_boards = [r['slots'] for r in result if r['who'] == who and any(x in SECRETS for x in r['slots'])]
            self.assertEqual(len(secret_boards), 21)
            self.assertTrue(all(sum(x in SECRETS for x in row) == 1 for row in secret_boards))
            for prize_id in SECRETS:
                self.assertEqual(sum(prize_id in row for row in secret_boards), 7)
            for slot in range(7):
                self.assertEqual(sum(row[slot] in SECRETS for row in secret_boards), 3)
        after = self.snapshot()
        for store in before:
            if store != 'arcadeBoards':
                self.assertEqual(after[store], before[store], store)

    def test_saved_normal_and_secret_boards_are_never_redrawn(self):
        self.install()
        self.page.evaluate("""async()=>{
          const tx=db.transaction('arcadeBoards','readwrite');
          tx.objectStore('arcadeBoards').put({profile:'student',slots:Array(7).fill('rabbit')});
          await new Promise((resolve,reject)=>{tx.oncomplete=resolve;tx.onabort=()=>reject(tx.error);});
        }""")
        before = self.snapshot()
        self.page.reload()
        self.ready()
        self.page.evaluate("""async()=>{
          const random=Math.random;Math.random=()=>{throw Error('保存済み盤面を再抽選した');};
          try {await ensureArcadeBoards();await openArcade();await ensureArcadeBoards();}
          finally {Math.random=random;}
        }""")
        self.assertEqual(self.snapshot(), before)

    def test_all_normal_prizes_keep_grab_and_carry_boundaries_for_each_band(self):
        result = self.page.evaluate("""()=>PLUSH_IDS.flatMap(id=>[
          [0,.90,.84],[3,.75,.67],[5,.38,.53]
        ].map(([offset,grab,carry])=>{
          const play={prizes:['secret_koryun',id,...Array(5).fill('bear')],armX:26+offset};
          const test=values=>chooseCraneOutcome(play,()=>values.shift()??0);
          return [test([grab-1e-9,carry-1e-9]).won,test([grab,0]).grabbed,
            test([0,carry]).won,test([0,carry-1e-9]).targetIndex];
        }))""")
        self.assertEqual(result, [[True, False, False, 1]] * 60)

    def test_only_actual_target_secret_gets_ninety_percent_carry_and_same_grab(self):
        result = self.page.evaluate("""()=>SECRET_PLUSH_IDS.flatMap(id=>[
          [0,.90,.84],[3,.75,.67],[5,.38,.53]
        ].map(([offset,grab,carry])=>{
          const play={prizes:['bear',id,...Array(5).fill('bear')],armX:26+offset};
          const test=values=>chooseCraneOutcome(play,()=>values.shift()??0);
          return [test([grab-1e-9,carry*.9-1e-9]).won,test([grab,0]).grabbed,
            test([0,carry*.9]).won,test([0,carry*.95]).won];
        }))""")
        self.assertEqual(result, [[True, False, False, False]] * 9)
        self.assertEqual(self.page.evaluate("""()=>{
          let calls=0;const random=()=>{calls++;return 0;};
          const empty=chooseCraneOutcome({prizes:Array(7).fill(null),armX:50},random);
          const miss=chooseCraneOutcome({prizes:Array(7).fill('bear'),armX:20},random);
          return [calls,empty.won,miss.won];
        }"""), [0, False, False])

    def test_unowned_secrets_have_identical_images_names_alt_and_no_id_hooks(self):
        self.install()
        self.assert_hidden()
        items = self.page.locator('#arcade-secret-collection-list .plush-item')
        self.assertEqual(items.count(), 3)
        markup = items.evaluate_all('els=>els.map(el=>el.outerHTML)')
        self.assertEqual(markup, [markup[0]] * 3)
        self.assertEqual(items.locator('strong').all_text_contents(), ['？？？'] * 3)
        self.assertEqual(items.locator('.owned').all_text_contents(), ['未獲得'] * 3)
        self.assertEqual(items.locator('[data-prize-id]').count(), 0)

    def test_collection_home_counts_profiles_and_shared_owned_item_structure(self):
        self.install(owned=['shiba', 'shiba', 'secret_yuniko', 'secret_yuniko'])
        self.page.evaluate('refreshArcadeHome()')
        self.assertIn('通常：1/20種類 ／ 2体', self.page.locator('#arcade-collection-count').inner_text())
        self.assertIn('シークレット：1/3種類 ／ 2体', self.page.locator('#arcade-secret-collection-count').inner_text())
        self.assertIn('通常：1/20種類 ／ シークレット：1/3種類', self.page.locator('#arcade-home-status').inner_text())
        self.assertEqual(self.page.locator('#arcade-secret-collection-list strong').all_text_contents(), ['？？？', 'ゆにこ', '？？？'])
        self.assertEqual(self.page.locator('#arcade-secret-collection-list [data-prize-id]').get_attribute('data-prize-id'), 'secret_yuniko')
        self.assertEqual(self.page.locator('.plush-item[data-prize-id="shiba"] .owned').inner_text(), '×2')
        self.page.evaluate("async()=>{profile='student';await renderArcade();await refreshArcadeHome();}")
        self.assertIn('通常：0/20種類', self.page.locator('#arcade-home-status').inner_text())
        self.assertIn('シークレット：0/3種類', self.page.locator('#arcade-secret-collection-count').inner_text())
        self.assertEqual(self.page.locator('#arcade-secret-collection-list strong').all_text_contents(), ['？？？'] * 3)

    def test_normal_complete_and_secret_complete_are_independent(self):
        self.install(owned=plush_test.IDS)
        self.assertIn('20/20種類', self.page.locator('#arcade-collection-count').inner_text())
        self.assertIn('コンプリート', self.page.locator('#arcade-collection-count').inner_text())
        self.assertIn('0/3種類', self.page.locator('#arcade-secret-collection-count').inner_text())
        self.install(owned=SECRETS)
        self.assertIn('0/20種類', self.page.locator('#arcade-collection-count').inner_text())
        self.assertNotIn('コンプリート', self.page.locator('#arcade-collection-count').inner_text())
        self.assertIn('3/3種類', self.page.locator('#arcade-secret-collection-count').inner_text())
        self.assertIn('コンプリート', self.page.locator('#arcade-secret-collection-count').inner_text())

    def test_grab_transport_delivery_miss_and_drop_always_keep_unknown_until_save(self):
        for secret in SECRETS:
            for outcome in ['win', 'miss', 'drop']:
                with self.subTest(secret=secret, outcome=outcome):
                    self.prepare('resolving', outcome, secret=secret)
                    states = self.page.evaluate("""async()=>{
                      arcadeResumeRequired=false;
                      const states=[],observer=new MutationObserver(()=>states.push(secretUI()));
                      observer.observe(document.querySelector('#arcade'),{subtree:true,childList:true,characterData:true,attributes:true});
                      const restore=fastCrane();
                      try {await animateCraneOutcome(arcadePlay);states.push(secretUI());}
                      finally {observer.disconnect();restore();}
                      return states;
                    }""")
                    for state in states:
                        self.assert_hidden(state)
                    self.assertTrue(any('dropping' in state['stage'] for state in states))
                    if outcome != 'miss':
                        self.assertTrue(any('grabbed' in state['toy'] for state in states))
                        self.assertTrue(any('transporting' in state['stage'] for state in states))
                        end_class = 'delivered' if outcome == 'win' else 'fallen'
                        self.assertTrue(any(end_class in state['toy'] for state in states))
                    self.assertEqual(self.page.evaluate("readAll('arcadePrizes')"), [])

    def test_previously_owned_secret_still_uses_unknown_in_machine(self):
        self.install(owned=['secret_koryun'])
        self.assertEqual(self.page.locator('.crane-toy[data-slot="3"] img').get_attribute('src'), UNKNOWN)
        self.assertEqual(self.page.locator('.crane-toy[data-slot="3"] img').get_attribute('alt'), '？？？')
        self.assertEqual(self.page.locator('#arcade-secret-collection-list strong').first.inner_text(), 'こりゅん')

    def test_reveal_waits_for_transaction_success_then_unknown_intro_then_identity(self):
        play_id = self.prepare()
        self.page.evaluate("""async()=>{
          arcadeResumeRequired=false;await renderArcade();stopCraneSweep();arcadePlay.armX=50;
          window.savedFinish=finishCranePlay;window.savedTimer=window.setTimeout;
          window.savedRandom=Math.random;Math.random=()=>0;
          finishCranePlay=async id=>{window.finishing=true;await new Promise(resolve=>window.allowFinish=resolve);
            const play=await savedFinish(id);window.committed=true;return play;};
          window.setTimeout=(fn,ms,...args)=>{
            if(ms===SECRET_REVEAL_MS.hidden){window.allowIdentity=fn;return 0;}
            if(ms===SECRET_REVEAL_MS.revealed){window.endReveal=fn;return 0;}
            return savedTimer(fn,0,...args);
          };
          window.catching=catchCrane();
        }""")
        self.page.wait_for_function('window.finishing')
        self.assert_hidden()
        self.assertFalse(self.page.locator('#crane-secret-reveal').is_visible())
        self.assertEqual(self.page.evaluate("id=>readOne('arcadePlays',id)", play_id)['status'], 'resolving')
        self.assertEqual(self.page.evaluate("readAll('arcadePrizes')"), [])
        self.page.evaluate('allowFinish()')
        self.page.wait_for_function('window.allowIdentity!==undefined')
        self.assertTrue(self.page.evaluate('window.committed'))
        self.assertIn('🎉 シークレットゲット！', self.page.locator('#crane-secret-reveal').inner_text())
        self.assertTrue(self.page.locator('#crane-secret-reveal').evaluate('el=>{const r=el.getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight;}'))
        self.assert_hidden()
        saved = self.snapshot()
        self.assertEqual(saved['arcadePlays'][0]['status'], 'finished')
        self.assertEqual(saved['arcadePrizes'][0]['prizeId'], 'secret_koryun')
        self.assertIsNone(self.board()['slots'][3])
        self.page.evaluate('allowIdentity()')
        self.page.wait_for_function('window.endReveal!==undefined')
        self.assertEqual(self.page.locator('#crane-secret-reveal img').get_attribute('src'), 'assets/plush/secret_koryun.webp')
        self.assertIn('こりゅん', self.page.locator('#crane-secret-reveal').inner_text())
        self.page.evaluate('async()=>{endReveal();await catching;finishCranePlay=savedFinish;window.setTimeout=savedTimer;Math.random=savedRandom;}')
        self.assertEqual(self.snapshot(), saved)

    def test_transaction_abort_hides_identity_rolls_back_and_manual_retry_awards_once(self):
        play_id = self.prepare('resolving', who='student')
        before = self.snapshot()
        self.page.evaluate("""async()=>{
          const add=IDBObjectStore.prototype.add,restore=fastCrane();
          IDBObjectStore.prototype.add=function(value,...args){
            if(this.name==='arcadePrizes')add.call(this,value,...args);
            return add.call(this,value,...args);
          };
          try {await startCrane();}finally{IDBObjectStore.prototype.add=add;restore();}
        }""")
        self.assertEqual(self.snapshot(), before)
        self.assert_hidden()
        self.assertFalse(self.page.locator('#crane-secret-reveal').is_visible())
        self.assertFalse(self.page.locator('#crane-start').is_disabled())
        self.page.evaluate("""async()=>{
          const choose=chooseCraneOutcome,restore=fastCrane();
          chooseCraneOutcome=()=>{throw Error('保存済み結果を再抽選した');};
          try {await Promise.all([startCrane(),startCrane(),startCrane()]);}
          finally {chooseCraneOutcome=choose;restore();}
        }""")
        self.page.evaluate('id=>Promise.all([finishCranePlay(id),finishCranePlay(id)])', play_id)
        after = self.snapshot()
        self.assertEqual(after['coinSpends'], before['coinSpends'])
        self.assertEqual(len(after['arcadePrizes']), 1)
        self.assertEqual(after['arcadePrizes'][0]['prizeId'], 'secret_koryun')
        self.assertIsNone(self.board('student')['slots'][3])
        self.assertIn('こりゅん', self.page.locator('#crane-secret-reveal').inner_text())

    def test_aiming_and_resolving_reload_are_manual_hidden_and_do_not_reroll(self):
        for status, outcome in [('aiming', 'win'), ('resolving', 'win'), ('resolving', 'drop'), ('resolving', 'miss')]:
            with self.subTest(status=status, outcome=outcome):
                play_id = self.prepare(status, outcome)
                before = self.snapshot()
                self.page.reload()
                self.ready()
                self.page.evaluate("async()=>{profile='test';await openArcade();}")
                self.assert_hidden()
                self.assertTrue(self.page.locator('#crane-catch').is_disabled())
                self.assertIsNone(self.page.evaluate('arcadeSweepFrame'))
                self.assertEqual(self.snapshot(), before)
                self.page.evaluate("""async status=>{
                  const choose=chooseCraneOutcome,restore=fastCrane();let calls=0;
                  chooseCraneOutcome=play=>{calls++;if(status==='resolving')throw Error('再抽選した');return choose(play,()=>0);};
                  try {
                    await startCrane();
                    if(status==='aiming'){stopCraneSweep();arcadePlay.armX=50;await catchCrane();}
                    window.outcomeCalls=calls;
                  }finally{chooseCraneOutcome=choose;restore();}
                }""", status)
                self.assertEqual(self.page.evaluate('window.outcomeCalls'), 1 if status == 'aiming' else 0)
                self.assertEqual(self.snapshot()['coinSpends'], before['coinSpends'])
                self.assertEqual(self.page.evaluate("id=>readOne('arcadePlays',id)", play_id)['status'], 'finished')
                if outcome == 'win':
                    self.assertEqual(len(self.snapshot()['arcadePrizes']), 1)
                else:
                    self.assertEqual(self.snapshot()['arcadePrizes'], [])
                    self.assert_hidden()

    def test_finished_play_reload_shows_static_identity_without_second_award(self):
        play_id = self.prepare('resolving')
        self.page.evaluate('id=>finishCranePlay(id)', play_id)
        before = self.snapshot()
        self.page.reload()
        self.ready()
        self.page.evaluate("async()=>{profile='test';await openArcade();}")
        self.assertIn('こりゅん', self.page.locator('#crane-secret-reveal').inner_text())
        self.assertEqual(self.page.locator('#crane-secret-reveal img').evaluate('img=>getComputedStyle(img).animationName'), 'none')
        self.assertEqual(self.snapshot(), before)
        self.page.evaluate('id=>Promise.all([finishCranePlay(id),finishCranePlay(id)])', play_id)
        self.assertEqual(self.snapshot(), before)

    def test_history_back_during_secret_transport_keeps_manual_unknown_result(self):
        self.prepare(who='student')
        self.page.evaluate("""async()=>{
          await startCrane();stopCraneSweep();arcadePlay.armX=50;
          window.savedRandom=Math.random;Math.random=()=>0;window.catching=catchCrane();
        }""")
        self.page.wait_for_function("arcadePlay.status==='resolving'")
        self.page.go_back()
        self.page.wait_for_function("!document.querySelector('#home').classList.contains('hidden')")
        self.page.evaluate('async()=>{await catching;Math.random=savedRandom;}')
        before = self.snapshot()
        self.assertEqual(before['arcadePlays'][0]['status'], 'resolving')
        self.assertEqual(before['arcadePrizes'], [])
        self.page.go_forward()
        self.page.wait_for_function("arcadeResumeRequired&&arcadePlay?.status==='resolving'&&!arcadeBusy")
        self.page.wait_for_function("document.querySelector('#crane-start').textContent.includes('追加料金なし')")
        self.assertTrue(self.page.locator('#crane-start').is_visible())
        self.assertFalse(self.page.locator('#crane-start').is_disabled())
        self.assert_hidden()
        self.assertEqual(self.snapshot(), before)
        self.page.evaluate("""async()=>{
          const choose=chooseCraneOutcome,restore=fastCrane();
          chooseCraneOutcome=()=>{throw Error('履歴復帰で再抽選した');};
          try{await startCrane();}finally{chooseCraneOutcome=choose;restore();}
        }""")
        after = self.snapshot()
        self.assertEqual(after['coinSpends'], before['coinSpends'])
        self.assertEqual([r['amount'] for r in after['coinSpends']], [100])
        self.assertEqual(after['arcadePlays'][0]['result'], before['arcadePlays'][0]['result'])
        self.assertEqual(len(after['arcadePrizes']), 1)
        self.assertIn('こりゅん', self.page.locator('#crane-secret-reveal').inner_text())
        self.page.evaluate('id=>Promise.all([finishCranePlay(id),finishCranePlay(id)])', after['arcadePlays'][0]['id'])
        self.assertEqual(self.snapshot(), after)

    def test_secret_award_history_profiles_reload_backup_stay_consistent(self):
        self.prepare()
        self.page.evaluate("""async()=>{
          await startCrane();stopCraneSweep();arcadePlay.armX=50;
          window.savedRandom=Math.random;Math.random=()=>0;
          window.savedAnimation=animateCraneOutcome;animateCraneOutcome=async()=>{};
          window.savedTimer=window.setTimeout;window.lateReveal=false;
          window.setTimeout=(fn,ms,...args)=>{
            if(ms===SECRET_REVEAL_MS.hidden){window.allowIdentity=fn;return 0;}
            if(ms===SECRET_REVEAL_MS.revealed)window.lateReveal=true;
            return savedTimer(fn,0,...args);
          };
          window.catching=catchCrane();
        }""")
        self.page.wait_for_function('window.allowIdentity!==undefined')
        before = self.snapshot()
        self.page.evaluate("navigate('arcade','student')")
        self.assertEqual(self.page.locator('#arcade-secret-collection-list strong').all_text_contents(), ['？？？'] * 3)
        self.assertFalse(self.page.locator('#crane-secret-reveal').is_visible())
        self.assertNotIn('こりゅん', self.page.locator('#arcade').inner_text())
        self.page.evaluate("navigate('arcade','test')")
        self.assertIn('こりゅん', self.page.locator('#crane-secret-reveal').inner_text())
        self.assertEqual(self.page.locator('#crane-secret-reveal img').evaluate('img=>getComputedStyle(img).animationName'), 'none')
        self.page.evaluate("""async()=>{
          allowIdentity();await catching;Math.random=savedRandom;
          animateCraneOutcome=savedAnimation;window.setTimeout=savedTimer;
        }""")
        self.assertFalse(self.page.evaluate('window.lateReveal'))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.page.locator('#crane-secret-reveal img').evaluate('img=>getComputedStyle(img).animationName'), 'none')
        self.page.reload()
        self.ready()
        self.assertIn('こりゅん', self.page.locator('#crane-secret-reveal').inner_text())
        self.assertEqual(self.page.locator('#arcade-secret-collection-list [data-prize-id="secret_koryun"] .owned').inner_text(), '×1')
        self.page.evaluate("navigate('arcade','student')")
        self.assertEqual(self.page.locator('#arcade-secret-collection-list strong').all_text_contents(), ['？？？'] * 3)
        self.page.go_back()
        self.page.wait_for_function("profile==='test'&&document.querySelector('#arcade-secret-collection-count').textContent.includes('1/3種類')")
        self.assertEqual(self.page.locator('#crane-secret-reveal img').get_attribute('src'), 'assets/plush/secret_koryun.webp')
        self.page.go_forward()
        self.page.wait_for_function("profile==='student'&&document.querySelector('#arcade-secret-collection-count').textContent.includes('0/3種類')")
        self.assertEqual(self.snapshot(), before)
        self.page.locator('#open-admin').click()
        if not self.page.locator('#admin-backup-group').evaluate('el=>el.open'):
            self.page.locator('#admin-backup-group > summary').click()
        self.page.locator('#toggle-backup').click()
        with self.page.expect_download() as event:
            self.page.locator('#backup-export').click()
        backup = json.loads(Path(event.value.path()).read_text())
        self.assertEqual(backup['backupVersion'], 9)
        self.assertEqual(backup['data'], before)
        self.page.evaluate('async()=>{await plushInstall(plushFixture());}')
        self.page.locator('#backup-file').set_input_files({
            'name': 'synthetic-integration-v7.json', 'mimeType': 'application/json', 'buffer': json.dumps(backup).encode()})
        self.page.wait_for_function("document.querySelector('#backup-preview').textContent.startsWith('検査OK')")
        self.page.locator('#backup-restore').click()
        self.page.wait_for_function('!backingUp&&pendingRestore===null')
        self.assertEqual(self.snapshot(), before, '回答・習得・コインを含む14ストアを保持')
        self.assertEqual(self.page.evaluate('[profile,history.state.profile]'), ['student', 'student'])
        self.page.evaluate("navigate('arcade','test')")
        self.assertEqual(self.page.locator('#crane-secret-reveal img').get_attribute('src'), 'assets/plush/secret_koryun.webp')
        self.assertEqual(self.page.locator('#arcade-secret-collection-list [data-prize-id="secret_koryun"] .owned').inner_text(), '×1')
        self.assertEqual(self.snapshot(), before)

    def test_process_close_and_reopen_preserves_hidden_resolving_secret_and_charge(self):
        executable = os.environ.get('HISTORY_MASTER_BROWSER') or shutil.which('chromium')
        with tempfile.TemporaryDirectory(prefix='history-secret-test-') as directory:
            first = self.playwright.chromium.launch_persistent_context(directory, executable_path=executable)
            page = first.new_page()
            page.goto(self.url)
            page.wait_for_function('appReady')
            page.evaluate(plush_test.FIXTURE_HELPERS)
            page.evaluate("""async slots=>{
              const data=plushFixture();data.arcadeBoards.find(b=>b.profile==='student').slots=slots;
              await plushInstall(data);const p=await purchaseCranePlay(newArcadePlay('student'));p.armX=50;
              await commitCraneOutcome(p,chooseCraneOutcome(p,()=>0));
            }""", SLOTS)
            before = page.evaluate('snapshotAllStores()')
            first.close()
            second = self.playwright.chromium.launch_persistent_context(directory, executable_path=executable)
            try:
                page = second.new_page()
                page.goto(self.url)
                page.wait_for_function('appReady')
                page.evaluate('openArcade()')
                self.assertEqual(page.locator('.crane-toy[data-slot="3"] img').get_attribute('src'), UNKNOWN)
                self.assertTrue(page.evaluate('arcadeResumeRequired'))
                self.assertIsNone(page.evaluate('arcadeSweepFrame'))
                self.assertEqual(page.evaluate('snapshotAllStores()'), before)
                self.assertNotIn('こりゅん', page.locator('#arcade').inner_text())
            finally:
                second.close()

    def test_v7_download_preview_restore_preserves_all_secret_ids_pending_and_fourteen_stores(self):
        self.page.evaluate("""async()=>{
          const data=secretFixture(SECRET_PLUSH_IDS);
          data.arcadeBoards.find(b=>b.profile==='student').slots=[null,'bear','rabbit','secret_kappamaru','seal',null,'star'];
          await plushInstall(data);
          const p=await purchaseCranePlay(newArcadePlay('student'));p.armX=50;
          await commitCraneOutcome(p,chooseCraneOutcome(p,()=>0));
        }""")
        before = self.snapshot()
        self.assertEqual(len(before), 16)
        self.page.locator('#open-admin').click()
        if not self.page.locator('#admin-backup-group').evaluate('el=>el.open'):
            self.page.locator('#admin-backup-group > summary').click()
        self.page.locator('#toggle-backup').click()
        with self.page.expect_download() as event:
            self.page.locator('#backup-export').click()
        backup = json.loads(Path(event.value.path()).read_text())
        self.assertEqual((backup['backupVersion'], self.page.evaluate('DB_VERSION')), (9, 9))
        self.assertEqual(backup['data'], before)
        self.assertNotIn('secret_unknown', json.dumps(backup))
        self.page.evaluate('async()=>{await plushInstall(plushFixture());}')
        cleared = self.snapshot()
        self.page.locator('#backup-file').set_input_files({
            'name': 'synthetic-secret-v7.json', 'mimeType': 'application/json', 'buffer': json.dumps(backup).encode()})
        self.page.wait_for_function("document.querySelector('#backup-preview').textContent.startsWith('検査OK')")
        self.assertEqual(self.snapshot(), cleared)
        self.page.locator('#backup-restore').click()
        self.page.wait_for_function('!backingUp && pendingRestore===null')
        self.assertEqual(self.snapshot(), before)
        self.page.reload()
        self.ready()
        self.assertEqual(self.snapshot(), before)
        self.page.evaluate('openArcade()')
        self.assert_hidden()

    def test_backup_rejects_display_only_and_unregistered_secret_ids(self):
        self.install()
        data = self.snapshot()
        for invalid in ['secret_unknown', 'secret_fake']:
            copy = json.loads(json.dumps(data))
            copy['arcadeBoards'][0]['slots'][0] = invalid
            self.assertTrue(self.page.evaluate("""data=>{
              try{validateBackup({backupFormat:BACKUP_FORMAT,backupVersion:7,data});return false;}catch{return true;}
            }""", copy))
        self.assertEqual(self.snapshot(), data)

    def test_official_four_webps_decode_with_transparent_background(self):
        for asset_id in [*SECRETS, 'secret_unknown']:
            data = (plush_test.ROOT / 'assets' / 'plush' / f'{asset_id}.webp').read_bytes()
            self.assertEqual(data[:4], b'RIFF')
            self.assertEqual(data[8:12], b'WEBP')
        images = self.page.evaluate("""async()=>Promise.all([...SECRET_PLUSH_IDS,'secret_unknown'].map(async id=>{
          const img=new Image();img.src=plushPath(id);await img.decode();
          const canvas=document.createElement('canvas');canvas.width=img.naturalWidth;canvas.height=img.naturalHeight;
          const ctx=canvas.getContext('2d');ctx.drawImage(img,0,0);
          const data=ctx.getImageData(0,0,canvas.width,canvas.height).data;let min=255,max=0;
          for(let i=3;i<data.length;i+=4){min=Math.min(min,data[i]);max=Math.max(max,data[i]);}
          return [img.naturalWidth,img.naturalHeight,min,max,data[3]];
        }))""")
        self.assertEqual(images, [[1024, 1024, 0, 255, 0]] * 4)

    def test_iphone_ipad_reveal_collection_and_reduced_motion_fit(self):
        self.install(owned=SECRETS)
        for width, height in [(375, 812), (390, 844), (1024, 768), (1180, 820)]:
            with self.subTest(width=width):
                self.page.set_viewport_size({'width': width, 'height': height})
                self.page.evaluate('paintCranePrizeResult(arcadePlay,true,true)')
                for img in self.page.locator('#crane-secret-reveal img, #arcade-secret-collection-list img').all():
                    img.scroll_into_view_if_needed()
                    img.evaluate('img=>img.decode()')
                self.assertTrue(self.page.evaluate("""()=>document.documentElement.scrollWidth<=innerWidth&&
                  [...document.querySelectorAll('#crane-secret-reveal,#arcade-secret-collection-list')].every(el=>{
                    const r=el.getBoundingClientRect();return r.width>0&&r.left>=0&&r.right<=innerWidth;
                  })"""))
        self.page.emulate_media(reduced_motion='reduce')
        self.assertEqual(self.page.locator('#crane-secret-reveal img').evaluate('img=>getComputedStyle(img).animationName'), 'none')
        self.assertEqual(self.page.evaluate('SECRET_REVEAL_MS.hidden+SECRET_REVEAL_MS.revealed'), 2400)


    def test_normal_win_shows_image_after_saved_result_and_not_on_failure(self):
        """通常景品も獲得後に画像と名前を表示。失敗・プロフィール違いでは非表示。"""
        play_id = self.prepare('resolving', secret='shiba')
        self.assertFalse(self.page.locator('#crane-secret-reveal').is_visible())
        self.page.evaluate('id=>finishCranePlay(id)', play_id)
        saved = self.snapshot()
        self.page.evaluate('renderArcade()')
        self.assertEqual(self.page.locator('#arcade-message').text_content(), '🎉 しば犬をゲット！')
        panel = self.page.locator('#crane-secret-reveal')
        self.assertTrue(panel.is_visible())
        self.assertEqual(panel.locator('img').get_attribute('src'), 'assets/plush/shiba.webp')
        self.assertEqual(panel.locator('img').get_attribute('alt'), 'しば犬')
        self.assertEqual(panel.locator('strong').all_text_contents(), ['しば犬'])
        panel.locator('img').evaluate('img=>img.decode()')
        for width, height in [(375, 812), (390, 844), (768, 1024), (1024, 768)]:
            with self.subTest(width=width):
                self.page.set_viewport_size({'width': width, 'height': height})
                self.assertTrue(self.page.evaluate("""()=>{
                  const msg=document.querySelector('#arcade-message').getBoundingClientRect();
                  const img=document.querySelector('#crane-secret-reveal img').getBoundingClientRect();
                  return img.top>=msg.bottom&&img.width>0&&img.right<=innerWidth&&
                    document.documentElement.scrollWidth<=innerWidth;
                }"""))
        self.assertEqual(self.snapshot(), saved)
        self.page.reload()
        self.ready()
        self.page.evaluate("async()=>{profile='test';await openArcade();}")
        self.assertEqual(self.page.locator('#crane-secret-reveal img').get_attribute('src'), 'assets/plush/shiba.webp')
        self.assertEqual(self.page.locator('#crane-secret-reveal img').evaluate('img=>getComputedStyle(img).animationName'), 'none')
        self.assertEqual(self.snapshot(), saved)
        self.page.evaluate("async()=>{profile='student';await renderArcade();}")
        self.assertFalse(panel.is_visible())
        self.page.evaluate("async()=>{profile='test';await renderArcade();}")
        self.assertEqual(panel.locator('img').get_attribute('src'), 'assets/plush/shiba.webp')

        self.prepare('resolving', outcome='miss', secret='shiba')
        self.page.evaluate('id=>finishCranePlay(id)', self.page.evaluate('arcadePlay.id'))
        self.page.evaluate('renderArcade()')
        self.assertFalse(panel.is_visible())


if __name__ == '__main__':
    unittest.main()
