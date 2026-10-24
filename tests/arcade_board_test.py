"""v1.6.7の永続盤面・取引・移行テスト。公開可能な架空データのみ使用。

実行方法はquestion_editor_test.pyと同じ。localhostと一時ブラウザだけを使う。
"""

import functools
import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest

from playwright.sync_api import sync_playwright
import plush_test


ROOT = plush_test.ROOT
SLOTS = ['shiba', 'rabbit', 'shiba', 'star', 'bear', 'seal', 'cloud']
EMPTY_MESSAGE = '景品がなくなったよ！『景品を入れ替える』で新しくしよう！'


class ArcadeBoardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(
            ('127.0.0.1', 0), functools.partial(plush_test.QuietHandler, directory=str(ROOT)))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.playwright = sync_playwright().start()
        executable = os.environ.get('HISTORY_MASTER_BROWSER') or shutil.which('chromium')
        cls.browser = cls.playwright.chromium.launch(executable_path=executable)
        cls.url = f'http://127.0.0.1:{cls.server.server_port}/index.html'

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.context = self.browser.new_context(viewport={'width': 390, 'height': 844}, has_touch=True)
        self.page = self.context.new_page()
        self.page.set_default_timeout(7000)
        self.errors = []
        self.dialogs = []
        self.cancel_dialog = False
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.on('dialog', self.on_dialog)
        self.page.goto(self.url)
        self.ready()

    def ready(self):
        self.page.wait_for_function("(typeof appReady==='undefined'?document.querySelectorAll('#era-list button').length===10:appReady)")
        self.page.evaluate(plush_test.FIXTURE_HELPERS)

    def on_dialog(self, dialog):
        self.dialogs.append(dialog.message)
        if self.cancel_dialog:
            dialog.dismiss()
        elif dialog.type == 'prompt':
            dialog.accept('初期化')
        else:
            dialog.accept()

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.errors, [])

    def snapshot(self):
        return self.page.evaluate('snapshotAllStores()')

    def install(self, slots=SLOTS, who='test'):
        self.page.evaluate("""async ({slots,who})=>{
          const data=plushFixture();
          data.arcadeBoards.find(b=>b.profile===who).slots=slots;
          await plushInstall(data);profile=who;await openArcade();
        }""", {'slots': slots, 'who': who})

    def board(self, who='test'):
        return self.page.evaluate("who=>readOne('arcadeBoards',who)", who)

    def replace_prizes_and_wait(self):
        # arcadeBusyはfinallyの再描画より先に解除されるため、操作全体を待つ。
        self.page.evaluate("""()=>{
          window.originalReplacement=replaceArcadePrizes;
          replaceArcadePrizes=(...args)=>window.boardReplacement=originalReplacement(...args);
        }""")
        self.page.locator('#crane-replace').click()
        self.page.evaluate("""async()=>{
          try {await boardReplacement;}
          finally {replaceArcadePrizes=originalReplacement;}
        }""")

    def round(self, slot=0, outcome='win'):
        return self.page.evaluate("""async ({slot,outcome})=>{
          const play=await purchaseCranePlay(newArcadePlay(profile));
          play.armX=NEW_PRIZE_POSITIONS[slot];
          const values=outcome==='drop'?[0,.999,.5]:outcome==='miss'?[.999]:[0,0];
          const result=chooseCraneOutcome(play,()=>values.shift()??0);
          await commitCraneOutcome(play,result);
          const finished=await finishCranePlay(play.id);
          await renderArcade();return finished;
        }""", {'slot': slot, 'outcome': outcome})

    def test_first_board_saved_once_and_visible_before_play(self):
        initial = self.snapshot()
        self.assertEqual(len(initial['arcadeBoards']), 2)
        for board in initial['arcadeBoards']:
            self.assertEqual(len(board['slots']), 7)
            self.assertTrue(all(prize in plush_test.IDS + ['secret_koryun', 'secret_yuniko', 'secret_kappamaru'] for prize in board['slots']))
        self.page.evaluate('openArcade()')
        self.assertEqual(self.page.locator('.crane-toy').count(), 7)
        self.assertIsNone(self.page.evaluate('arcadePlay'))
        self.page.evaluate('async()=>{await ensureArcadeBoards();await ensureArcadeBoards();}')
        self.page.reload()
        self.ready()
        self.assertEqual(self.snapshot(), initial)
        self.page.evaluate('openArcade()')
        self.assertEqual(self.page.locator('.crane-toy img').evaluate_all(
            'imgs=>imgs.map(img=>img.getAttribute("src").split("/").pop().replace(".webp",""))'),
            ['secret_unknown' if prize.startswith('secret_') else prize
             for prize in next(b['slots'] for b in initial['arcadeBoards'] if b['profile'] == 'student')])

    def test_win_clears_only_target_duplicate_and_next_snapshot_keeps_null(self):
        self.install()
        play = self.round(2)
        expected = SLOTS[:]
        expected[2] = None
        self.assertEqual(self.board()['slots'], expected)
        self.assertEqual(play['prizes'], SLOTS)
        self.assertEqual(self.page.locator('.crane-toy').evaluate_all('els=>els.map(el=>+el.dataset.slot)'),
                         [0, 1, 3, 4, 5, 6])
        again = self.round(2)
        self.assertEqual(again['prizes'], expected)
        self.assertFalse(again['result']['grabbed'])
        self.assertFalse(again['result']['won'])
        self.assertEqual(self.board()['slots'], expected)
        self.assertEqual(len(self.snapshot()['arcadePrizes']), 1)
        self.assertEqual(self.page.evaluate("id=>readOne('arcadePlays',id)", play['id'])['prizes'], SLOTS)
        self.page.evaluate('data=>validateBackup({backupFormat:BACKUP_FORMAT,backupVersion:7,data})', self.snapshot())

    def test_miss_and_transport_drop_leave_entire_board_unchanged(self):
        self.install()
        for outcome in ['miss', 'drop']:
            with self.subTest(outcome=outcome):
                before = self.board()
                play = self.round(1, outcome)
                self.assertFalse(play['result']['won'])
                self.assertEqual(play['result']['grabbed'], outcome == 'drop')
                self.assertEqual(self.board(), before)
        self.assertEqual(self.snapshot()['arcadePrizes'], [])

    def test_empty_target_never_grabs_neighbor_and_remaining_targets_work(self):
        slots = SLOTS[:]
        slots[3] = None
        self.install(slots)
        for x in [46, 49, 50, 51, 54]:
            result = self.page.evaluate('x=>chooseCraneOutcome({prizes:arcadeBoard.slots,armX:x},()=>0)', x)
            self.assertEqual(result['targetIndex'], 3)
            self.assertFalse(result['grabbed'])
            self.assertFalse(result['won'])
        won = self.round(4)
        self.assertTrue(won['result']['won'])
        slots[4] = None
        self.assertEqual(self.board()['slots'], slots)

    def test_all_empty_blocks_start_without_charge_or_confirmation_and_survives_reload(self):
        for who in ['student', 'test']:
            with self.subTest(profile=who):
                self.install([None] * 7, who)
                before = self.snapshot()
                self.assertTrue(self.page.locator('#crane-start').is_disabled())
                self.assertEqual(self.page.locator('#arcade-message').inner_text(), EMPTY_MESSAGE)
                self.assertEqual(self.page.locator('.crane-toy').count(), 0)
                self.page.evaluate('startCrane()')
                refused = self.page.evaluate("""async()=>{
                  try{await purchaseCranePlay(newArcadePlay(profile));return false;}catch{return true;}
                }""")
                self.assertTrue(refused)
                self.assertEqual(self.snapshot(), before)
                self.assertEqual(self.dialogs, [])
                self.page.reload()
                self.ready()
                self.assertEqual(self.snapshot(), before)

    def test_last_prize_win_disables_next_play_and_shows_empty_message(self):
        self.install([None, None, 'rabbit', None, None, None, None], 'student')
        self.round(2)
        self.assertEqual(self.board('student')['slots'], [None] * 7)
        self.assertTrue(self.page.locator('#crane-start').is_disabled())
        self.assertEqual(self.page.locator('#arcade-message').inner_text(), EMPTY_MESSAGE)
        before = self.snapshot()
        self.page.evaluate('startCrane()')
        self.assertEqual(self.snapshot(), before)

    def test_board_persists_after_browser_process_closes_and_reopens(self):
        executable = os.environ.get('HISTORY_MASTER_BROWSER') or shutil.which('chromium')
        with tempfile.TemporaryDirectory(prefix='history-board-test-') as directory:
            first = self.playwright.chromium.launch_persistent_context(directory, executable_path=executable)
            page = first.new_page()
            page.goto(self.url)
            page.wait_for_function("(typeof appReady==='undefined'?document.querySelectorAll('#era-list button').length===10:appReady)")
            page.evaluate("""async()=>{
              const tx=db.transaction('arcadeBoards','readwrite');
              tx.objectStore('arcadeBoards').put({profile:'student',slots:[null,'rabbit',null,'star',null,'seal',null]});
              tx.objectStore('arcadeBoards').put({profile:'test',slots:Array(7).fill(null)});
              await new Promise((resolve,reject)=>{tx.oncomplete=resolve;tx.onabort=()=>reject(tx.error);});
            }""")
            before = page.evaluate('snapshotAllStores()')
            first.close()
            second = self.playwright.chromium.launch_persistent_context(directory, executable_path=executable)
            try:
                page = second.new_page()
                page.goto(self.url)
                page.wait_for_function("(typeof appReady==='undefined'?document.querySelectorAll('#era-list button').length===10:appReady)")
                self.assertEqual(page.evaluate('snapshotAllStores()'), before)
                page.evaluate('openArcade()')
                self.assertEqual(page.locator('.crane-toy').count(), 3)
            finally:
                second.close()

    def test_swap_free_fills_seven_cancel_noop_and_empty_has_no_confirmation(self):
        for who in ['student', 'test']:
            with self.subTest(profile=who):
                self.install([None, *SLOTS[1:]], who)
                before = self.snapshot()
                self.cancel_dialog = True
                self.replace_prizes_and_wait()
                self.page.wait_for_function('!arcadeBusy')
                self.assertEqual(self.snapshot(), before)
                self.assertEqual(self.dialogs[-1], '今ある景品をすべて入れ替えますか？（無料）')
                self.cancel_dialog = False
                self.page.evaluate('window.originalRandom=Math.random;Math.random=()=>.999;')
                self.replace_prizes_and_wait()
                self.page.wait_for_function('!arcadeBusy')
                self.page.evaluate('Math.random=window.originalRandom')
                after = self.snapshot()
                self.assertEqual(self.board(who)['slots'], ['star'] * 7)
                for store in before:
                    if store != 'arcadeBoards':
                        self.assertEqual(after[store], before[store], store)
                other = 'student' if who == 'test' else 'test'
                self.assertEqual(next(b for b in before['arcadeBoards'] if b['profile'] == other), self.board(other))
        self.install([None] * 7)
        count = len(self.dialogs)
        # 通常景品を検証するこのケースでは、秘密の混入抽選を固定する。
        # 無固定だと既存の通常IDのassertが抽選次第で失敗する。
        self.page.evaluate('window.originalRandom=Math.random;Math.random=()=>.999;')
        try:
            self.replace_prizes_and_wait()
        finally:
            self.page.evaluate('Math.random=window.originalRandom')
        self.page.wait_for_function('!arcadeBusy')
        self.assertEqual(len(self.dialogs), count)
        self.assertTrue(all(p in plush_test.IDS for p in self.board()['slots']))

    def test_swap_disabled_during_play_resume_animation_save_and_rapid_taps(self):
        self.install()
        self.page.evaluate("""()=>{
          window.savedReplace=replaceCraneBoard;window.replaceCount=0;
          replaceCraneBoard=async(...args)=>{window.replaceCount++;
            await new Promise(resolve=>window.releaseReplace=resolve);return savedReplace(...args);};
          window.replacing=replaceArcadePrizes();
        }""")
        self.page.wait_for_function('window.releaseReplace!==undefined')
        self.assertTrue(self.page.locator('#crane-replace').is_disabled())
        self.assertTrue(self.page.locator('#crane-start').is_disabled())
        self.page.evaluate('async()=>{await Promise.all(Array.from({length:8},()=>replaceArcadePrizes()));}')
        self.assertEqual(self.page.evaluate('window.replaceCount'), 1)
        self.page.evaluate('async()=>{releaseReplace();await replacing;replaceCraneBoard=savedReplace;}')
        self.page.locator('#crane-start').click()
        self.page.wait_for_function("arcadePlay?.status==='aiming'&&!arcadeBusy")
        self.page.evaluate('stopCraneSweep()')
        self.assertTrue(self.page.locator('#crane-replace').is_disabled())
        before = self.board()
        self.page.evaluate('replaceArcadePrizes()')
        self.assertEqual(self.board(), before)
        self.page.reload()
        self.ready()
        self.page.evaluate("async()=>{profile='test';await openArcade();}")
        self.assertTrue(self.page.evaluate('arcadeResumeRequired'))
        self.assertTrue(self.page.locator('#crane-replace').is_disabled())
        self.page.evaluate('replaceArcadePrizes()')
        self.assertEqual(self.board(), before)
        self.page.locator('#crane-start').click()
        self.page.wait_for_function('!arcadeBusy')
        self.page.evaluate("""async()=>{
          stopCraneSweep();arcadePlay.armX=50;
          window.savedAnimation=animateCraneOutcome;
          animateCraneOutcome=()=>new Promise(resolve=>window.releaseAnimation=resolve);
          window.catching=catchCrane();
        }""")
        self.page.wait_for_function("arcadePlay.status==='resolving'&&window.releaseAnimation!==undefined")
        self.assertTrue(self.page.locator('#crane-replace').is_disabled())
        self.page.evaluate('replaceArcadePrizes()')
        self.assertEqual(self.board(), before)
        self.page.evaluate('async()=>{releaseAnimation();await catching;animateCraneOutcome=savedAnimation;}')
        self.assertFalse(self.page.locator('#crane-replace').is_disabled())

    def test_transactions_serialize_purchase_swap_and_stale_confirmation(self):
        self.install(who='student')
        outcomes = self.page.evaluate("""async()=>{
          const slots=[...arcadeBoard.slots];
          const results=await Promise.allSettled([purchaseCranePlay(newArcadePlay(profile)),
            purchaseCranePlay(newArcadePlay(profile)),replaceCraneBoard(profile,slots)]);
          return results.map(r=>r.status);
        }""")
        self.assertEqual(outcomes, ['fulfilled', 'rejected', 'rejected'])
        self.assertEqual(len(self.snapshot()['coinSpends']), 1)
        self.assertEqual(self.board('student')['slots'], SLOTS)
        self.install()
        self.assertTrue(self.page.evaluate("""async()=>{
          const original=[...arcadeBoard.slots],random=Math.random;
          Math.random=()=>.999;try{await replaceCraneBoard(profile,original);
            try{await replaceCraneBoard(profile,original);return false;}catch{return true;}
          }finally{Math.random=random;}
        }"""))

    def test_two_tabs_cannot_replace_an_active_board(self):
        self.install()
        other = self.context.new_page()
        other.goto(self.url)
        other.wait_for_function("(typeof appReady==='undefined'?document.querySelectorAll('#era-list button').length===10:appReady)")
        other.evaluate("async()=>{profile='test';await openArcade();}")
        self.page.locator('#crane-start').click()
        self.page.wait_for_function("arcadePlay?.status==='aiming'&&!arcadeBusy")
        self.page.evaluate('stopCraneSweep()')
        before = self.snapshot()
        other.evaluate('replaceArcadePrizes()')
        self.assertEqual(self.snapshot(), before)
        self.assertTrue(other.locator('#crane-replace').is_disabled())
        other.close()

    def test_legacy_backups_v1_through_v6_restore_without_previous_board_leaks(self):
        for version in range(1, 7):
            with self.subTest(version=version):
                self.install(['star'] * 7)
                data = self.page.evaluate("plushFixture(['shiba'],'student',7)")
                data.pop('arcadeBoards')
                if version < 5:
                    for name in ['reviewEvents', 'coinSpends', 'arcadePlays', 'arcadePrizes']:
                        data.pop(name)
                if version < 4:
                    for name in ['coinClaims', 'coinEvents', 'coinMeta']:
                        data.pop(name)
                if version < 3:
                    data.pop('sampleSettings')
                if version == 1:
                    data.pop('awards')
                before = self.snapshot()
                normalized = self.page.evaluate("""({data,version})=>
                  validateBackup({backupFormat:BACKUP_FORMAT,backupVersion:version,data})
                """, {'data': data, 'version': version})
                self.assertEqual(self.snapshot(), before)
                self.page.evaluate('async data=>{pendingRestore=data;await applyRestore();}', normalized)
                after = self.snapshot()
                for name in ['questions', 'progress', 'sessions', 'answers', 'awards', 'sampleSettings',
                             'coinClaims', 'coinEvents', 'reviewEvents', 'arcadePlays', 'arcadePrizes']:
                    if name in data:
                        self.assertEqual(sorted(after[name], key=lambda r: r.get('key', r.get('id', ''))),
                                         sorted(data[name], key=lambda r: r.get('key', r.get('id', ''))), name)
                if version >= 5:
                    self.assertEqual(self.board('student')['slots'], [None] + ['shiba'] * 6)
                self.assertEqual(after['arcadeBoards'], normalized['arcadeBoards'])
                self.page.reload()
                self.ready()
                self.assertEqual(self.snapshot(), after)

    def test_v7_download_preview_restore_reload_preserves_nulls_and_profiles(self):
        self.install([None, 'rabbit', None, 'star', None, 'seal', None], 'student')
        self.round(1, 'miss')
        self.page.evaluate("""async()=>{
          const tx=db.transaction('arcadeBoards','readwrite');
          tx.objectStore('arcadeBoards').put({profile:'test',slots:Array(7).fill(null)});
          await new Promise((resolve,reject)=>{tx.oncomplete=resolve;tx.onabort=()=>reject(tx.error);});
        }""")
        before = self.snapshot()
        self.page.locator('#open-admin').click()
        if not self.page.locator('#admin-backup-group').evaluate('el=>el.open'):
            self.page.locator('#admin-backup-group > summary').click()
        self.page.locator('#toggle-backup').click()
        with self.page.expect_download() as event:
            self.page.locator('#backup-export').click()
        backup = json.loads(Path(event.value.path()).read_text())
        self.assertEqual(backup['backupVersion'], 8)
        self.assertEqual(backup['data'], before)
        self.install()
        changed = self.snapshot()
        self.page.locator('#open-admin').click()
        self.page.locator('#backup-file').set_input_files({
            'name': 'synthetic-board-v7.json', 'mimeType': 'application/json',
            'buffer': json.dumps(backup).encode()})
        self.page.wait_for_function("document.querySelector('#backup-preview').textContent.startsWith('検査OK')")
        self.assertEqual(self.snapshot(), changed)
        self.page.locator('#backup-restore').click()
        self.page.wait_for_function('!backingUp&&pendingRestore===null')
        self.assertEqual(self.snapshot(), before)
        self.page.reload()
        self.ready()
        self.assertEqual(self.snapshot(), before)

    def test_v7_validation_rejects_corruption_empty_wins_and_profile_mismatch(self):
        self.install()
        self.round()
        results = self.page.evaluate("""async()=>{
          const data=await snapshotAllStores();
          const changes=[
            d=>delete d.arcadeBoards,
            d=>d.arcadeBoards[0].slots.pop(),
            d=>d.arcadeBoards[0].slots[0]='unknown',
            d=>d.arcadeBoards[0].slots[0]=false,
            d=>d.arcadeBoards.push({...d.arcadeBoards[0]}),
            d=>d.arcadeBoards[0].profile='someone',
            d=>d.arcadePlays[0].prizes[0]=null,
            d=>d.arcadePlays[0].prizes=['shiba',null,'rabbit'],
            d=>{const p=d.arcadePlays[0];p.status='resolving';d.arcadePrizes=[];
              d.arcadeBoards.find(b=>b.profile===p.profile).slots=['star',...p.prizes.slice(1)];},
            d=>{const p=d.arcadePlays[0];p.status='resolving';d.arcadePrizes=[];
              d.arcadeBoards=d.arcadeBoards.filter(b=>b.profile!==p.profile);}
          ];
          return changes.map(change=>{const d=structuredClone(data);change(d);
            try{validateBackup({backupFormat:BACKUP_FORMAT,backupVersion:7,data:d});return false;}
            catch{return true;}});
        }""")
        self.assertEqual(results, [True] * 10)

    def test_db6_upgrade_keeps_thirteen_stores_migrates_latest_layout_once(self):
        data = self.page.evaluate("plushFixture(['shiba','rabbit'],'student',7)")
        data.pop('arcadeBoards')
        test = self.page.evaluate("plushFixture(['star'],'test',7)")
        test['arcadePlays'][0]['status'] = 'resolving'
        for name in ['arcadePlays', 'coinSpends']:
            data[name] += test[name]
        # 実際のv1.6.6 mainでDB6を作り、DB7のアプリを開く。
        old_source = subprocess.check_output(['git', 'show', '53f6450:index.html'], cwd=ROOT, text=True)
        self.page.evaluate("""async()=>{
          db.close();await new Promise((resolve,reject)=>{const r=indexedDB.deleteDatabase(DB_NAME);
            r.onsuccess=resolve;r.onerror=()=>reject(r.error);});
        }""")
        self.page.route(self.url, lambda route: route.fulfill(body=old_source, content_type='text/html'))
        self.page.reload()
        self.page.wait_for_function("(typeof appReady==='undefined'?document.querySelectorAll('#era-list button').length===10:appReady)")
        self.page.evaluate('data=>replaceAllStores(data)', data)
        before = self.snapshot()
        self.assertEqual(self.page.evaluate('db.version'), 6)
        self.page.unroute(self.url)
        self.page.reload()
        self.ready()
        after = self.snapshot()
        self.assertEqual(self.page.evaluate('[db.version,db.objectStoreNames.length]'), [8, 15])
        for name in before:
            self.assertEqual(after[name], before[name], name)
        self.assertEqual(self.board('student')['slots'], [None] + ['rabbit'] * 6)
        self.assertEqual(self.board('test')['slots'], ['star'] * 7)
        self.page.reload()
        self.ready()
        self.assertEqual(self.snapshot(), after)
        self.page.evaluate("async()=>{profile='test';await openArcade();}")
        self.assertIsNone(self.page.evaluate('arcadeSweepFrame'))
        self.page.locator('#crane-start').click()
        self.page.wait_for_function('!arcadeBusy')
        self.page.evaluate("finishCranePlay('fixture-test-0')")
        self.assertEqual(self.board('test')['slots'], [None] + ['star'] * 6)
        self.assertEqual(len(self.snapshot()['arcadePrizes']), len(before['arcadePrizes']) + 1)
        self.assertEqual(self.snapshot()['coinSpends'], before['coinSpends'])

    def test_old_three_and_seven_slot_aiming_resolving_resume_once(self):
        for slots in [3, 7]:
            for status in ['aiming', 'resolving']:
                with self.subTest(slots=slots, status=status):
                    data = self.page.evaluate('slots=>plushFixture(["shiba"],"student",slots)', slots)
                    p = data['arcadePlays'][0]
                    p['status'] = status
                    if status == 'aiming':
                        del p['result']
                    data['arcadePrizes'] = []
                    data.pop('arcadeBoards')
                    normalized = self.page.evaluate('data=>validateBackup({backupFormat:BACKUP_FORMAT,backupVersion:6,data})', data)
                    self.page.evaluate('async data=>{await plushInstall(data);profile="student";await openArcade();}', normalized)
                    self.assertTrue(self.page.locator('#crane-replace').is_disabled())
                    self.assertEqual(self.page.locator('.crane-toy').count(), slots)
                    if slots == 3:
                        self.assertIsNone(self.board('student'))
                    self.page.locator('#crane-start').click()
                    self.page.wait_for_function('!arcadeBusy')
                    if status == 'aiming':
                        self.page.evaluate('''async()=>{
                          stopCraneSweep();arcadePlay.armX=positionsForPlay(arcadePlay)[0];
                          const saved=animateCraneOutcome;animateCraneOutcome=async()=>{};
                          const random=Math.random;Math.random=()=>0;
                          try{await catchCrane();}finally{animateCraneOutcome=saved;Math.random=random;}
                        }''')
                    self.page.evaluate('id=>Promise.all([finishCranePlay(id),finishCranePlay(id)])', p['id'])
                    self.assertEqual(len(self.snapshot()['arcadePrizes']), 1)
                    self.assertEqual(self.snapshot()['coinSpends'], data['coinSpends'])
                    self.assertEqual(self.page.evaluate("id=>readOne('arcadePlays',id)", p['id'])['prizes'], p['prizes'])
                    self.assertEqual(len(self.board('student')['slots']), 7)
                    self.page.evaluate('startCrane()')
                    self.page.evaluate('stopCraneSweep()')
                    self.assertEqual(len(self.page.evaluate('arcadePlay.prizes')), 7)

    def test_profile_reset_other_board_and_full_reset_with_confirmations(self):
        for who in ['student', 'test']:
            with self.subTest(profile=who):
                self.install()
                before = self.snapshot()
                self.page.locator('#open-admin').click()
                if not self.page.locator('#admin-other-group').evaluate('el=>el.open'):
                    self.page.locator('#admin-other-group > summary').click()
                self.page.locator('#toggle-reset').click()
                self.page.locator(f'#reset-{who}').check()
                self.page.locator('#reset-ack').check()
                self.page.wait_for_function('!document.querySelector("#reset-apply").disabled')
                self.cancel_dialog = True
                self.page.locator('#reset-apply').click()
                self.assertEqual(self.snapshot(), before)
                self.cancel_dialog = False
                self.page.locator('#reset-apply').click()
                self.page.wait_for_function("!resetting&&!backingUp&&document.querySelector('#reset-preview').textContent.includes('初期化しました')||!resetting&&!backingUp&&document.querySelector('#reset-preview').textContent.startsWith('選択した初期化が完了')")
                after = self.snapshot()
                self.assertIsNone(self.board(who))
                other = 'test' if who == 'student' else 'student'
                for store in before:
                    self.assertEqual([r for r in after[store] if r.get('profile') == other],
                                     [r for r in before[store] if r.get('profile') == other], store)
                self.assertEqual(after['questions'], before['questions'])
                self.page.evaluate('async who=>{profile=who;await openArcade();}', who)
                self.assertEqual(len(self.board(who)['slots']), 7)
                self.page.locator('#reset-panel').evaluate('el=>el.classList.add("hidden")')
        self.page.locator('#open-admin').click()
        if not self.page.locator('#admin-other-group').evaluate('el=>el.open'):
            self.page.locator('#admin-other-group > summary').click()
        self.page.locator('#toggle-reset').click()
        before = self.snapshot()
        self.cancel_dialog = True
        self.page.locator('#reset-all').click()
        self.assertEqual(self.snapshot(), before)
        self.cancel_dialog = False
        self.page.locator('#reset-all').click()
        self.page.wait_for_function("!resetting&&!backingUp&&document.querySelector('#reset-preview').textContent.includes('初期化しました')||!resetting&&!backingUp&&document.querySelector('#reset-preview').textContent.startsWith('選択した初期化が完了')")
        self.assertEqual(self.snapshot()['arcadeBoards'], [])
        self.assertTrue(any('完全初期化するには' in msg for msg in self.dialogs))
        for name, rows in self.snapshot().items():
            if name != 'coinMeta':
                self.assertEqual(rows, [], name)

    def test_iphone_ipad_board_buttons_and_empty_message_fit(self):
        self.install([None] * 7)
        for width, height in [(375, 812), (390, 844), (820, 1180), (1024, 768), (1180, 820)]:
            with self.subTest(width=width):
                self.page.set_viewport_size({'width': width, 'height': height})
                self.assertTrue(self.page.evaluate('''()=>document.documentElement.scrollWidth<=innerWidth&&
                  ['crane-stage','crane-start','crane-replace','arcade-message'].every(id=>{
                    const el=document.getElementById(id),r=el.getBoundingClientRect();
                    return r.width>0&&r.left>=0&&r.right<=innerWidth&&
                      (el.tagName!=='BUTTON'||r.height>=44);
                  })'''))
        self.replace_prizes_and_wait()
        self.page.wait_for_function('!arcadeBusy')
        self.assertEqual(self.page.locator('.crane-toy').count(), 7)

    def test_atomic_completion_rolls_back_all_on_error_and_retries_once(self):
        self.install()
        play_id = self.page.evaluate("""async()=>{
          const p=await purchaseCranePlay(newArcadePlay(profile));p.armX=14;
          await commitCraneOutcome(p,chooseCraneOutcome(p,()=>0));return p.id;
        }""")
        before = self.snapshot()
        failed = self.page.evaluate("""async id=>{
          const add=IDBObjectStore.prototype.add;
          IDBObjectStore.prototype.add=function(value,...args){
            if(this.name==='arcadePrizes')add.call(this,value,...args);
            return add.call(this,value,...args);
          };
          try {await finishCranePlay(id);return false;}catch{return true;}
          finally{IDBObjectStore.prototype.add=add;}
        }""", play_id)
        self.assertTrue(failed)
        self.assertEqual(self.snapshot(), before)
        self.page.evaluate('id=>Promise.all([finishCranePlay(id),finishCranePlay(id),finishCranePlay(id)])', play_id)
        after = self.snapshot()
        self.assertEqual(len(after['arcadePrizes']), 1)
        self.assertEqual(len(after['coinSpends']), 1)
        self.assertEqual(after['arcadePlays'][0]['status'], 'finished')
        self.assertEqual(after['arcadePlays'][0]['prizes'], SLOTS)
        self.assertEqual(self.board()['slots'], [None, *SLOTS[1:]])


if __name__ == '__main__':
    unittest.main()
