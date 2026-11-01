"""Issue #20 Phase 1: 架空データのみで指摘・集約・DB移行・バックアップを検証。

実行方法はquestion_editor_test.pyを参照。Safari実機の保証ではない。
"""
import json
from pathlib import Path
import unittest

import history_navigation_test as navigation


class QuestionFeedbackTest(unittest.TestCase):
    setUpClass = classmethod(navigation.HistoryNavigationTest.setUpClass.__func__)
    tearDownClass = classmethod(navigation.HistoryNavigationTest.tearDownClass.__func__)
    setUp = navigation.HistoryNavigationTest.setUp
    tearDown = navigation.HistoryNavigationTest.tearDown
    ready = navigation.HistoryNavigationTest.ready
    install = navigation.HistoryNavigationTest.install
    snapshot = navigation.HistoryNavigationTest.snapshot
    quiz = navigation.HistoryNavigationTest.quiz
    answer = navigation.HistoryNavigationTest.answer
    screen = navigation.HistoryNavigationTest.screen
    second_tab = navigation.HistoryNavigationTest.second_tab

    def records(self):
        return self.page.evaluate('readAll("questionFeedback")')

    def report(self, comment='架空の指摘', category='explanation'):
        self.page.locator('#report-question').click()
        self.page.locator('#feedback-category').select_option(category)
        self.page.locator('#feedback-comment').fill(comment)
        self.page.locator('#feedback-save').click()
        self.page.wait_for_function('!feedbackSaving&&!document.querySelector("#feedback-dialog").open')
        return self.records()[-1]

    def admin(self):
        self.page.evaluate('navigate("admin")')
        self.screen('admin')
        if not self.page.locator('#feedback-panel').is_visible():
            self.page.locator('#toggle-feedback').click()
        self.page.wait_for_function('document.querySelector("#feedback-summary").textContent.includes("全")')

    def exchange(self, reports=None):
        return {'feedbackFormat': 'history-master-feedback', 'formatVersion': 1,
                'exportedAt': '2026-10-24T00:00:00.000Z', 'reports': reports or []}

    def seed(self, count=1):
        return self.page.evaluate('''async count=>{
          const q=allQuestionRecords().find(q=>q.id==='TEST-PLUSH-001'),at='2020-01-01T00:00:00.000Z';
          const base={questionId:q.id,questionRevision:questionRevision(q),questionHash:await sha256Text(questionFingerprintSource(q)),
            questionSnapshot:{...exportableQuestion(q),deleted:!!q.deleted},reporterRole:'learner',sourceProfile:'student',category:'answer',comment:'架空の指摘',createdAt:at};
          const reports=Array.from({length:count},()=>({...base,reportId:crypto.randomUUID()}));
          await importFeedbackRecords(reports);return reports;
        }''', count)

    def upload(self, obj):
        self.page.locator('#feedback-file').set_input_files({
            'name': 'synthetic-feedback.json', 'mimeType': 'application/json',
            'buffer': json.dumps(obj, ensure_ascii=False).encode()})
        self.page.wait_for_function('''()=>{
          const t=document.querySelector('#feedback-import-preview').textContent;
          return t.startsWith('検査OK')||t.startsWith('取り込めません');
        }''')
        return self.page.locator('#feedback-import-preview').inner_text()

    def test_before_answer_hidden_after_both_results_under_next(self):
        self.quiz()
        self.assertFalse(self.page.locator('#report-question').is_visible())
        for correct in [True, False]:
            self.answer(correct)
            self.assertTrue(self.page.locator('#report-question').is_visible())
            self.assertEqual(self.page.locator('#report-question').evaluate('el=>el.previousElementSibling.id'), 'next')
            self.page.locator('#next').click()
            self.page.wait_for_function('quizReady&&phase==="question"')
            self.assertFalse(self.page.locator('#report-question').is_visible())
        self.assertEqual(self.records(), [])

    def test_learner_categories_cancel_and_history_unchanged(self):
        self.quiz(); self.answer()
        before = self.snapshot()
        history = self.page.evaluate('[history.length,history.state]')
        self.page.locator('#report-question').click()
        self.assertEqual(self.page.locator('#feedback-category option').evaluate_all('els=>els.map(e=>e.value)'),
                         ['answer', 'explanation', 'too_hard', 'too_easy', 'other'])
        self.page.locator('#feedback-cancel').click()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.page.evaluate('[history.length,history.state]'), history)

    def test_save_persists_and_only_feedback_changes(self):
        self.quiz(); self.answer()
        before = self.snapshot()
        history = self.page.evaluate('[history.length,history.state]')
        report = self.report()
        self.assertEqual(self.page.locator('#notice').text_content(), '報告を保存しました')
        after = self.snapshot()
        for store in before:
            if store != 'questionFeedback':
                self.assertEqual(before[store], after[store], store)
        self.assertEqual(self.page.evaluate('[history.length,history.state]'), history)
        self.page.reload(); self.ready()
        self.assertEqual(self.records(), [report])

    def test_failed_save_keeps_input_and_retry_without_success(self):
        self.quiz(); self.answer()
        self.page.evaluate('''()=>{window.realSave=saveFeedbackRecord;saveFeedbackRecord=()=>Promise.reject(new Error('架空の容量不足'));}''')
        self.page.locator('#report-question').click()
        self.page.locator('#feedback-comment').fill('消えない架空入力')
        self.page.locator('#feedback-save').click()
        self.page.wait_for_function('!feedbackSaving')
        self.assertTrue(self.page.locator('#feedback-dialog').is_visible())
        self.assertEqual(self.page.locator('#feedback-comment').input_value(), '消えない架空入力')
        self.assertIn('保存できませんでした', self.page.locator('#feedback-save-status').inner_text())
        self.assertNotEqual(self.page.locator('#notice').text_content(), '報告を保存しました')
        self.assertEqual(self.records(), [])
        self.page.evaluate('()=>{saveFeedbackRecord=realSave;}')
        self.page.locator('#feedback-save').click()
        self.page.wait_for_function('!feedbackSaving&&!feedbackDraft')
        self.assertEqual(len(self.records()), 1)

    def test_multiple_and_shuffled_options_capture_original(self):
        self.page.evaluate('''async()=>{
          const q=await readOne('questions','TEST-PLUSH-001');q.answers=[2,0];q.shuffleOptions=true;
          await new Promise((ok,no)=>{const t=db.transaction('questions','readwrite');t.objectStore('questions').put(q);t.oncomplete=ok;t.onerror=no;});
          await loadImportedQuestions();
        }''')
        self.quiz(); self.answer()
        expected = self.page.evaluate('exportableQuestion(currentQuestion)')
        report = self.report()
        self.assertEqual(report['questionSnapshot'], dict(expected, deleted=False))
        self.assertEqual(report['questionId'], expected['id'])
        self.assertEqual(report['questionSnapshot']['correctAnswers'], ['3', '1'])
        self.assertNotIn('selected', report)

    def test_test_result_is_learner_test_and_admin_has_eight_categories(self):
        self.page.evaluate('navigateHome("test")')
        self.quiz(); self.answer()
        self.assertEqual(self.report()['sourceProfile'], 'test')
        self.assertEqual(self.records()[0]['reporterRole'], 'learner')
        self.admin()
        self.page.locator('#toggle-manage').click()
        self.page.locator('#manage-list .manager-item').first.get_by_role('button', name='指摘する', exact=True).click()
        self.assertEqual(self.page.locator('#feedback-category option').count(), 8)
        self.assertIn('解説：', self.page.locator('#feedback-target').inner_text())
        self.assertIn('✓ 正解', self.page.locator('#feedback-target').inner_text())
        self.page.locator('#feedback-category').select_option('fact')
        self.page.locator('#feedback-save').click()
        self.page.wait_for_function('!feedbackSaving&&!feedbackDraft')
        admin = [r for r in self.records() if r['reporterRole'] == 'admin'][0]
        self.assertNotIn('sourceProfile', admin)
        self.assertEqual(admin['category'], 'fact')

    def test_open_dialog_then_navigation_profile_and_next_invalidate(self):
        self.quiz(); self.answer()
        for action in ['navigateHome("test")', 'navigate("admin")', 'advance(currentEra,currentQuestion.id)']:
            self.page.locator('#report-question').click()
            self.page.evaluate(action)
            self.page.wait_for_function('!feedbackDraft')
            self.assertFalse(self.page.locator('#feedback-dialog').is_visible())
            self.page.evaluate('navigateHome("student")')
            self.quiz()
            if self.page.evaluate('phase') != 'result':
                self.answer()
        self.assertEqual(self.records(), [])

    def test_browser_back_forward_and_pageshow_invalidate(self):
        self.quiz(); self.answer()
        self.page.locator('#report-question').click()
        self.page.go_back(); self.screen('home')
        self.assertFalse(self.page.locator('#feedback-dialog').is_visible())
        self.page.go_forward(); self.screen('quiz'); self.page.wait_for_function('quizReady')
        self.page.locator('#report-question').click()
        self.page.evaluate("dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}))")
        self.page.wait_for_function('quizReady&&!feedbackDraft')
        self.assertEqual(self.records(), [])

    def test_delayed_hash_and_screen_change_does_not_save(self):
        self.quiz(); self.answer()
        self.page.evaluate('''()=>{const real=sha256Text;sha256Text=async v=>{await new Promise(ok=>window.releaseHash=ok);return real(v);};}''')
        self.page.locator('#report-question').click()
        self.page.locator('#feedback-save').click()
        self.page.wait_for_function('typeof releaseHash==="function"')
        self.page.evaluate('navigateHome("test")')
        self.page.evaluate('releaseHash()')
        self.page.wait_for_function('!feedbackSaving')
        self.assertEqual(self.records(), [])

    def test_other_tab_advances_result_then_save_rejected(self):
        self.quiz(); self.answer()
        self.page.locator('#report-question').click()
        second = self.second_tab()
        second.evaluate('navigate("quiz","student","E01")')
        second.wait_for_function('quizReady')
        second.locator('#next').click()
        second.wait_for_function('quizReady&&phase==="question"')
        self.page.locator('#feedback-save').click()
        self.page.wait_for_function('!feedbackSaving')
        self.assertEqual(self.records(), [])
        self.assertIn('別タブ', self.page.locator('#feedback-save-status').inner_text())

    def test_import_preview_only_repeat_and_status_preserved(self):
        reports = self.seed()
        self.admin()
        self.page.evaluate('''async()=>{const r=(await readAll('questionFeedback'))[0];await changeFeedbackStatus(r.reportId,'resolved',r);}''')
        before = self.records()
        obj = self.exchange(reports)
        text = self.upload(obj)
        self.assertIn('重複1件', text)
        self.assertEqual(self.records(), before)
        for _ in range(2):
            self.page.locator('#feedback-import').click()
            self.page.wait_for_function('!feedbackImporting&&!feedbackPlan')
            self.assertEqual(self.records(), before)
            self.upload(obj)

    def test_new_import_waits_for_button(self):
        reports = self.seed()
        self.page.evaluate('''async()=>{const t=db.transaction('questionFeedback','readwrite');t.objectStore('questionFeedback').clear();await new Promise(ok=>t.oncomplete=ok);}''')
        self.admin(); self.upload(self.exchange(reports))
        self.assertEqual(self.records(), [])
        self.page.locator('#feedback-import').click()
        self.page.wait_for_function('!feedbackImporting&&!feedbackPlan')
        self.assertEqual(len(self.records()), 1)
        self.assertEqual(self.records()[0]['status'], 'unreviewed')
        self.assertIn('新規1件', self.page.locator('#feedback-import-preview').inner_text())

    def test_conflict_detected_before_save(self):
        reports = self.seed(); self.admin()
        reports[0]['comment'] = '別内容'
        self.assertIn('衝突1件', self.upload(self.exchange(reports)))
        self.assertFalse(self.page.locator('#feedback-import').is_visible())
        self.assertEqual(self.records()[0]['comment'], '架空の指摘')

    def test_file_duplicate_id_and_bad_fields_rejected(self):
        report = self.seed()[0]; self.admin()
        self.assertIn('重複', self.upload(self.exchange([report, report])))
        for field, value in [('reportId', 'bad'), ('createdAt', '2020-02-31T00:00:00.000Z'),
                             ('category', 'invalid'), ('comment', 'あ' * 501), ('status', 'resolved'),
                             ('questionHash', '0' * 64), ('sourceProfile', 'family')]:
            with self.subTest(field=field):
                invalid = dict(report); invalid[field] = value
                self.assertIn('取り込めません', self.upload(self.exchange([invalid])))
        obj = self.exchange([report]); obj['formatVersion'] = 2
        self.assertIn('取り込めません', self.upload(obj))

    def test_snapshot_invalid_and_extra_personal_field_rejected(self):
        report = self.seed()[0]; self.admin()
        for edit in ['id', 'answers', 'extra']:
            obj = self.exchange([json.loads(json.dumps(report))]); snap = obj['reports'][0]['questionSnapshot']
            if edit == 'id': snap['id'] = 'ANOTHER-ID'
            elif edit == 'answers': snap['correctAnswers'] = ['999']
            else: obj['reports'][0]['personalName'] = '架空名'
            self.assertIn('取り込めません', self.upload(obj))

    def test_limits_bytes_and_report_count(self):
        self.admin()
        data = self.exchange([None] * 5001)
        self.assertIn('5,000', self.upload(data))
        self.page.locator('#feedback-file').set_input_files({'name': 'oversize.json', 'mimeType': 'application/json', 'buffer': b' ' * (8 * 1024 * 1024 + 1)})
        self.page.wait_for_function('document.querySelector("#feedback-import-preview").textContent.includes("8MiB")')
        self.assertEqual(self.records(), [])

    def test_import_mid_transaction_failure_rolls_back(self):
        reports = self.seed(3)
        self.page.evaluate('''async()=>{const t=db.transaction('questionFeedback','readwrite');t.objectStore('questionFeedback').clear();await new Promise(ok=>t.oncomplete=ok);}''')
        self.admin(); self.upload(self.exchange(reports))
        self.page.evaluate('''()=>{
          const original=IDBObjectStore.prototype.add;let calls=0;
          IDBObjectStore.prototype.add=function(...args){
            if(this.name==='questionFeedback'&&++calls===2){this.transaction.abort();return {};}
            return original.apply(this,args);
          };
        }''')
        self.page.locator('#feedback-import').click()
        self.page.wait_for_function('!feedbackImporting')
        self.assertEqual(self.records(), [])
        self.assertIn('全件ロールバック', self.page.locator('#feedback-import-preview').inner_text())

    def test_conflict_created_after_preview_rolls_back_new_records(self):
        reports = self.seed(2); self.admin()
        self.page.evaluate('''async()=>{const t=db.transaction('questionFeedback','readwrite');t.objectStore('questionFeedback').clear();await new Promise(ok=>t.oncomplete=ok);}''')
        self.upload(self.exchange(reports))
        self.page.evaluate('r=>importFeedbackRecords([{...r,comment:"別タブの競合"}])', reports[1])
        self.page.locator('#feedback-import').click(); self.page.wait_for_function('!feedbackImporting')
        self.assertEqual(len(self.records()), 1)
        self.assertEqual(self.records()[0]['comment'], '別タブの競合')

    def test_status_compare_and_set_across_tabs(self):
        reports = self.seed(); self.admin()
        old = self.records()[0]
        second = self.second_tab(); second.evaluate('navigate("admin")')
        second.evaluate('r=>changeFeedbackStatus(r.reportId,"reviewing",r)', old)
        message = self.page.evaluate('async r=>{try{await changeFeedbackStatus(r.reportId,"resolved",r);return "";}catch(e){return e.message;}}', old)
        self.assertIn('別タブ', message)
        self.assertEqual(self.records()[0]['status'], 'reviewing')
        self.page.evaluate('renderFeedback()')
        self.assertEqual(self.page.locator('#feedback-list select').input_value(), 'reviewing')
        self.page.locator('#feedback-list select').select_option('fix_pending')
        self.page.wait_for_function('document.querySelector("#feedback-list select").value==="fix_pending"&&!document.querySelector("#feedback-list select").disabled')
        self.assertEqual(self.records()[0]['status'], 'fix_pending')

    def test_state_change_only_admin(self):
        self.seed()
        message = self.page.evaluate('''async()=>{const r=(await readAll('questionFeedback'))[0];try{await changeFeedbackStatus(r.reportId,'resolved',r);return '';}catch(e){return e.message;}}''')
        self.assertIn('保護者', message)
        self.assertEqual(self.records()[0]['status'], 'unreviewed')

    def test_version_hash_and_missing_problem_retain_snapshot(self):
        reports = self.seed(2)
        # 同じrevisionでも解説変更を検出。
        self.page.evaluate('''async()=>{const t=db.transaction('questions','readwrite'),s=t.objectStore('questions'),r=s.get('TEST-PLUSH-001');r.onsuccess=()=>s.put({...r.result,why:'架空の変更解説'});await new Promise(ok=>t.oncomplete=ok);}''')
        self.admin(); self.page.evaluate('renderFeedback()')
        self.assertIn('要確認2件', self.page.locator('#feedback-summary').inner_text())
        self.page.locator('#feedback-filter-version').select_option('mismatch')
        self.page.wait_for_function('document.querySelectorAll("#feedback-list .manager-item").length===2')
        self.page.evaluate('''async()=>{const t=db.transaction('questions','readwrite');t.objectStore('questions').delete('TEST-PLUSH-001');await new Promise(ok=>t.oncomplete=ok);await renderFeedback();}''')
        self.page.locator('#feedback-list details').first.locator('summary').click()
        self.assertIn(reports[0]['questionSnapshot']['question'], self.page.locator('#feedback-list').inner_text())
        self.assertEqual(len(self.records()), 2)

    def test_import_different_revision_is_retained_and_counted(self):
        reports = self.seed()
        report = self.page.evaluate('''async r=>{
          r.reportId=crypto.randomUUID();r.questionRevision=2;
          r.questionHash=await sha256Text(questionFingerprintSource(feedbackQuestion(r.questionSnapshot,2)));return r;
        }''', reports[0])
        self.admin(); self.assertIn('版不一致1件', self.upload(self.exchange([report])))
        self.page.locator('#feedback-import').click(); self.page.wait_for_function('!feedbackImporting')
        self.assertEqual(len(self.records()), 2)
        self.assertEqual(sorted(r['questionRevision'] for r in self.records()), [1, 2])

    def test_filters_and_per_question_count(self):
        self.seed(2); self.admin()
        self.page.evaluate('renderFeedback()')
        self.assertEqual(self.page.locator('#feedback-list .feedback-select').first.inner_text(), 'TEST-PLUSH-001（計2件）')
        for selector, value in [('feedback-era', 'E04'), ('feedback-filter-category', 'fact'), ('feedback-filter-status', 'resolved')]:
            self.page.locator('#' + selector).select_option(value)
            self.page.wait_for_function('document.querySelectorAll("#feedback-list .manager-item").length===0')
            self.page.locator('#' + selector).select_option('all')
            self.page.wait_for_function('document.querySelectorAll("#feedback-list .manager-item").length===2')

    def test_export_selected_and_all_without_status_or_deletion(self):
        self.seed(2); self.admin(); before = self.snapshot()
        self.page.locator('#feedback-list input[type=checkbox]').first.check()
        self.assertIn('選択1件', self.page.locator('#feedback-summary').inner_text())
        for button, count in [('feedback-export-selected', 1), ('feedback-export-all', 2)]:
            with self.page.expect_download() as download:
                self.page.locator('#' + button).click()
            obj = json.loads(Path(download.value.path()).read_text())
            self.assertEqual(obj['feedbackFormat'], 'history-master-feedback')
            self.assertEqual(obj['formatVersion'], 1)
            self.assertEqual(len(obj['reports']), count)
            for report in obj['reports']:
                self.assertNotIn('status', report)
                self.assertNotIn('statusUpdatedAt', report)
            self.page.evaluate('obj=>validateFeedbackExchange(obj)', obj)
        self.assertEqual(self.snapshot(), before)

    def test_untrusted_strings_display_as_text(self):
        report = self.seed()[0]
        report['comment'] = '<img src=x onerror="window.feedbackInjected=true">'
        report = self.page.evaluate('''async r=>{
          r.reportId=crypto.randomUUID();r.questionSnapshot.question='<svg onload="window.feedbackInjected=true">架空の文章';
          r.questionHash=await sha256Text(questionFingerprintSource(feedbackQuestion(r.questionSnapshot,r.questionRevision)));return r;
        }''', report)
        self.admin(); self.upload(self.exchange([report]))
        self.page.locator('#feedback-import').click(); self.page.wait_for_function('!feedbackImporting')
        self.assertEqual(self.page.locator('#feedback-list img, #feedback-list svg').count(), 0)
        self.assertIsNone(self.page.evaluate('window.feedbackInjected'))
        self.assertIn('<img src=x', self.page.locator('#feedback-list').inner_text())

    def test_backup_v1_through_v7_keep_feedback(self):
        self.seed(); before = self.records()
        result = self.page.evaluate('''async()=>{
          const snapshot=await snapshotAllStores(),results=[];
          for(let version=1;version<=7;version++){
            const data=structuredClone(snapshot);
            // 旧版が保存していなかった指摘が紛れても採用しない。
            data.questionFeedback=[{invalid:true}];
            const checked=validateBackup({backupFormat:BACKUP_FORMAT,backupVersion:version,data});
            await replaceAllStores(checked);results.push(await readAll('questionFeedback'));
          }return results;
        }''')
        self.assertEqual(result, [before] * 7)

    def test_backup_v8_replaces_all_fifteen_stores(self):
        self.seed(2); before = self.snapshot()
        self.page.evaluate('''async()=>{
          window.savedBackup=validateBackup({backupFormat:BACKUP_FORMAT,backupVersion:8,data:await snapshotAllStores()});
          await performReset({},true);await replaceAllStores(savedBackup);
        }''')
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(len(before), 16)
        self.assertEqual(self.page.evaluate('[DB_VERSION,BACKUP_VERSION]'), [9, 9])

    def test_v8_backup_rejects_bad_reports(self):
        self.seed()
        for mutation in ['d.questionFeedback[0].status="bad"', 'd.questionFeedback.push(d.questionFeedback[0])', 'delete d.questionFeedback']:
            message = self.page.evaluate('''mutation=>{
              return snapshotAllStores().then(d=>{eval(mutation);try{validateBackup({backupFormat:BACKUP_FORMAT,backupVersion:8,data:d});return '';}catch(e){return e.message;}});
            }''', mutation)
            self.assertTrue(message)

    def test_restore_preview_and_confirmation_old_keep_v8_replace(self):
        self.seed(); self.admin()
        self.page.locator('#admin-backup-group > summary').click(); self.page.locator('#toggle-backup').click()
        for version in [7, 8]:
            obj = self.page.evaluate('async v=>({backupFormat:BACKUP_FORMAT,backupVersion:v,data:await snapshotAllStores()})', version)
            self.page.locator('#backup-file').set_input_files({'name': 'synthetic-backup.json', 'mimeType': 'application/json', 'buffer': json.dumps(obj).encode()})
            self.page.wait_for_function('pendingRestore!==null')
            preview = self.page.locator('#backup-preview').inner_text()
            self.assertIn('保持' if version == 7 else '現在の指摘1件も置き換え', preview)
            messages = []
            self.page.once('dialog', lambda d: messages.append(d.message))
            self.page.locator('#backup-restore').click(); self.page.wait_for_function('!backingUp&&pendingRestore===null')
            self.assertIn('保持' if version == 7 else '指摘も', messages[0])
            self.assertEqual(len(self.records()), 1)

    def test_v8_restore_midway_failure_rolls_back_every_store(self):
        self.seed(2); before = self.snapshot()
        result = self.page.evaluate('''async()=>{
          const data=await snapshotAllStores();data.questionFeedback[1]={...data.questionFeedback[1],reportId:undefined};
          data.questions=[];
          try{await replaceAllStores(data);return false;}catch{return true;}
        }''')
        self.assertTrue(result)
        self.assertEqual(self.snapshot(), before)

    def test_history_reset_and_hide_keep_feedback_full_reset_removes(self):
        self.seed(); before = self.records()
        for choice in [{'student': True}, {'test': True}, {'hideImported': True, 'hideSamples': True}]:
            self.page.evaluate('choice=>performReset(choice)', choice)
            self.assertEqual(self.records(), before)
        self.page.evaluate('performReset({},true)')
        self.assertEqual(self.records(), [])
        self.assertTrue(all(not rows for rows in self.snapshot().values()))

    def test_reset_preview_and_full_warning_include_feedback_count(self):
        self.seed(2); self.admin()
        self.page.locator('#admin-other-group > summary').click(); self.page.locator('#toggle-reset').click()
        self.page.wait_for_function('document.querySelector("#reset-preview").textContent.includes("指摘：2件")')
        messages = []
        self.page.once('dialog', lambda d: messages.append(d.message))
        self.page.locator('#reset-all').click()
        self.page.wait_for_function('document.querySelector("#reset-preview").textContent.startsWith("完全初期化しました")')
        self.assertIn('指摘 2件', messages[0])
        self.assertEqual(self.records(), [])

    def test_layout_mobile_and_ipad(self):
        self.quiz(); self.answer()
        for width, height in [(375, 812), (390, 844), (768, 1024), (1024, 768)]:
            self.page.set_viewport_size({'width': width, 'height': height})
            self.assertGreaterEqual(self.page.locator('#report-question').evaluate('el=>el.getBoundingClientRect().height'), 44)
            self.page.locator('#report-question').click()
            self.assertTrue(self.page.locator('#feedback-dialog').evaluate('el=>{const r=el.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.bottom<=innerHeight;}'))
            self.page.locator('#feedback-comment').fill('あ' * 500)
            self.page.locator('#feedback-cancel').click()
            self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
        self.seed(); self.admin()
        for width, height in [(375, 812), (390, 844), (768, 1024), (1024, 768)]:
            self.page.set_viewport_size({'width': width, 'height': height})
            self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth<=innerWidth'))

    def test_db7_migration_preserves_fourteen_stores_and_is_repeatable(self):
        # 別の一時コンテキストで現行14ストアとv7を用意し、通常の起動経路を通す。
        context = self.browser.new_context()
        page = context.new_page()
        source = (Path(__file__).resolve().parents[1] / 'index.html').read_text()
        old = source.replace('const DB_VERSION = 9;', 'const DB_VERSION = 7;')
        old = old.replace('      if (!database.objectStoreNames.contains("questionFeedback")) database.createObjectStore("questionFeedback", {keyPath:"reportId"});', '')
        old = old.replace(', "questionFeedback", "studySets"];', '];')
        old = old.replace('      if (!database.objectStoreNames.contains("studySets")) database.createObjectStore("studySets", {keyPath:"key"});', '')
        old = old.replace('  const sets=await readAll("studySets");', '  const sets=[];')
        page.route(self.url, lambda route: route.fulfill(body=old, content_type='text/html'))
        page.goto(self.url); self.ready(page)
        from plush_test import FIXTURE_HELPERS
        page.evaluate(FIXTURE_HELPERS)
        page.evaluate('async()=>{await plushInstall(plushFixture());}')
        before = self.snapshot(page)
        self.assertEqual(len(before), 14)
        page.unroute(self.url)
        page.reload(); self.ready(page)
        after = self.snapshot(page)
        self.assertEqual(page.evaluate('[db.version,db.objectStoreNames.length]'), [9, 16])
        for name in before:
            self.assertEqual(after[name], before[name], name)
        self.assertEqual(after['questionFeedback'], [])
        page.reload(); self.ready(page)
        self.assertEqual(self.snapshot(page), after)
        context.close()

    def test_database_versionchange_closes_old_connection(self):
        self.page.evaluate('''()=>{
          window.upgradeDone=false;
          const req=indexedDB.open(DB_NAME,DB_VERSION+1);
          req.onsuccess=()=>{req.result.close();upgradeDone=true;};
        }''')
        self.page.wait_for_function('upgradeDone')
        self.assertFalse(self.page.evaluate('appReady'))
        self.assertIn('別タブ', self.page.locator('#notice').text_content())


    def old_database(self):
        context = self.browser.new_context()
        page = context.new_page()
        source = (Path(__file__).resolve().parents[1] / 'index.html').read_text()
        old = source.replace('const DB_VERSION = 9;', 'const DB_VERSION = 7;')
        old = old.replace('      if (!database.objectStoreNames.contains("questionFeedback")) database.createObjectStore("questionFeedback", {keyPath:"reportId"});', '')
        old = old.replace(', "questionFeedback", "studySets"];', '];')
        old = old.replace('      if (!database.objectStoreNames.contains("studySets")) database.createObjectStore("studySets", {keyPath:"key"});', '')
        old = old.replace('  const sets=await readAll("studySets");', '  const sets=[];')
        page.route(self.url, lambda route: route.fulfill(body=old, content_type='text/html'))
        page.goto(self.url); self.ready(page)
        from plush_test import FIXTURE_HELPERS
        page.evaluate(FIXTURE_HELPERS)
        page.evaluate('async()=>{await plushInstall(plushFixture());}')
        return context, page, source

    def test_blocked_upgrade_waits_then_preserves_data(self):
        context, page, source = self.old_database()
        before = self.snapshot(page)
        page.evaluate('()=>{db.onversionchange=()=>{};}')
        second = context.new_page()
        second.goto(self.url)
        second.wait_for_function('document.querySelector("#notice").textContent.includes("更新待ち")')
        self.assertFalse(second.evaluate('appReady'))
        self.assertEqual(self.snapshot(page), before)
        page.evaluate('db.close()')
        self.ready(second)
        after = self.snapshot(second)
        for name in before:
            self.assertEqual(after[name], before[name], name)
        self.assertEqual(after['questionFeedback'], [])
        context.close()

    def test_failed_upgrade_keeps_original_database_and_shows_cause(self):
        context, page, source = self.old_database()
        before = self.snapshot(page)
        failed = source.replace('database.createObjectStore("questionFeedback", {keyPath:"reportId"});',
                                'database.createObjectStore("questionFeedback", {keyPath:"reportId"}); request.transaction.abort();')
        page.unroute(self.url)
        page.route(self.url, lambda route: route.fulfill(body=failed, content_type='text/html'))
        page.reload()
        page.wait_for_function('document.querySelector("#notice").textContent.includes("起動・移行に失敗")')
        self.assertIn('データは削除していません', page.locator('#notice').inner_text())
        original = page.evaluate("""()=>new Promise((ok,no)=>{
          const r=indexedDB.open(DB_NAME,7);
          r.onsuccess=()=>{const d=r.result,names=[...d.objectStoreNames],t=d.transaction(names,'readonly'),requests=names.map(n=>[n,t.objectStore(n).getAll()]);
            t.oncomplete=()=>{ok(Object.fromEntries(requests.map(([n,r])=>[n,r.result])));d.close();};};
          r.onerror=()=>no(r.error);
        })""")
        self.assertEqual(original, before)
        context.close()

    def test_pagehide_closes_dialog_without_write(self):
        self.quiz(); self.answer()
        self.page.locator('#report-question').click()
        self.page.evaluate("dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}))")
        self.assertFalse(self.page.locator('#feedback-dialog').is_visible())
        self.assertEqual(self.records(), [])

    def test_changed_question_in_other_tab_blocks_stale_report(self):
        self.quiz(); self.answer()
        self.page.locator('#report-question').click()
        self.page.evaluate("""async()=>{
          const t=db.transaction('questions','readwrite'),s=t.objectStore('questions'),r=s.get(currentQuestion.id);
          r.onsuccess=()=>s.put({...r.result,why:'別タブの架空の解説更新'});await new Promise(ok=>t.oncomplete=ok);
        }""")
        self.page.locator('#feedback-save').click(); self.page.wait_for_function('!feedbackSaving')
        self.assertIn('問題の版が変わりました', self.page.locator('#feedback-save-status').inner_text())
        self.assertEqual(self.records(), [])

    def test_real_save_transaction_abort_has_no_success(self):
        self.quiz(); self.answer()
        self.page.locator('#report-question').click()
        self.page.locator('#feedback-comment').fill('架空の再試行文')
        self.page.evaluate("""()=>{
          const add=IDBObjectStore.prototype.add;
          IDBObjectStore.prototype.add=function(...args){if(this.name==='questionFeedback'){this.transaction.abort();return {};}return add.apply(this,args);};
        }""")
        self.page.locator('#feedback-save').click(); self.page.wait_for_function('!feedbackSaving')
        self.assertIn('保存できませんでした', self.page.locator('#feedback-save-status').inner_text())
        self.assertNotIn('報告を保存しました', self.page.locator('#notice').text_content())
        self.assertEqual(self.page.locator('#feedback-comment').input_value(), '架空の再試行文')
        self.assertEqual(self.records(), [])

    def test_admin_report_needs_no_answer_and_changes_only_feedback(self):
        self.admin(); self.page.locator('#toggle-manage').click()
        before = self.snapshot()
        self.page.locator('#manage-list .manager-item').first.get_by_role('button', name='指摘する', exact=True).click()
        self.page.locator('#feedback-category').select_option('options')
        self.page.locator('#feedback-save').click(); self.page.wait_for_function('!feedbackSaving&&!feedbackDraft')
        after = self.snapshot()
        self.assertEqual(len(after['questionFeedback']), 1)
        self.assertEqual(after['questionFeedback'][0]['reporterRole'], 'admin')
        for name in before:
            if name != 'questionFeedback':
                self.assertEqual(before[name], after[name], name)

    def test_export_all_splits_into_importable_files(self):
        self.seed(5001); self.admin()
        downloads = []
        self.page.on('download', lambda d: downloads.append(d))
        # 案内文の更新とdownloadイベントの到着は非同期。両ファイルを待ってから件数を検証する。
        with self.page.expect_download(predicate=lambda d: d.suggested_filename.endswith('-1.json')), \
                self.page.expect_download(predicate=lambda d: d.suggested_filename.endswith('-2.json')):
            self.page.locator('#feedback-export-all').click()
        self.page.wait_for_function('document.querySelector("#notice").textContent.includes("2ファイル")')
        self.assertEqual(len(downloads), 2)
        counts = []
        for download in downloads:
            path = Path(download.path())
            self.assertLessEqual(path.stat().st_size, 8 * 1024 * 1024)
            obj = json.loads(path.read_text())
            counts.append(len(obj['reports']))
            self.page.evaluate('obj=>validateFeedbackExchange(obj)', obj)
        self.assertEqual(counts, [5000, 1])
        self.assertEqual(len(self.records()), 5001)

if __name__ == '__main__':
    unittest.main()
