"""Issue #20 Phase 2: 改善依頼JSONと修正後の指摘確認。公開可能な架空データのみ。"""
import json
from pathlib import Path
import unittest

import history_navigation_test as navigation
import question_feedback_test as feedback


class ImprovementRequestTest(unittest.TestCase):
    setUpClass = classmethod(navigation.HistoryNavigationTest.setUpClass.__func__)
    tearDownClass = classmethod(navigation.HistoryNavigationTest.tearDownClass.__func__)
    setUp = navigation.HistoryNavigationTest.setUp
    tearDown = navigation.HistoryNavigationTest.tearDown
    ready = navigation.HistoryNavigationTest.ready
    install = navigation.HistoryNavigationTest.install
    screen = navigation.HistoryNavigationTest.screen
    snapshot = navigation.HistoryNavigationTest.snapshot
    seed = feedback.QuestionFeedbackTest.seed
    admin = feedback.QuestionFeedbackTest.admin

    def pack(self):
        return self.page.evaluate('''async()=>buildImprovementRequest(
            await readAll("questionFeedback"), await readAll("questions"))''')

    def test_pack_has_unique_format_current_content_and_update_baseline(self):
        self.seed(2)
        data = self.pack()
        self.assertEqual((data["improvementRequestFormat"], data["formatVersion"]),
                         ("history-master-improvement-request", 1))
        self.assertEqual((data["questionCount"], data["reportCount"]), (1, 2))
        q = data["questions"][0]
        self.assertEqual(q["questionId"], "TEST-PLUSH-001")
        self.assertEqual(q["sourceType"], "imported")
        self.assertTrue(q["updateEligible"])
        self.assertEqual(q["currentRevision"], q["baseRevision"])
        self.assertEqual(len(q["baseHash"]), 64)
        self.assertEqual(q["currentQuestion"]["question"],
                         self.page.evaluate('importedQuestions.find(item=>item.id==="TEST-PLUSH-001").q'))
        self.assertEqual(q["currentQuestion"], self.page.evaluate(
            'async()=>exportableQuestion(await readOne("questions","TEST-PLUSH-001"))'))
        self.assertEqual(q["baseHash"], self.page.evaluate(
            'async()=>sha256Text(questionFingerprintSource(await readOne("questions","TEST-PLUSH-001")))'))
        self.assertEqual(len(q["reports"]), 2)
        self.assertEqual(len({x["reportId"] for x in q["reports"]}), 2)
        self.assertTrue(all(x["versionMismatch"] is False for x in q["reports"]))

    def test_pack_is_not_an_update_or_feedback_exchange_file(self):
        self.seed()
        pack = self.pack()
        self.assertNotIn("questionUpdateFormat", pack)
        self.assertNotIn("feedbackFormat", pack)
        result = self.page.evaluate('''pack=>({
            acceptsUpdate: (()=>{try{validateQuestionUpdateFile(pack);return true;}catch(e){return false;}})(),
            acceptsFeedback: (()=>{try{return pack.feedbackFormat===FEEDBACK_FORMAT;}catch(e){return false;}})()
        })''', pack)
        self.assertEqual(result, {"acceptsUpdate": False, "acceptsFeedback": False})

    def test_pending_export_only_unreviewed_and_reviewing(self):
        reports = self.seed(3)
        self.admin()
        self.page.evaluate('''async ids=>{
            const all=await readAll("questionFeedback");
            await changeFeedbackStatus(ids[1],"reviewing",all.find(r=>r.reportId===ids[1]));
            const updated=await readAll("questionFeedback");
            await changeFeedbackStatus(ids[2],"resolved",updated.find(r=>r.reportId===ids[2]));
        }''', [r["reportId"] for r in reports])
        with self.page.expect_download() as event:
            self.page.locator("#feedback-improvement-pending").click()
        pack = json.loads(Path(event.value.path()).read_text(encoding="utf-8"))
        self.assertEqual(pack["reportCount"], 2)
        self.assertEqual({x["status"] for x in pack["questions"][0]["reports"]},
                         {"unreviewed", "reviewing"})

    def test_selection_can_export_resolved_reports_explicitly(self):
        reports=self.seed(2)
        self.admin()
        self.page.evaluate('''async id=>{
            const rows=await readAll("questionFeedback");
            await changeFeedbackStatus(id,"resolved",rows.find(x=>x.reportId===id));
            feedbackSelected.add(id);
        }''', reports[0]["reportId"])
        with self.page.expect_download() as event:
            self.page.locator("#feedback-improvement-selected").click()
        pack=json.loads(Path(event.value.path()).read_text(encoding="utf-8"))
        self.assertEqual(pack["reportCount"],1)
        self.assertEqual(pack["questions"][0]["reports"][0]["status"],"resolved")

    def test_empty_pack_shows_message_without_download(self):
        self.admin()
        self.page.locator("#feedback-improvement-pending").click()
        self.page.wait_for_function('document.querySelector("#feedback-improvement-status").textContent.includes("未確認・確認中の指摘がありません")')
        self.assertIn("未確認・確認中の指摘がありません",
                      self.page.locator("#feedback-improvement-status").inner_text())

    def test_export_does_not_touch_any_indexeddb_store(self):
        self.seed()
        before=self.snapshot()
        self.admin()
        with self.page.expect_download():
            self.page.locator("#feedback-improvement-pending").click()
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(self.page.evaluate('[DB_VERSION,BACKUP_VERSION,db.objectStoreNames.length]'),
                         [9,9,16])

    def test_missing_problem_keeps_snapshot_and_is_not_update_eligible(self):
        self.seed()
        pack=self.page.evaluate('''async()=>buildImprovementRequest(
            await readAll("questionFeedback"), [])''')
        q=pack["questions"][0]
        self.assertEqual(q["sourceType"],"missing")
        self.assertFalse(q["updateEligible"])
        self.assertIsNone(q["currentQuestion"])
        self.assertIsNone(q["baseRevision"])
        self.assertIsNone(q["baseHash"])
        self.assertTrue(q["reports"][0]["versionMismatch"])
        self.assertIn("questionSnapshot",q["reports"][0])

    def test_hidden_imported_problem_is_not_update_eligible(self):
        self.seed()
        pack=self.page.evaluate('''async()=>{
            const qs=await readAll("questions");
            const target=qs.find(q=>q.id==="TEST-PLUSH-001");target.deleted=true;
            return buildImprovementRequest(await readAll("questionFeedback"),qs);
        }''')
        q=pack["questions"][0]
        self.assertEqual(q["sourceType"],"imported")
        self.assertFalse(q["updateEligible"])
        self.assertIsNone(q["baseRevision"])
        self.assertIn("復元",q["updateRestriction"])

    def test_builtin_sample_requires_app_code_change(self):
        pack=self.page.evaluate('''async()=>{
            const q=SAMPLE_QUESTIONS[0],at=new Date().toISOString();
            const report={reportId:crypto.randomUUID(),questionId:q.id,questionRevision:questionRevision(q),
              questionHash:await sha256Text(questionFingerprintSource(q)),
              questionSnapshot:{...exportableQuestion(q),deleted:false},
              reporterRole:"admin",category:"fact",comment:"架空の報告",createdAt:at,
              status:"unreviewed",statusUpdatedAt:at};
            return buildImprovementRequest([report],await readAll("questions"));
        }''')
        q=pack["questions"][0]
        self.assertEqual(q["sourceType"],"builtin-sample")
        self.assertFalse(q["updateEligible"])
        self.assertIsNone(q["baseHash"])
        self.assertIn("アプリ本体",q["updateRestriction"])

    def test_current_explanation_change_marks_mismatch_and_fields(self):
        self.seed()
        pack=self.page.evaluate('''async()=>{
            const qs=await readAll("questions");
            qs.find(q=>q.id==="TEST-PLUSH-001").why="修正後の架空の解説";
            return buildImprovementRequest(await readAll("questionFeedback"),qs);
        }''')
        report=pack["questions"][0]["reports"][0]
        self.assertTrue(report["versionMismatch"])
        self.assertIn("explanation",report["changedFields"])

    def test_exported_baseline_works_with_existing_update_validator(self):
        self.seed()
        data=self.pack()
        result=self.page.evaluate('''async data=>{
            const entry=data.questions[0];
            const obj={questionUpdateFormat:QUESTION_UPDATE_FORMAT,formatVersion:QUESTION_UPDATE_VERSION,
              schemaVersion:1,exportedAt:data.exportedAt,
              questions:[{...entry.currentQuestion,baseRevision:entry.baseRevision,baseHash:entry.baseHash}]};
            const valid=validateQuestionUpdateFile(obj);
            const plan=await planQuestionUpdate(valid,await readAll("questions"));
            obj.questions[0].explanation+=" 追記の架空説明";
            const changed=await planQuestionUpdate(validateQuestionUpdateFile(obj),await readAll("questions"));
            return {unchanged:plan.unchanged,changes:plan.changes.length,
              changed:changed.changes.length,resets:changed.resetCount};
        }''',data)
        self.assertEqual(result,{"unchanged":1,"changes":0,"changed":1,"resets":0})

    def test_report_comparison_and_manual_fix_pending_only(self):
        self.seed()
        self.page.evaluate('''async()=>{
            const q=await readOne("questions","TEST-PLUSH-001");
            q.why="修正後の架空解説";
            await new Promise((resolve,reject)=>{
                const tx=db.transaction("questions","readwrite");
                tx.objectStore("questions").put(q);
                tx.oncomplete=resolve;tx.onerror=reject;
            });
            await loadImportedQuestions();
        }''')
        self.admin()
        self.page.locator("#feedback-refresh").click()
        self.page.wait_for_function('document.querySelector("#feedback-list").textContent.includes("要確認")')
        self.assertEqual(self.page.evaluate('(async()=> (await readAll("questionFeedback"))[0].status)()'),
                         "unreviewed")
        self.page.get_by_text("報告時と現在の問題を比較").click()
        self.assertIn("修正後の架空解説",self.page.locator("#feedback-list").inner_text())
        self.page.get_by_role("button",name="修正確認待ちにする（保護者確認）").click()
        self.page.wait_for_function('''async()=>(
          await readAll("questionFeedback"))[0].status==="fix_pending"''')
        self.assertEqual(len(self.page.evaluate('readAll("questionFeedback")')),1)

    def test_101_different_questions_rejected_before_download(self):
        self.seed()
        err=self.page.evaluate('''async()=>{
            const report=(await readAll("questionFeedback"))[0],qs=await readAll("questions");
            const many=Array.from({length:101},(_,i)=>{
              const id="TEST-BULK-"+String(i).padStart(3,"0");
              return {...report,reportId:crypto.randomUUID(),questionId:id,
                questionSnapshot:{...report.questionSnapshot,id}};
            });
            try {await buildImprovementRequest(many,qs);return null;}catch(e){return e.message;}
        }''')
        self.assertIn("100問",err)

    def test_report_json_does_not_include_learning_history_or_coin_balance(self):
        self.seed()
        pack=self.pack()
        text=json.dumps(pack,ensure_ascii=False)
        self.assertNotIn('"answers"', text)
        self.assertNotIn('"progress"', text)
        self.assertNotIn('"coinEvents"', text)
        self.assertNotIn('"arcadePrizes"', text)
        self.assertNotIn('"studentName"', text)


    def update_file(self, pack):
        entries = [dict(q['currentQuestion'], baseRevision=q['baseRevision'], baseHash=q['baseHash'])
                   for q in pack['questions'] if q['updateEligible']]
        return {'questionUpdateFormat': 'history-master-question-update', 'formatVersion': 1,
                'schemaVersion': 1, 'exportedAt': pack['exportedAt'], 'questions': entries}

    def change_question(self, changes):
        self.page.evaluate('''async changes=>{
          const t=db.transaction('questions','readwrite'),s=t.objectStore('questions'),r=s.get('TEST-PLUSH-001');
          r.onsuccess=()=>s.put({...r.result,...changes});
          await new Promise((ok,no)=>{t.oncomplete=ok;t.onerror=()=>no(t.error);});
        }''', changes)

    def test_stale_baselines_and_changes_after_preview_are_rejected(self):
        self.seed()
        update = self.update_file(self.pack())
        update['questions'][0]['explanation'] += ' 修正案'
        for changes, expected in [({'why': '別端末で変更済み'}, '照合値'), ({'revision': 2}, '改訂番号')]:
            with self.subTest(changes=changes):
                before = self.snapshot()
                message = self.page.evaluate('''async ({update,changes})=>{
                  const qs=await readAll('questions');Object.assign(qs.find(q=>q.id==='TEST-PLUSH-001'),changes);
                  try{await planQuestionUpdate(validateQuestionUpdateFile(update),qs);return '';}catch(e){return e.message;}
                }''', {'update': update, 'changes': changes})
                self.assertIn(expected, message)
                self.assertEqual(self.snapshot(), before)
        self.page.evaluate('''async update=>{window.oldPlan=await planQuestionUpdate(validateQuestionUpdateFile(update),await readAll('questions'));}''', update)
        self.change_question({'why': '保存直前の別タブ更新'})
        before = self.snapshot()
        message = self.page.evaluate('''async()=>{try{await writeQuestionUpdatePlan(oldPlan);return '';}catch(e){return e.message;}}''')
        self.assertIn('保存直前', message)
        self.assertEqual(self.snapshot(), before)

    def test_roundtrip_writes_keep_history_coins_awards_feedback_and_mastery_rules(self):
        for edits, reset in [({'explanation': '新しい架空解説', 'difficulty': 'advanced', 'tag': 'person'}, False),
                             ({'question': '意味を変更した架空の設問'}, True),
                             ({'options': [{'id': '1', 'text': '変更した選択肢'}, {'id': '2', 'text': '架空の乙'}, {'id': '3', 'text': '架空の丙'}]}, True),
                             ({'correctAnswers': ['2']}, True)]:
            with self.subTest(edits=edits):
                self.install(mastered=True)
                self.seed()
                before = self.snapshot()
                update = self.update_file(self.pack())
                update['questions'][0].update(edits)
                result = self.page.evaluate('''async update=>{
                  const plan=await planQuestionUpdate(validateQuestionUpdateFile(update),await readAll('questions'));
                  await writeQuestionUpdatePlan(plan);await loadImportedQuestions();await ensureEarnedCards();
                  const progress=await readAll('progress'),q=importedQuestions.find(q=>q.id==='TEST-PLUSH-001');
                  return {resets:plan.resetCount,revision:questionRevision(q),
                    active:['student','test'].map(who=>!!activeProgress(q,progress.find(p=>p.profile===who&&p.questionId===q.id))),
                    mastery:masteryStats('E01',new Map(progress.filter(p=>p.profile==='student').map(p=>[p.questionId,p]))).percentage};
                }''', update)
                self.assertEqual(result, {'resets': int(reset), 'revision': 2 if reset else 1,
                                          'active': [not reset, not reset], 'mastery': 0 if reset else 100})
                after = self.snapshot()
                for name in before:
                    if name not in ['questions', 'sessions']:
                        self.assertEqual(after[name], before[name], name)
                if reset:
                    self.assertFalse(any(s['questionId'] == 'TEST-PLUSH-001' for s in after['sessions']))
                else:
                    self.assertEqual(after['sessions'], before['sessions'])

    def test_actual_update_ui_refreshes_comparison_without_resolving_reports(self):
        self.seed(); self.admin()
        update = self.update_file(self.pack())
        update['questions'][0]['explanation'] = '画面から反映する架空解説'
        before = self.snapshot()
        self.page.locator('#toggle-question-update').click()
        self.page.locator('#question-update-file').set_input_files({
            'name': 'synthetic-update.json', 'mimeType': 'application/json',
            'buffer': json.dumps(update).encode()})
        self.page.wait_for_function('pendingQuestionUpdate!==null&&!updatingQuestions')
        self.page.locator('#question-update-apply').click()
        self.page.wait_for_function('!updatingQuestions&&document.querySelector("#question-update-preview").textContent.startsWith("更新完了")')
        self.assertIn('要確認', self.page.locator('#feedback-list').inner_text())
        self.page.get_by_text('報告時と現在の問題を比較').click()
        self.assertIn('画面から反映する架空解説', self.page.locator('#feedback-list').inner_text())
        after = self.snapshot()
        for name in before:
            if name != 'questions':
                self.assertEqual(after[name], before[name], name)
        self.assertEqual(after['questionFeedback'][0]['status'], 'unreviewed')

    def test_revision_only_difference_is_visible_in_json_and_comparison(self):
        self.seed(); self.change_question({'revision': 2})
        pack = self.pack(); entry = pack['questions'][0]; report = entry['reports'][0]
        self.assertEqual((entry['currentRevision'], report['questionRevision']), (2, 1))
        self.assertTrue(report['versionMismatch'])
        self.assertEqual(report['changedFields'], [])
        self.admin(); self.page.get_by_text('報告時と現在の問題を比較').click()
        self.assertIn('改訂番号', self.page.locator('#feedback-list').inner_text())
        self.assertEqual(self.page.evaluate('(async()=>(await readAll("questionFeedback"))[0].status)()'), 'unreviewed')

    def test_matching_builtin_report_still_shows_app_change_advice(self):
        self.page.evaluate('''async()=>{
          const q=SAMPLE_QUESTIONS[0],at='2020-01-01T00:00:00.000Z';
          await importFeedbackRecords([{reportId:crypto.randomUUID(),questionId:q.id,questionRevision:1,
            questionHash:await sha256Text(questionFingerprintSource(q)),questionSnapshot:{...exportableQuestion(q),deleted:false},
            reporterRole:'admin',category:'fact',comment:'架空の確認',createdAt:at}]);
        }''')
        self.admin()
        self.assertIn('現在の問題と一致', self.page.locator('#feedback-list').inner_text())
        self.assertIn('アプリ本体の修正が必要', self.page.locator('#feedback-list').inner_text())

    def test_stale_manual_fix_pending_cannot_overwrite_another_tab(self):
        self.seed(); self.change_question({'why': '架空の解説変更'}); self.admin()
        button = self.page.get_by_role('button', name='修正確認待ちにする（保護者確認）').element_handle()
        old = self.page.evaluate('(async()=>(await readAll("questionFeedback"))[0])()')
        second = self.context.new_page(); second.goto(self.url); self.ready(second)
        second.evaluate('navigate("admin")')
        second.evaluate('r=>changeFeedbackStatus(r.reportId,"reviewing",r)', old)
        button.evaluate('el=>el.click()')
        self.page.wait_for_function('document.querySelector("#notice").textContent.includes("別タブ")')
        self.assertEqual(self.page.evaluate('(async()=>(await readAll("questionFeedback"))[0].status)()'), 'reviewing')

    def test_actual_file_size_boundary_includes_final_newline(self):
        self.seed(); self.admin()
        # 正常な形式の大きいパックをメモリ上で合成。本文1件のサイズから件数を求め、
        # 各コメント500文字以内で実ファイルをちょうど8MiBに調整する。
        self.page.evaluate('''async()=>{
          const pack=await buildImprovementRequest(await readAll('questionFeedback'),await readAll('questions'));
          const template={...pack.questions[0].reports[0],comment:''},rows=pack.questions[0].reports;
          const bytes=()=>new Blob([JSON.stringify(pack,null,2)+'\\n']).size;
          const one=bytes();rows.push({...template});const stride=bytes()-one;
          const count=Math.floor((8*1024*1024-one)/stride)+1;
          pack.questions[0].reports=Array.from({length:count},(_,i)=>({...template,reportId:'00000000-0000-4000-8000-'+i.toString(16).padStart(12,'0')}));
          pack.reportCount=count;
          let remaining=8*1024*1024-bytes();
          if(remaining<0)throw new Error('境界データが上限超過');
          for(const r of pack.questions[0].reports){const n=Math.min(500,remaining);r.comment='x'.repeat(n);remaining-=n;if(!remaining)break;}
          if(remaining||bytes()!==8*1024*1024)throw new Error('境界データのサイズ不正');
          window.boundaryPack=pack;buildImprovementRequest=async()=>structuredClone(boundaryPack);
        }''')
        downloads = []
        self.page.on('download', lambda d: downloads.append(d))
        before = self.snapshot()
        with self.page.expect_download() as event:
            self.page.locator('#feedback-improvement-pending').click()
        self.assertEqual(Path(event.value.path()).stat().st_size, 8 * 1024 * 1024)
        self.page.wait_for_function('!improvementExporting')
        self.page.evaluate('boundaryPack.questions[0].reports.at(-1).comment+="x"')
        self.page.locator('#feedback-improvement-pending').click()
        self.page.wait_for_function('!improvementExporting&&document.querySelector("#feedback-improvement-status").textContent.includes("8MiB")')
        self.assertEqual(len(downloads), 1, '8MiB+1バイトは書き出さない')
        self.assertEqual(self.snapshot(), before)

    def test_exactly_100_questions_keep_all_reports_and_sort_ids(self):
        self.seed(2)
        result = self.page.evaluate('''async()=>{
          const originals=await readAll('questionFeedback'),q=await readOne('questions','TEST-PLUSH-001'),questions=[],reports=[];
          for(let i=99;i>=0;i--){
            const current={...q,id:'TEST-GROUP-'+String(i).padStart(3,'0'),q:'架空の問題 '+i};questions.push(current);
            const hash=await sha256Text(questionFingerprintSource(current));
            for(const r of originals)reports.push({...r,reportId:crypto.randomUUID(),questionId:current.id,questionHash:hash,
              questionSnapshot:{...exportableQuestion(current),deleted:false}});
          }
          const pack=await buildImprovementRequest(reports,questions);
          return {count:pack.questionCount,reports:pack.reportCount,ids:pack.questions.map(q=>q.questionId),
            perQuestion:pack.questions.map(q=>q.reports.length)};
        }''')
        self.assertEqual((result['count'], result['reports']), (100, 200))
        self.assertEqual(result['ids'], sorted(result['ids']))
        self.assertEqual(result['perQuestion'], [2] * 100)

    def test_untrusted_comments_and_comparison_are_text_and_no_extra_data_leaks(self):
        report = self.seed()[0]
        hostile = '<img src=x onerror="window.improvementInjected=true">'
        self.page.evaluate('''async ({r,text})=>{
          await importFeedbackRecords([{...r,reportId:crypto.randomUUID(),comment:text}]);
        }''', {'r': report, 'text': hostile})
        self.change_question({'why': hostile, 'studentName': '含めてはいけない架空の名前'})
        self.admin()
        self.page.get_by_text('報告時と現在の問題を比較', exact=True).first.click()
        self.assertIn(hostile, self.page.locator('#feedback-list').inner_text())
        self.assertEqual(self.page.locator('#feedback-list img, #feedback-list svg').count(), 0)
        self.assertIsNone(self.page.evaluate('window.improvementInjected'))
        with self.page.expect_download() as event:
            self.page.locator('#feedback-improvement-pending').click()
        text = Path(event.value.path()).read_text()
        self.assertIn(hostile, json.loads(text)['questions'][0]['currentQuestion']['explanation'])
        self.assertNotIn('含めてはいけない架空の名前', text)
        self.assertEqual(set(json.loads(text)), {'improvementRequestFormat', 'formatVersion', 'exportedAt', 'questionCount', 'reportCount', 'questions'})

    def test_ten_earned_cards_decode_expand_and_survive_export_reload_and_profiles(self):
        self.install(mastered=True); self.seed()
        self.page.evaluate('''async()=>{
          await writeAwards(ERAS.map(([era])=>({key:'student:'+era,profile:'student',era,
            earnedAt:'2020-01-01T00:00:00.000Z',questionCountAtEarn:50})));
          await navigateHome('student');
        }''')
        before = self.snapshot()
        self.assertEqual(self.page.locator('#card-gallery button.trophy-open').count(), 10)
        self.assertEqual(self.page.locator('#card-total').inner_text(), '10 / 10枚')
        self.assertIn('理解度 100%', self.page.locator('#era-list .era').first.inner_text())
        self.assertIn('理解度 0%', self.page.locator('#era-list .era').nth(3).inner_text())
        for i in range(10):
            card = self.page.locator('#card-gallery button.trophy-open').nth(i)
            img = card.locator('img')
            img.evaluate('img=>img.decode()')
            self.assertEqual(img.get_attribute('src'), f'assets/cards/E{i+1:02d}.webp')
            self.assertGreater(img.evaluate('img=>img.naturalWidth'), 0)
            card.click()
            self.assertTrue(self.page.locator('#card-detail-dialog').is_visible())
            detail = self.page.locator('#card-detail-art-host img')
            detail.evaluate('img=>img.decode()')
            self.assertEqual(detail.get_attribute('src'), img.get_attribute('src'))
            self.page.locator('#card-detail-close').click()
        self.admin()
        with self.page.expect_download():
            self.page.locator('#feedback-improvement-pending').click()
        self.page.reload(); self.ready()
        self.page.evaluate('navigateHome("test")')
        self.page.wait_for_function('document.querySelector("#card-total").textContent==="1 / 10枚"')
        self.page.evaluate('navigateHome("student")')
        self.page.wait_for_function('document.querySelector("#card-total").textContent==="10 / 10枚"')
        self.assertEqual(self.snapshot(), before)

    def test_export_cancelled_on_navigation_during_hash(self):
        self.seed(); self.admin()
        self.page.evaluate('''()=>{
          const original=sha256Text;let first=true;
          sha256Text=async text=>{if(first){first=false;await new Promise(ok=>window.releaseExportHash=ok);}return original(text);};
        }''')
        downloads = []
        self.page.on('download', lambda d: downloads.append(d))
        self.page.locator('#feedback-improvement-pending').click()
        self.page.wait_for_function('typeof releaseExportHash==="function"')
        self.page.evaluate('navigateHome("test")')
        self.page.evaluate('releaseExportHash()')
        self.page.wait_for_function('!improvementExporting')
        self.assertEqual(downloads, [])

    def test_selection_fixed_at_click_and_export_uses_readonly_snapshot(self):
        reports = self.seed(2); self.admin()
        self.page.evaluate('''id=>{
          feedbackSelected.add(id);const original=readImprovementSource;
          readImprovementSource=async()=>{await new Promise(ok=>window.releaseExportRead=ok);return original();};
          window.exportTransactions=[];const transaction=db.transaction.bind(db);
          db.transaction=(names,mode,...rest)=>{exportTransactions.push({names:typeof names==='string'?[names]:[...names],mode});return transaction(names,mode,...rest);};
        }''', reports[0]['reportId'])
        with self.page.expect_download() as event:
            self.page.locator('#feedback-improvement-selected').click()
            self.page.wait_for_function('typeof releaseExportRead==="function"')
            self.page.evaluate('id=>{feedbackSelected.clear();feedbackSelected.add(id);releaseExportRead();}', reports[1]['reportId'])
        pack = json.loads(Path(event.value.path()).read_text())
        self.assertEqual([r['reportId'] for r in pack['questions'][0]['reports']], [reports[0]['reportId']])
        transactions = self.page.evaluate('exportTransactions')
        self.assertTrue(any(set(t['names']) == {'questionFeedback', 'questions'} and t['mode'] == 'readonly' for t in transactions))
        self.assertTrue(all(t['mode'] == 'readonly' for t in transactions))

if __name__ == "__main__":
    unittest.main()
