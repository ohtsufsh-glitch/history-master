"""景品追加・保存互換性の回帰テスト。教材・個人データは使用しない。

実行: python -m unittest discover -s tests -p '*_test.py' -v
準備とブラウザ指定は question_editor_test.py と同じ。
合成履歴は一時ブラウザ内だけに作り、実際の端末や公開サイトへ接続しない。
"""

import functools
import http.server
import json
import os
from pathlib import Path
import re
import shutil
import threading
import unittest

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
TYPES = {
    'shiba': 'しば犬', 'sloth': 'なまけもの', 'goldfish': '金魚',
    'salamander': 'オオサンショウウオ', 'bear': 'くま',
    'rabbit': 'うさもち', 'chick': 'ぴよまる', 'seal': 'あざらし',
    'penguin': 'ぺんころ', 'hamster': 'はむぷく', 'capybara': 'カピバラ',
    'redpanda': 'れさぽん', 'kitten': 'にゃこまる', 'puppy': 'わんころ',
    'piglet': 'こぶた', 'jelly': 'くらげ', 'otter': 'らこまる',
    'bird': 'ことり', 'cloud': 'くもふわ', 'star': 'ほしぷに',
}
IDS = list(TYPES)

# 全14ストアに公開可能な架空データを作る。報酬も実際の検証条件を満たす。
FIXTURE_HELPERS = """() => {
  window.plushFixture = (ids=[], who='test', slots=7) => {
    const at='2020-01-01T00:00:00.000Z', qid='TEST-PLUSH-001';
    const data=Object.fromEntries(BACKUP_STORES.map(name=>[name,[]]));
    data.questions=[{id:qid,era:'E01',q:'合成データの動作確認です。',
      options:['確認用の甲','確認用の乙'],answers:[0],why:'テスト専用の説明です。',
      revision:1,difficulty:'basic',tag:'culture',shuffleOptions:false,deleted:false}];
    data.coinMeta=[{id:COIN_MIGRATION_KEY,migratedAt:at,legacyClaims:0}];
    data.sampleSettings=[{id:SAMPLE_QUESTIONS[0].id,hidden:true}];
    for (const profile of ['student','test']) {
      data.progress.push({key:`${profile}:${qid}`,profile,questionId:qid,revision:1,
        attempts:2,streak:2,mastered:true,everWrong:false,lastAnsweredAt:at});
      data.sessions.push({key:`${profile}:E01`,profile,era:'E01',questionId:qid,
        revision:1,phase:'question',selected:[0],optionOrder:[0,1],recentIds:[qid]});
      data.awards.push({key:`${profile}:E01`,profile,era:'E01',earnedAt:at,questionCountAtEarn:50});
      for (const stage of ['first','master']) {
        data.answers.push({id:data.answers.length+1,profile,questionId:qid,
          revision:1,correct:true,selected:[0],at});
        const key=coinClaimKey(profile,qid,stage);
        data.coinClaims.push({key,profile,questionId:qid,stage,source:'reward',claimedAt:at});
        data.coinEvents.push({key,profile,questionId:qid,stage,difficulty:'basic',
          amount:COIN_REWARDS.basic[stage],at});
      }
      for(let i=0;i<(profile==='student'?400:2);i++)
        data.reviewEvents.push({key:`review:${profile}:${crypto.randomUUID()}`,
          profile,questionId:qid,difficulty:'basic',amount:2,at});
    }
    ids.forEach((id,i)=>{
      const playId=`fixture-${who}-${i}`;
      const prizes=slots===3?[id,...['shiba','sloth','goldfish','bear'].filter(x=>x!==id).slice(0,2)]:Array(7).fill(id);
      const startedAt=new Date(Date.parse(at)+i*1000).toISOString();
      data.arcadePlays.push({id:playId,profile:who,game:'crane',status:'finished',
        startedAt,armX:slots===3?20:14,direction:1,prizes,
        result:{targetIndex:0,alignment:'perfect',grabbed:true,won:true,fallAt:null,at:startedAt}});
      data.coinSpends.push({id:playId,profile:who,game:'crane',amount:who==='test'?0:100,at:startedAt});
      data.arcadePrizes.push({id:playId,profile:who,prizeId:id,wonAt:startedAt});
    });
    data.arcadeBoards=['student','test'].map(who=>initialArcadeBoard(who,data.arcadePlays)).filter(Boolean);
    return data;
  };
  window.plushInstall = async data => {
    stopCraneSweep();arcadePlay=null;arcadeResumeRequired=true;
    await replaceAllStores(data);await loadImportedQuestions();
    answerEvents=await readAll('answers');
  };
}"""


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class PlushTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handler = functools.partial(QuietHandler, directory=str(ROOT))
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
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
        self.context = self.browser.new_context(
            viewport={'width': 1180, 'height': 820}, has_touch=True)
        self.page = self.context.new_page()
        self.page.set_default_timeout(7000)
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.on('dialog', lambda dialog: dialog.accept())
        self.page.goto(self.url)
        self.ready()

    def ready(self):
        self.page.wait_for_function("(typeof appReady==='undefined'?document.querySelectorAll('#era-list button').length===10:appReady)")
        self.page.evaluate(FIXTURE_HELPERS)

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.errors, [])

    def snapshot(self):
        return self.page.evaluate('snapshotAllStores()')

    def assert_stores_equal(self, actual, expected):
        # getAll() は主キー順。バックアップの配列順は記録の内容ではない。
        self.assertEqual(actual.keys(), expected.keys())
        for store in expected:
            key = lambda row: row.get('key', row.get('id', row.get('profile')))
            self.assertEqual(sorted(actual[store], key=key),
                             sorted(expected[store], key=key), store)

    def fixture(self, ids=(), who='test', slots=7):
        return self.page.evaluate('args=>plushFixture(...args)', [list(ids), who, slots])

    def install(self, data):
        self.page.evaluate('data=>plushInstall(data)', data)

    def test_definitions_paths_decoded_images_and_equal_probability_seven_slots(self):
        actual = self.page.evaluate("""async () => ({
          types:PLUSH_TYPES,ids:PLUSH_IDS,db:db.version,backup:BACKUP_VERSION,
          images:await Promise.all(PLUSH_IDS.map(async id=>{
            const img=new Image();img.src=plushPath(id);await img.decode();
            return {path:img.getAttribute('src'),width:img.naturalWidth,height:img.naturalHeight};
          })),
          samples:(()=>{
            const saved=Math.random, samples=[];
            try {
              // 各等幅区間の両端付近を確認。重複配置も同時に検証する。
              for(let i=0;i<20;i++)for(const offset of [.001,.999]) {
                let first=true;samples.push(randomArcadePrizes(()=>{if(first){first=false;return .5;}return (i+offset)/20;}));
              }
            } finally {Math.random=saved;}
            return samples;
          })()
        })""")
        self.assertEqual(actual['types'], TYPES)
        self.assertEqual(actual['ids'], IDS)
        self.assertEqual((actual['db'], actual['backup']), (8, 8))
        for prize_id, image in zip(IDS, actual['images']):
            self.assertEqual(image['path'], f'assets/plush/{prize_id}.webp')
            self.assertGreater(image['width'], 0)
            self.assertGreater(image['height'], 0)
        self.assertEqual(actual['samples'], [[prize_id] * 7 for prize_id in IDS for _ in range(2)])

    def test_collection_order_counts_dark_images_completion_and_dynamic_total(self):
        self.install(self.fixture(['shiba', 'shiba', 'rabbit'], 'student'))
        self.page.evaluate("async()=>{profile='student';await openArcade();await refreshArcadeHome();}")
        self.assertEqual(self.page.locator('#arcade-collection-list .plush-item strong').all_text_contents(), list(TYPES.values()))
        self.assertEqual(self.page.locator('#arcade-collection-list .plush-item').count(), 20)
        self.assertEqual(self.page.locator('#arcade-collection-list .plush-item.not-owned').count(), 18)
        self.assertEqual(self.page.locator('#arcade-collection-list .plush-item .owned').nth(0).inner_text(), '×2')
        self.assertIn('2/20種類', self.page.locator('#arcade-collection-count').inner_text())
        self.assertIn('2/20種類', self.page.locator('#arcade-home-status').inner_text())
        self.assertIn('全20種類', self.page.locator('#arcade-home-description').inner_text())
        filters = self.page.locator('#arcade-collection-list .plush-item img').evaluate_all(
            "imgs=>imgs.map(img=>({filter:getComputedStyle(img).filter,lazy:img.loading}))")
        self.assertEqual(filters[0]['filter'], 'none')
        self.assertIn('grayscale', filters[1]['filter'])
        self.assertTrue(all(item['lazy'] == 'lazy' for item in filters))
        self.install(self.fixture(IDS[:-1]))
        self.page.evaluate("async()=>{profile='test';await renderArcadeCollection();}")
        self.assertIn('19/20種類', self.page.locator('#arcade-collection-count').inner_text())
        # 将来の種類数変更にも追従することを、定義から作ったID一覧の変更で確認。
        self.page.evaluate("async()=>{window.removedPlushId=PLUSH_IDS.pop();await renderArcadeCollection();await refreshArcadeHome();}")
        self.assertIn('コンプリート', self.page.locator('#arcade-collection-count').inner_text())
        self.assertIn('19/19種類', self.page.locator('#arcade-home-status').inner_text())
        self.page.evaluate('PLUSH_IDS.push(window.removedPlushId)')
        self.install(self.fixture(IDS + ['star']))
        self.page.evaluate('renderArcadeCollection()')
        self.assertIn('コンプリート', self.page.locator('#arcade-collection-count').inner_text())
        self.assertIn('21体', self.page.locator('#arcade-collection-count').inner_text())
        self.assertEqual(self.page.locator('#arcade-collection-list .plush-item.not-owned').count(), 0)
        self.assertEqual(self.page.locator('#arcade-collection-list .plush-item .owned').last.inner_text(), '×2')

    def test_collection_fits_ipad_and_iphone_and_all_lazy_images_load_on_scroll(self):
        self.page.evaluate('openArcade()')
        for width, height, columns in [(1180, 820, 5), (1024, 768, 5), (390, 844, 3)]:
            with self.subTest(width=width):
                self.page.set_viewport_size({'width': width, 'height': height})
                for image in self.page.locator('#arcade-collection-list .plush-item img').all():
                    image.scroll_into_view_if_needed()
                    image.evaluate('img=>img.decode()')
                layout = self.page.locator('#arcade-collection-list').evaluate("""grid=>({
                  columns:getComputedStyle(grid).gridTemplateColumns.split(' ').length,
                  fits:document.documentElement.scrollWidth<=innerWidth,
                  loaded:[...grid.querySelectorAll('img')].every(img=>img.complete&&img.naturalWidth>0)
                })""")
                self.assertEqual(layout, {'columns': columns, 'fits': True, 'loaded': True})

    def test_v3_to_v6_restore_preserves_legacy_records_and_three_seven_layouts(self):
        for version in [3, 4, 5, 6]:
            with self.subTest(version=version):
                data = self.fixture(IDS[:5], 'student', 3)
                if version >= 5:
                    seven = self.fixture(['bear', 'bear'])
                    data['arcadePlays'] += seven['arcadePlays']
                    data['arcadePrizes'] += seven['arcadePrizes']
                    data['coinSpends'] += seven['coinSpends']
                else:
                    for name in ['reviewEvents', 'coinSpends', 'arcadePlays', 'arcadePrizes']:
                        del data[name]
                if version == 3:
                    for name in ['coinClaims', 'coinEvents', 'coinMeta']:
                        del data[name]
                result = self.page.evaluate("""async ({data,version})=>{
                  stopCraneSweep();
                  const normalized=validateBackup({backupFormat:BACKUP_FORMAT,backupVersion:version,data});
                  const localFeedback=await readAll("questionFeedback");
                  pendingRestore=normalized;await applyRestore();
                  return {normalized:{...normalized,questionFeedback:localFeedback},snapshot:await snapshotAllStores(),
                    positions:normalized.arcadePlays.map(play=>positionsForPlay(play)),
                    balance:await getAvailableCoins('student')};
                }""", {'data': data, 'version': version})
                self.assert_stores_equal(result['snapshot'], result['normalized'])
                for store in ['questions', 'progress', 'sessions', 'answers', 'awards', 'sampleSettings']:
                    self.assertEqual(result['snapshot'][store], data[store], store)
                if version >= 5:
                    self.assert_stores_equal({'arcadePrizes': result['snapshot']['arcadePrizes']},
                                            {'arcadePrizes': data['arcadePrizes']})
                    self.assertEqual(result['positions'], [[20, 50, 80]] * 5 + [[14, 26, 38, 50, 62, 74, 86]] * 2)
                if version == 3:
                    self.assertEqual(result['balance'], 0)
                    self.assertEqual(len(result['snapshot']['coinClaims']), 4)

    def test_new_prizes_backup_download_preview_restore_and_reload_all_stores(self):
        data = self.fixture(IDS)
        old = self.fixture(IDS[:5], 'student', 3)
        for name in ['arcadePlays', 'arcadePrizes', 'coinSpends']:
            data[name] += old[name]
        # 新景品を含む未完了プレイも完全バックアップで往復する。
        data['arcadePlays'].append({
            'id': 'pending-new', 'profile': 'student', 'game': 'crane', 'status': 'aiming',
            'startedAt': '2021-01-01T00:00:00.000Z', 'armX': 62, 'direction': -1,
            'prizes': ['star', 'cloud', 'bird', 'otter', 'jelly', 'piglet', 'puppy']})
        data['coinSpends'].append({'id': 'pending-new', 'profile': 'student', 'game': 'crane',
                                   'amount': 100, 'at': '2021-01-01T00:00:00.000Z'})
        data['arcadeBoards'][0]['slots']=data['arcadePlays'][-1]['prizes'][:]
        self.install(data)
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
        self.install(self.fixture())
        cleared = self.snapshot()
        self.page.locator('#backup-file').set_input_files({
            'name': 'synthetic-plush-backup.json', 'mimeType': 'application/json',
            'buffer': json.dumps(backup).encode()})
        self.page.wait_for_function("document.querySelector('#backup-preview').textContent.startsWith('検査OK')")
        self.assertEqual(self.snapshot(), cleared, 'プレビューでは保存データを変更しない')
        self.page.locator('#backup-restore').click()
        self.page.wait_for_function('!backingUp && pendingRestore===null')
        self.assertEqual(self.snapshot(), before)
        self.page.reload()
        self.ready()
        self.assertEqual(self.snapshot(), before)

    def test_upgrade_from_five_prize_definitions_keeps_all_stores(self):
        # 旧5種類の定義で保存した同じDBを、新20種類のアプリで開き直す。
        source = (ROOT / 'index.html').read_text()
        legacy_source, replacements = re.subn(
            r'const PLUSH_TYPES=Object\.freeze\(\{.*?\n\}\);',
            lambda _: 'const PLUSH_TYPES=Object.freeze(' + json.dumps(dict(list(TYPES.items())[:5])) + ');',
            source, count=1, flags=re.S)
        self.assertEqual(replacements, 1)
        self.page.route(self.url, lambda route: route.fulfill(body=legacy_source, content_type='text/html'))
        self.page.reload()
        self.ready()
        self.assertEqual(self.page.evaluate('PLUSH_IDS'), IDS[:5])
        data = self.fixture(IDS[:5], 'student', 3)
        duplicate = self.fixture(['bear', 'bear'])
        for store in ['arcadePlays', 'arcadePrizes', 'coinSpends']:
            data[store] += duplicate[store]
        self.install(data)
        before = self.snapshot()
        self.page.unroute(self.url)
        self.page.reload()
        self.ready()
        self.assertEqual(self.page.evaluate('PLUSH_IDS'), IDS)
        self.assertEqual(self.snapshot(), before)
        self.page.evaluate('openArcade()')
        self.assertIn('5/20種類', self.page.locator('#arcade-collection-count').inner_text())
        self.assertEqual(self.page.locator('#arcade-collection-list .plush-item.not-owned').count(), 15)

    def test_backup_still_rejects_unknown_ids_and_inconsistent_transactions(self):
        data = self.fixture(['rabbit'])
        self.install(data)
        result = self.page.evaluate("""async data=>{
          const changes=[
            d=>d.arcadePlays[0].prizes[0]='unknown',
            d=>d.arcadePrizes[0].prizeId='chick',
            d=>d.arcadePrizes=[],
            d=>d.arcadePrizes.push({...d.arcadePrizes[0]}),
            d=>d.coinSpends=[],
            d=>d.arcadePlays[0].prizes=['rabbit','rabbit','shiba']
          ];
          return changes.map(change=>{
            const copy=structuredClone(data);change(copy);
            try {validateBackup({backupFormat:BACKUP_FORMAT,backupVersion:6,data:copy});return false;}
            catch {return true;}
          });
        }""", data)
        self.assertEqual(result, [True] * 6)
        self.assert_stores_equal(self.snapshot(), data)

    def test_student_cost_free_repeat_test_and_profile_separation(self):
        data = self.fixture()
        for store in ['coinEvents', 'reviewEvents']:
            data[store] = [r for r in data[store] if r['profile'] == 'student']
        next(b for b in data['arcadeBoards'] if b['profile']=='test')['slots']=['rabbit']*7
        self.install(data)
        self.assertEqual(self.page.evaluate("getAvailableCoins('test')"), 0)
        before = self.snapshot()
        self.page.evaluate("async()=>{profile='student';await openArcade();}")
        balance = self.page.evaluate("getAvailableCoins('student')")
        self.page.locator('#crane-start').click()
        self.page.wait_for_function("arcadePlay?.status==='aiming' && !arcadeBusy")
        self.assertEqual(self.page.evaluate("getAvailableCoins('student')"), balance - 100)
        paid = self.page.evaluate("readAll('coinSpends')")
        self.assertEqual([row['amount'] for row in paid], [100])
        self.page.evaluate("async()=>{stopCraneSweep();profile='test';await openArcade();}")
        # 画面移動時のアーム位置保存が終わってから本番データを比較する。
        student = self.snapshot()
        for slot in range(3):
            self.page.locator('#crane-start').click()
            self.page.wait_for_function("arcadePlay?.profile==='test' && arcadePlay.status==='aiming' && !arcadeBusy")
            self.page.evaluate("""async slot=>{
              stopCraneSweep();
              arcadePlay=await commitCraneOutcome(arcadePlay,{targetIndex:slot,alignment:'perfect',
                grabbed:true,won:true,fallAt:null,at:new Date().toISOString()});
              arcadePlay=await finishCranePlay(arcadePlay.id);await renderArcade();
            }""", slot)
        after = self.snapshot()
        self.assertEqual([r['amount'] for r in after['coinSpends'] if r['profile'] == 'test'], [0, 0, 0])
        self.assertEqual([r['prizeId'] for r in after['arcadePrizes']], ['rabbit'] * 3)
        self.assertEqual(self.page.evaluate("getAvailableCoins('test')"), 0)
        for store in before:
            self.assertEqual([r for r in after[store] if r.get('profile') == 'student'],
                             [r for r in student[store] if r.get('profile') == 'student'], store)
        self.assertEqual(self.page.locator('#arcade-collection-list .plush-item .owned').nth(5).inner_text(), '×3')

    def test_legacy_aiming_and_new_resolving_require_manual_resume_without_charge_or_duplicate_prize(self):
        for status, slots in [('aiming', 3), ('resolving', 7)]:
            with self.subTest(status=status):
                data = self.fixture(['shiba'], 'student', slots)
                data['reviewEvents'] = ([r for r in data['reviewEvents'] if r['profile'] == 'student'][:50]
                                        + [r for r in data['reviewEvents'] if r['profile'] == 'test'])
                play = data['arcadePlays'][0]
                play['status'] = status
                data['arcadePrizes'] = []
                if status == 'aiming':
                    del play['result']
                else:
                    play['prizes'] = ['star'] * 7
                data=self.page.evaluate('data=>validateBackup({backupFormat:BACKUP_FORMAT,backupVersion:6,data})', data)
                local_feedback = self.page.evaluate('readAll("questionFeedback")')
                self.install(data)
                data["questionFeedback"] = local_feedback  # 旧復元は指摘を保持する仕様。比較対象にも含める。
                self.page.evaluate("async()=>{profile='student';await openArcade();}")
                self.assertIn('追加料金なし', self.page.locator('#crane-start').inner_text())
                self.assertTrue(self.page.locator('#crane-catch').is_disabled())
                self.assertIsNone(self.page.evaluate('arcadeSweepFrame'))
                self.assertEqual(self.page.locator('.crane-toy').count(), slots)
                self.assert_stores_equal(self.snapshot(), data)
                self.page.locator('#crane-start').click()
                # busy解除後の非同期renderArcade()がボタンを更新するまで待つ。
                self.page.wait_for_function("""status=>!arcadeBusy &&
                  (status==='aiming' ? !document.querySelector('#crane-catch').disabled : arcadePlay?.status==='finished')
                """, arg=status)
                if status == 'aiming':
                    self.assertFalse(self.page.locator('#crane-catch').is_disabled())
                    self.assertIsNotNone(self.page.evaluate('arcadeSweepFrame'))
                    self.page.evaluate('stopCraneSweep()')
                else:
                    self.assertEqual(self.page.evaluate('arcadePlay.status'), 'finished')
                    self.page.evaluate("finishCranePlay('fixture-student-0')")
                    self.page.evaluate("finishCranePlay('fixture-student-0')")
                    prizes = self.page.evaluate("readAll('arcadePrizes')")
                    self.assertEqual(len(prizes), 1)
                    self.assertEqual(prizes[0]['prizeId'], 'star')
                self.assertEqual(self.page.evaluate("readAll('coinSpends')"), data['coinSpends'])
                self.assertEqual(self.page.evaluate("getAvailableCoins('student')"), 5)


if __name__ == '__main__':
    unittest.main()
