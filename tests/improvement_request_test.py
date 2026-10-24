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
                         self.page.evaluate('importedQuestions[0].q'))
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
                         [8,8,15])

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


if __name__ == "__main__":
    unittest.main()
