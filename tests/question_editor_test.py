"""問題編集の回帰テスト。教材・個人データは使用しない。

準備: python -m pip install playwright && playwright install chromium
実行: python -m unittest discover -s tests -p '*_test.py' -v
任意: HISTORY_MASTER_BROWSER に Chromium の実行ファイルを指定する。
各テストは一時的なブラウザ環境と localhost のサーバーだけを使用する。
"""

import functools
import http.server
import os
from pathlib import Path
import shutil
import threading
import unittest

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class QuestionEditorTest(unittest.TestCase):
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
            viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
        self.page = self.context.new_page()
        self.page.set_default_timeout(5000)
        self.errors = []
        self.dialogs = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.on('dialog', self.accept_dialog)
        self.page.goto(self.url)
        self.page.wait_for_function("(typeof appReady==='undefined'?document.querySelectorAll('#era-list button').length===10:appReady)")
        # 公開可能な独自のダミー文章。実際の問題JSON・バックアップは保存しない。
        self.questions = self.page.evaluate("""async () => {
          const variants = [
            {id:'TEST-PLAIN', options:['確認用あ','確認用い','確認用う'], answers:[1]},
            {id:'TEST-SINGLE', options:['確認用A\\n続きA','確認用B\\n続きB','確認用C'], answers:[1]},
            {id:'TEST-MULTIPLE', options:['確認用甲\\n\\n段落甲','確認用乙','確認用丙\\n続き丙'], answers:[2,0]},
            {id:'TEST-TWO', options:['確認用左\\n続き左','確認用右'], answers:[0]},
            {id:'TEST-SIX', options:Array.from({length:6},(_,i)=>`確認用${i}\\n続き${i}`), answers:[0,5]},
            {id:'TEST-LEGACY', options:['旧形式あ','旧形式い'], answers:[0]},
            {id:'TEST-RAW', options:['\\n確認用改行\\r\\n次の行\\n','確認用別案\\r単独改行'], answers:[1]}
          ];
          const questions=variants.map((item,i)=>({
            ...item,era:'E01',q:`独立した編集テスト ${i}`,why:'検証用の説明。',
            ...(item.id==='TEST-LEGACY'?{}:{revision:7,deleted:false,shuffleOptions:i%2===0,difficulty:'basic',tag:'culture'})
          }));
          const tx=db.transaction([...db.objectStoreNames],'readwrite');
          for (const q of questions) {
            tx.objectStore('questions').put(q);
            for (const who of ['student','test']) {
              tx.objectStore('progress').put({key:`${who}:${q.id}`,profile:who,questionId:q.id,
                revision:questionRevision(q),attempts:2,streak:2,mastered:true,everWrong:false});
              tx.objectStore('answers').add({profile:who,questionId:q.id,revision:questionRevision(q),
                correct:true,selected:q.answers,at:'2020-01-01T00:00:00.000Z'});
            }
          }
          for (const who of ['student','test']) {
            tx.objectStore('sessions').put({key:`${who}:E01`,profile:who,era:'E01',
              questionId:'TEST-SINGLE',revision:7,phase:'question',selected:[1],optionOrder:[2,0,1]});
            for (const store of ['awards','coinClaims','coinEvents','reviewEvents'])
              tx.objectStore(store).put({key:`${who}:test-marker`,profile:who,value:19});
            for (const store of ['coinSpends','arcadePlays','arcadePrizes'])
              tx.objectStore(store).put({id:`${who}:test-marker`,profile:who,value:23});
          }
          await new Promise((resolve,reject)=>{tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);});
          await loadImportedQuestions();
          answerEvents=await readAll('answers');
          return questions;
        }""")
        self.page.locator('#open-admin').click()
        self.page.locator('#toggle-manage').click()

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.errors, [])

    def accept_dialog(self, dialog):
        self.dialogs.append(dialog.message)
        dialog.accept()

    def snapshot(self):
        return self.page.evaluate("""async () => Object.fromEntries(
          await Promise.all([...db.objectStoreNames].map(async name=>[name,await readAll(name)])))""")

    def open_editor(self, question_id):
        self.page.locator('#manage-search').fill(question_id)
        self.page.locator('#manage-list').get_by_role('button', name='修正する', exact=True).click()
        self.page.locator('.edit-form').wait_for(state='visible')

    def choice(self, number):
        return self.page.get_by_label(f'選択肢 {number}', exact=True)

    def save(self):
        self.page.get_by_role('button', name='修正内容を保存', exact=True).click()
        self.page.locator('.edit-form').wait_for(state='detached')

    def test_noop_preserves_multiline_and_plain_questions_and_all_history(self):
        before = self.snapshot()
        for q in self.questions:
            with self.subTest(question=q['id']):
                self.open_editor(q['id'])
                self.save()
                actual = self.page.evaluate("id=>readOne('questions',id)", q['id'])
                self.assertEqual(actual['options'], q['options'])
                self.assertEqual(actual['answers'], q['answers'])
                self.assertEqual(actual.get('revision', 1), q.get('revision', 1))
        after = self.snapshot()
        self.assertEqual(self.dialogs, [])
        for store in before:
            if store != 'questions':
                self.assertEqual(after[store], before[store], store)
        for q in after['questions']:
            original = next(item for item in self.questions if item['id'] == q['id'])
            self.assertEqual(q, {**original, 'revision': original.get('revision', 1),
                                 'deleted': False, 'shuffleOptions': original.get('shuffleOptions', True)})
        self.page.reload()
        self.page.wait_for_function("(typeof appReady==='undefined'?document.querySelectorAll('#era-list button').length===10:appReady)")
        self.assertEqual(self.snapshot(), after)

    def test_add_remove_options_and_keep_multiline_text(self):
        before = self.snapshot()
        self.open_editor('TEST-TWO')
        add = self.page.get_by_role('button', name='選択肢を追加', exact=True)
        remove = self.page.get_by_role('button', name='最後の選択肢を削除', exact=True)
        self.assertTrue(remove.is_disabled())
        for count in range(3, 7):
            add.click()
            self.choice(count).fill(f'追加した選択肢 {count}\n\n次の段落')
        self.assertTrue(add.is_disabled())
        remove.click()
        self.assertEqual(self.choice(5).input_value(), '追加した選択肢 5\n\n次の段落')
        self.page.get_by_label('正解の選択肢番号', exact=False).fill('1,5')
        self.save()
        after = self.snapshot()
        changed = next(q for q in after['questions'] if q['id'] == 'TEST-TWO')
        self.assertEqual(len(changed['options']), 5)
        self.assertEqual(changed['options'][0], '確認用左\n続き左')
        self.assertEqual(changed['options'][4], '追加した選択肢 5\n\n次の段落')
        self.assertEqual(changed['answers'], [0, 4])
        self.assertEqual(changed['revision'], 8)
        for store in before:
            if store != 'questions':
                self.assertEqual(after[store], before[store], store)

    def test_rejects_blank_overlong_and_invalid_correct_answers_without_writes(self):
        before = self.snapshot()
        self.open_editor('TEST-SINGLE')
        correct = self.page.get_by_label('正解の選択肢番号', exact=False)
        for invalid in ['', '1,1', '4', '7']:
            correct.fill(invalid)
            self.page.get_by_role('button', name='修正内容を保存', exact=True).click()
            self.assertTrue(self.page.locator('.edit-form').get_by_role('alert').inner_text().startswith('修正できません：'))
            self.assertEqual(self.snapshot(), before)
        correct.fill('2')
        for invalid in ['\n \n', 'あ' * 501]:
            self.choice(1).fill(invalid)
            self.page.get_by_role('button', name='修正内容を保存', exact=True).click()
            self.assertTrue(self.page.locator('.edit-form').get_by_role('alert').inner_text().startswith('修正できません：'))
            self.assertEqual(self.snapshot(), before)
        self.page.get_by_role('button', name='キャンセル', exact=True).click()
        self.assertEqual(self.snapshot(), before)

    def test_multiline_edit_keeps_revision_rules_and_old_answer_events(self):
        before = self.snapshot()
        self.open_editor('TEST-SINGLE')
        self.choice(1).fill('確認用A\n\n続きA')
        self.save()
        after_spacing = self.snapshot()
        self.assertEqual(self.dialogs, [])
        self.assertEqual(next(q for q in after_spacing['questions'] if q['id'] == 'TEST-SINGLE')['revision'], 7)
        self.assertEqual(after_spacing['sessions'], before['sessions'])
        self.open_editor('TEST-SINGLE')
        self.choice(1).fill('別の確認用文章\n次の行')
        self.save()
        after = self.snapshot()
        changed = next(q for q in after['questions'] if q['id'] == 'TEST-SINGLE')
        self.assertEqual(changed['options'][0], '別の確認用文章\n次の行')
        self.assertEqual(changed['revision'], 8)
        self.assertEqual(len(self.dialogs), 1)
        self.assertEqual(after['sessions'], [])
        for store in before:
            if store not in ('questions', 'sessions'):
                self.assertEqual(after[store], before[store], store)
        self.assertEqual([q for q in after['questions'] if q['id'] != 'TEST-SINGLE'],
                         [q for q in before['questions'] if q['id'] != 'TEST-SINGLE'])

    def test_grading_after_noop_save_single_multiple_shuffle_and_profiles(self):
        for question_id in ['TEST-SINGLE', 'TEST-MULTIPLE']:
            self.open_editor(question_id)
            self.save()
        before = self.snapshot()
        for question_id, selections, expected in [
            ('TEST-SINGLE', [1], True), ('TEST-SINGLE', [0], False),
            ('TEST-MULTIPLE', [0], False), ('TEST-MULTIPLE', [0, 1, 2], False),
            ('TEST-MULTIPLE', [0, 2], True), ('TEST-MULTIPLE', [2, 0], True)
        ]:
            with self.subTest(question=question_id, selections=selections):
                self.page.evaluate("""async id=>{
                  profile='test';
                  const q=QUESTIONS.find(q=>q.id===id);
                  const order=shuffledOrder(q);
                  if (shuffleAllowed(q)&&order.every((value,i)=>value===i)) order.reverse();
                  await writeSession({key:`test:${q.era}`,profile:'test',era:q.era,questionId:q.id,
                    revision:questionRevision(q),phase:'question',selected:[],
                    optionOrder:order,recentIds:[q.id]});
                  await startEra(q.era);
                }""", question_id)
                session_before = self.page.evaluate("readOne('sessions','test:E01')")
                self.assertEqual(session_before['questionId'], question_id)
                self.assertEqual(session_before['phase'], 'question')
                self.assertEqual(session_before['revision'], 7)
                self.assertEqual(self.page.locator('#choices button').evaluate_all(
                    'buttons=>buttons.map(b=>Number(b.dataset.originalIndex))'), session_before['optionOrder'])
                if question_id == 'TEST-MULTIPLE':
                    self.assertNotEqual(session_before['optionOrder'], [0, 1, 2])
                if question_id == 'TEST-SINGLE':
                    self.assertEqual(self.page.locator('#choices button').evaluate_all(
                        'buttons=>buttons.map(b=>Number(b.dataset.originalIndex))'), [0, 1, 2])
                    self.page.locator('#choices button[data-original-index="0"]').click()
                for index in selections:
                    self.page.locator(f'#choices button[data-original-index="{index}"]').click()
                self.page.locator('#check').click()
                self.page.locator('#result').wait_for(state='visible')
                self.page.wait_for_function('!saving')
                self.assertEqual('正解！' in self.page.locator('#result strong').inner_text(), expected)
                session_after = self.page.evaluate("readOne('sessions','test:E01')")
                self.assertEqual(session_after['questionId'], question_id)
                self.assertEqual(session_after['phase'], 'result')
                self.assertEqual(session_after['revision'], session_before['revision'])
                self.assertEqual(session_after['optionOrder'], session_before['optionOrder'])
                self.assertEqual(session_after['selected'], selections)
                last_answer = self.page.evaluate("async ()=>(await readAll('answers')).at(-1)")
                self.assertEqual(last_answer['questionId'], question_id)
                self.assertEqual(last_answer['profile'], 'test')
                self.assertEqual(last_answer['selected'], selections)
                self.assertEqual(last_answer['correct'], expected)
                self.assertEqual(self.page.locator('#choices .choice-text').evaluate_all(
                    'nodes=>nodes.every(n=>getComputedStyle(n).whiteSpace === "pre-wrap")'), True)
        after = self.snapshot()
        for store in ['progress', 'sessions', 'answers', 'awards', 'coinClaims', 'coinEvents', 'reviewEvents']:
            self.assertEqual([r for r in after[store] if r.get('profile') == 'student'],
                             [r for r in before[store] if r.get('profile') == 'student'], store)
        self.assertEqual(len(after['answers']) - len(before['answers']), 6)

    def test_json_formats_and_bulk_update_compatibility(self):
        self.open_editor('TEST-MULTIPLE')
        self.save()
        result = self.page.evaluate("""async () => {
          const q=await readOne('questions','TEST-MULTIPLE');
          const external=exportableQuestion(q);
          const imported=validateImportObject({schemaVersion:1,questions:[external]})[0];
          const file={questionUpdateFormat:QUESTION_UPDATE_FORMAT,formatVersion:1,schemaVersion:1,
            questions:[{...external,baseRevision:questionRevision(q),baseHash:await sha256Text(questionFingerprintSource(q))}]};
          const plan=await planQuestionUpdate(validateQuestionUpdateFile(file),await readAll('questions'));
          let rejected=0;
          for (const size of [1,7]) {
            try {validateImportObject({schemaVersion:1,questions:[{...external,
              options:Array.from({length:size},(_,i)=>({id:String(i+1),text:'確認用'})),correctAnswers:['1'],type:'single'}]});}
            catch {rejected++;}
          }
          file.questions[0].baseHash='0'.repeat(64);
          try {await planQuestionUpdate(validateQuestionUpdateFile(file),await readAll('questions'));}
          catch {rejected++;}
          return {options:imported.options,answers:imported.answers,unchanged:plan.unchanged,
            changes:plan.changes.length,rejected,dbVersion:db.version,
            backupFormat:BACKUP_FORMAT,backupVersion:BACKUP_VERSION};
        }""")
        q = next(q for q in self.questions if q['id'] == 'TEST-MULTIPLE')
        self.assertEqual(result, {'options': q['options'], 'answers': q['answers'],
                                 'unchanged': 1, 'changes': 0, 'rejected': 3,
                                 'dbVersion': 9, 'backupFormat': 'history-master-backup', 'backupVersion': 9})

    def test_touch_layout_and_enter_creates_line_within_one_option(self):
        for width, height in [(375, 812), (390, 844), (820, 1180)]:
            with self.subTest(width=width):
                self.page.set_viewport_size({'width': width, 'height': height})
                self.open_editor('TEST-SIX')
                self.choice(1).focus()
                self.choice(1).press('End')
                self.choice(1).press('Enter')
                self.page.keyboard.insert_text('入力した改行の次の行')
                self.assertEqual(self.page.locator('.edit-form textarea').count(), 8)
                self.assertIn('\n入力した改行の次の行', self.choice(1).input_value())
                layout = self.page.locator('.edit-form').evaluate("""form=>({
                  fits:document.documentElement.scrollWidth<=innerWidth,
                  controls:[...form.querySelectorAll('textarea,button')].every(el=>{
                    const rect=el.getBoundingClientRect();return rect.width>0&&rect.height>=44&&rect.left>=0&&rect.right<=innerWidth;
                  }),
                  textSize:[...form.querySelectorAll('textarea')].every(el=>parseFloat(getComputedStyle(el).fontSize)>=16)
                })""")
                self.assertEqual(layout, {'fits': True, 'controls': True, 'textSize': True})
                self.page.get_by_role('button', name='キャンセル', exact=True).click()


if __name__ == '__main__':
    unittest.main()
