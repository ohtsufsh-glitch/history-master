"""Issue #21: 管理メニューの階層・状態保持・安全手順。架空データのみ使用。

実行・準備は question_editor_test.py と同じ。Safari実機確認の代替ではない。
"""
import json
from pathlib import Path
import unittest

import history_navigation_test as navigation


GROUPS = ['admin-questions-group', 'admin-backup-group', 'admin-other-group']
PANELS = ['import', 'manage', 'question-update', 'feedback', 'tag-map', 'backup', 'reset']


class AdminMenuHierarchyTest(unittest.TestCase):
    # TestCaseを継承せず、既存テストを重複実行・計上しない。
    setUpClass = classmethod(navigation.HistoryNavigationTest.setUpClass.__func__)
    tearDownClass = classmethod(navigation.HistoryNavigationTest.tearDownClass.__func__)
    tearDown = navigation.HistoryNavigationTest.tearDown
    ready = navigation.HistoryNavigationTest.ready
    install = navigation.HistoryNavigationTest.install
    snapshot = navigation.HistoryNavigationTest.snapshot
    screen = navigation.HistoryNavigationTest.screen

    def setUp(self):
        self.context = self.browser.new_context(viewport={'width': 390, 'height': 844}, has_touch=True)
        self.page = self.context.new_page()
        self.page.set_default_timeout(7000)
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.dialogs = []
        self.cancel_dialog = False
        self.prompt_text = '初期化'
        self.page.on('dialog', self.on_dialog)
        self.page.goto(self.url)
        self.ready()
        self.install()
        self.page.locator('#open-admin').click()
        self.screen('admin')

    def on_dialog(self, dialog):
        self.dialogs.append((dialog.type, dialog.message))
        if self.cancel_dialog:
            dialog.dismiss()
        elif dialog.type == 'prompt':
            dialog.accept(self.prompt_text)
        else:
            dialog.accept()

    def group(self, group, opened=True):
        element = self.page.locator('#' + group)
        if element.evaluate('el=>el.open') != opened:
            element.locator(':scope > summary').click()
        self.assertEqual(element.evaluate('el=>el.open'), opened)

    def cycle(self, group):
        self.group(group, False)
        self.group(group)

    def panel(self, name):
        group = GROUPS[1] if name == 'backup' else GROUPS[2] if name == 'reset' else GROUPS[0]
        self.group(group)
        if self.page.locator('#' + name + '-panel').evaluate('el=>el.classList.contains("hidden")'):
            self.page.locator('#toggle-' + name).click()
        self.assertTrue(self.page.locator('#' + name + '-panel').is_visible())

    def upload(self, name, data, filename=None):
        self.panel(name)
        filename = filename or 'synthetic-' + name + '.json'
        self.page.locator('#' + name + '-file').set_input_files({
            'name': filename, 'mimeType': 'application/json',
            'buffer': json.dumps(data, ensure_ascii=False).encode()})
        self.page.wait_for_function(
            'id=>document.getElementById(id).textContent.startsWith("検査OK")',
            arg=name + '-preview')
        return self.page.locator('#' + name + '-preview').inner_text()

    def import_data(self):
        return {'schemaVersion': 1, 'questions': [{
            'id': 'TEST-ADMIN-NEW', 'eraId': 'E01', 'question': '独自の管理UI確認用文章です。',
            'type': 'single', 'options': [{'id': 'A', 'text': '架空の赤'}, {'id': 'B', 'text': '架空の青'}],
            'correctAnswers': ['A'], 'explanation': '公開可能な独自の検証文です。',
            'difficulty': 'basic', 'tag': 'culture'}]}

    def backup(self):
        return self.page.evaluate('async()=>({backupFormat:BACKUP_FORMAT,backupVersion:BACKUP_VERSION,data:await snapshotAllStores()})')

    def export_master(self):
        self.panel('question-update')
        with self.page.expect_download() as event:
            self.page.locator('#question-export').click()
        return json.loads(Path(event.value.path()).read_text())

    def editor(self):
        self.panel('manage')
        self.page.locator('#manage-sort').select_option('accuracy-desc')
        self.page.locator('#manage-era').select_option('E01')
        self.page.locator('#manage-search').fill('TEST-PLUSH-001')
        self.page.locator('#manage-list').get_by_role('button', name='修正する', exact=True).click()
        self.page.get_by_label('問題文', exact=True).fill('保存前の入力\n続きも保持')

    def test_three_groups_and_function_order(self):
        self.assertEqual(self.page.locator('#admin > .admin-group').count(), 3)
        self.assertEqual(self.page.locator('#admin > .admin-group > summary h3').evaluate_all('els=>els.map(el=>el.firstChild.textContent)'),
                         ['📚 問題を管理する', '💾 バックアップ・復元', '⚙️ その他の管理'])
        self.assertEqual(self.page.locator('#admin-questions-group .import-toggle').evaluate_all('els=>els.map(el=>el.id)'),
                         ['toggle-import', 'toggle-manage', 'toggle-question-update', 'toggle-feedback', 'toggle-tag-map'])
        self.assertEqual(self.page.locator('#admin-other-group > .admin-group-content').evaluate(
            'el=>[...el.children].map(el=>el.id)'), ['card-preview-panel', 'toggle-reset', 'reset-panel'])

    def test_test_mode_section_always_visible(self):
        for group in GROUPS:
            self.group(group, False)
        self.assertTrue(self.page.locator('.admin-test-area').is_visible())
        self.assertTrue(self.page.locator('#admin-start-test').is_visible())
        self.assertEqual(self.page.locator('.admin-test-area').evaluate('el=>el.closest("details")'), None)

    def test_questions_initially_open(self):
        self.assertTrue(self.page.locator('#' + GROUPS[0]).evaluate('el=>el.open'))

    def test_backup_and_other_initially_closed(self):
        for group in GROUPS[1:]:
            self.assertFalse(self.page.locator('#' + group).evaluate('el=>el.open'))

    def test_all_child_panels_initially_closed(self):
        for name in PANELS:
            self.assertEqual(self.page.locator('#toggle-' + name).get_attribute('aria-expanded'), 'false')
            self.assertTrue(self.page.locator('#' + name + '-panel').is_hidden())
        self.assertFalse(self.page.locator('#card-preview-panel').evaluate('el=>el.open'))

    def test_multiple_groups_expand_independently(self):
        for group in GROUPS:
            self.group(group)
        for group in GROUPS:
            self.assertTrue(self.page.locator('#' + group).evaluate('el=>el.open'))
        self.group(GROUPS[1], False)
        for group in [GROUPS[0], GROUPS[2]]:
            self.assertTrue(self.page.locator('#' + group).evaluate('el=>el.open'))

    def test_editor_input_search_sort_and_dom_identity_survive_group_toggle(self):
        self.editor()
        before = self.snapshot()
        self.page.locator('.edit-form').evaluate('el=>window.originalEditor=el')
        self.cycle(GROUPS[0])
        self.assertEqual(self.page.get_by_label('問題文', exact=True).input_value(), '保存前の入力\n続きも保持')
        self.assertEqual(self.page.locator('#manage-search').input_value(), 'TEST-PLUSH-001')
        self.assertEqual(self.page.locator('#manage-sort').input_value(), 'accuracy-desc')
        self.assertEqual(self.page.locator('#manage-era').input_value(), 'E01')
        self.assertTrue(self.page.locator('.edit-form').evaluate('el=>el===originalEditor'))
        self.assertEqual(self.snapshot(), before)

    def test_import_file_and_preview_survive_group_toggle(self):
        before = self.snapshot()
        text = self.upload('import', self.import_data())
        self.page.evaluate('window.originalFile=document.querySelector("#import-file").files[0]')
        self.cycle(GROUPS[0])
        self.assertEqual(self.page.locator('#import-preview').inner_text(), text)
        self.assertTrue(self.page.evaluate('document.querySelector("#import-file").files[0]===originalFile'))
        self.assertTrue(self.page.locator('#import-apply').is_visible())
        self.assertEqual(self.page.evaluate('pendingImport.length'), 1)
        self.assertEqual(self.snapshot(), before)

    def test_master_update_file_diff_and_plan_survive_group_toggle(self):
        before = self.snapshot()
        master = self.export_master()
        master['questions'][0]['explanation'] = '架空の解説変更のプレビュー'
        text = self.upload('question-update', master)
        self.page.locator('#question-update-diffs summary').click()
        diff = self.page.locator('#question-update-diffs').inner_text()
        self.cycle(GROUPS[0])
        self.assertEqual(self.page.locator('#question-update-preview').inner_text(), text)
        self.assertEqual(self.page.locator('#question-update-diffs').inner_text(), diff)
        self.assertIn('架空の解説変更', diff)
        self.assertEqual(self.page.locator('#question-update-file').evaluate('el=>el.files[0].name'), 'synthetic-question-update.json')
        self.assertTrue(self.page.locator('#question-update-apply').is_visible())
        self.assertEqual(self.snapshot(), before)

    def test_tag_map_preview_survives_group_toggle(self):
        question_id = self.page.evaluate('importedQuestions[0].id')
        before = self.snapshot()
        self.panel('tag-map')
        self.page.locator('#tag-map-file').set_input_files({
            'name': 'synthetic-tags.json', 'mimeType': 'application/json',
            'buffer': json.dumps({'tagMapVersion': 1, 'assignments': [{'id': question_id, 'tag': 'society'}]}).encode()})
        self.page.wait_for_function('pendingTagMap!==null')
        text = self.page.locator('#tag-map-preview').inner_text()
        self.cycle(GROUPS[0])
        self.assertEqual(self.page.locator('#tag-map-preview').inner_text(), text)
        self.assertEqual(self.page.locator('#tag-map-file').evaluate('el=>el.files[0].name'), 'synthetic-tags.json')
        self.assertTrue(self.page.locator('#tag-map-apply').is_visible())
        self.assertEqual(self.snapshot(), before)

    def test_backup_file_and_inspection_survive_group_toggle(self):
        before = self.snapshot()
        text = self.upload('backup', self.backup())
        pending = self.page.evaluate('pendingRestore')
        self.cycle(GROUPS[1])
        self.assertEqual(self.page.locator('#backup-preview').inner_text(), text)
        self.assertEqual(self.page.evaluate('pendingRestore'), pending)
        self.assertEqual(self.page.locator('#backup-file').evaluate('el=>el.files[0].name'), 'synthetic-backup.json')
        self.assertTrue(self.page.locator('#backup-restore').is_visible())
        self.assertEqual(self.snapshot(), before)

    def test_reset_checks_ack_and_preview_survive_group_toggle(self):
        before = self.snapshot()
        self.panel('reset')
        self.page.locator('#reset-test').check()
        self.page.locator('#reset-ack').check()
        self.page.wait_for_function('!document.querySelector("#reset-apply").disabled')
        text = self.page.locator('#reset-preview').inner_text()
        self.cycle(GROUPS[2])
        self.assertTrue(self.page.locator('#reset-test').is_checked())
        self.assertTrue(self.page.locator('#reset-ack').is_checked())
        self.assertTrue(self.page.locator('#reset-apply').is_enabled())
        self.assertEqual(self.page.locator('#reset-preview').inner_text(), text)
        self.assertEqual(self.snapshot(), before)

    def test_all_existing_functions_remain_accessible_and_children_toggle(self):
        for name in PANELS:
            self.panel(name)
            button = self.page.locator('#toggle-' + name)
            self.assertEqual(button.get_attribute('aria-expanded'), 'true')
            self.assertEqual(button.get_attribute('aria-controls'), name + '-panel')
            self.cycle(GROUPS[1] if name == 'backup' else GROUPS[2] if name == 'reset' else GROUPS[0])
            self.assertTrue(self.page.locator('#' + name + '-panel').is_visible())
            button.click()
            self.assertEqual(button.get_attribute('aria-expanded'), 'false')
            self.assertTrue(self.page.locator('#' + name + '-panel').is_hidden())
        self.page.locator('#card-preview-panel > summary').click()
        self.page.wait_for_function('document.querySelectorAll("#admin-card-preview .trophy").length===10')
        self.assertEqual(self.page.locator('#admin-card-preview .trophy').count(), 10)

    def test_backup_restore_still_requires_confirmation_and_cancel_is_safe(self):
        before = self.snapshot()
        self.upload('backup', self.backup())
        self.cycle(GROUPS[1])
        self.assertIn('すべて置き換えます', self.page.locator('#backup-panel .backup-warn').inner_text())
        self.cancel_dialog = True
        self.page.locator('#backup-restore').click()
        self.assertEqual(len(self.dialogs), 1)
        self.assertIn('復元を実行しますか', self.dialogs[0][1])
        self.assertEqual(self.snapshot(), before)
        self.assertIsNotNone(self.page.evaluate('pendingRestore'))

    def test_selected_reset_requires_checks_ack_and_dialog(self):
        before = self.snapshot()
        self.panel('reset')
        self.assertTrue(self.page.locator('#reset-apply').is_disabled())
        self.page.locator('#reset-test').check()
        self.assertTrue(self.page.locator('#reset-apply').is_disabled())
        self.page.locator('#reset-ack').check()
        self.page.wait_for_function('!document.querySelector("#reset-apply").disabled')
        self.cycle(GROUPS[2])
        self.cancel_dialog = True
        with self.page.expect_event('dialog'):
            self.page.locator('#reset-apply').click()
        self.page.wait_for_function('!resetting')
        self.assertEqual(len(self.dialogs), 1)
        self.assertIn('初期化します', self.dialogs[0][1])
        self.assertEqual(self.snapshot(), before)

    def test_full_reset_keeps_warning_confirm_and_typed_confirmation(self):
        before = self.snapshot()
        self.panel('reset')
        self.assertIn('取り消し不可', self.page.locator('.reset-danger').inner_text())
        self.prompt_text = '別の文字'
        self.cycle(GROUPS[2])
        with self.page.expect_event('dialog', predicate=lambda dialog: dialog.type == 'prompt'):
            self.page.locator('#reset-all').click()
        self.page.wait_for_function('!resetting')
        self.assertEqual([x[0] for x in self.dialogs], ['confirm', 'prompt'])
        self.assertIn('永久に消去', self.dialogs[0][1])
        self.assertIn('初期化', self.dialogs[1][1])
        self.assertEqual(self.snapshot(), before)

    def test_card_preview_does_not_modify_learning_data(self):
        before = self.snapshot()
        self.group(GROUPS[2])
        self.page.locator('#card-preview-panel > summary').click()
        self.page.wait_for_function('document.querySelectorAll("#admin-card-preview .trophy").length===10')
        self.cycle(GROUPS[2])
        self.assertTrue(self.page.locator('#card-preview-panel').evaluate('el=>el.open'))
        self.assertEqual(self.snapshot(), before)

    def test_menu_toggles_leave_all_fourteen_stores_unchanged(self):
        before = self.snapshot()
        self.assertEqual(len(before), 16)
        for name in PANELS:
            self.panel(name)
        for _ in range(2):
            for group in GROUPS:
                self.cycle(group)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.page.evaluate('[DB_VERSION,BACKUP_VERSION]'), [9, 9])

    def test_menu_toggles_do_not_add_browser_history(self):
        before = self.page.evaluate('({length:history.length,state:history.state,url:location.href})')
        for name in PANELS:
            self.panel(name)
        for group in GROUPS:
            self.cycle(group)
        self.assertEqual(self.page.evaluate('({length:history.length,state:history.state,url:location.href})'), before)

    def test_iphone_ipad_widths_fit_open_panels_files_and_warnings(self):
        self.upload('import', self.import_data(), 'synthetic-' + 'long-name-' * 18 + '.json')
        self.upload('backup', self.backup())
        for name in PANELS:
            self.panel(name)
        self.page.locator('#card-preview-panel > summary').click()
        for width, height in [(375, 812), (390, 844), (768, 1024), (1024, 768)]:
            with self.subTest(width=width):
                self.page.set_viewport_size({'width': width, 'height': height})
                self.assertEqual(self.page.evaluate('''()=>{
                  const els=[...document.querySelectorAll('#admin button,#admin summary,#admin input,#admin select,#admin .backup-warn,#admin h3,#admin h4')];
                  return els.filter(el=>el.getClientRects().length).filter(el=>{
                    const r=el.getBoundingClientRect();return r.left<0||r.right>innerWidth+1;
                  }).map(el=>el.id||el.textContent);
                }'''), [])
                self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'), width)

    def test_menu_tap_targets_are_at_least_44_pixels(self):
        for group in GROUPS:
            self.group(group)
        targets = self.page.locator('#admin > .admin-group > summary, #admin .import-toggle, #card-preview-panel > summary')
        self.assertEqual(targets.count(), 11)
        for target in targets.all():
            bounds = target.bounding_box()
            self.assertGreaterEqual(bounds['height'], 44)
            self.assertGreaterEqual(bounds['width'], 44)

    def test_keyboard_native_expansion_aria_and_focus(self):
        # summaryのネイティブ開閉状態はブラウザのアクセシビリティツリーに出る。
        # aria-expandedの手動複製を加えず、読み上げに使われる実際の状態を検証。
        session = self.context.new_cdp_session(self.page)

        def expanded():
            nodes = session.send('Accessibility.getFullAXTree')['nodes']
            summary_node = next(node for node in nodes
                                if node.get('role', {}).get('value') == 'DisclosureTriangle'
                                and node.get('name', {}).get('value', '').startswith('💾 バックアップ・復元'))
            return next(prop['value']['value'] for prop in summary_node['properties'] if prop['name'] == 'expanded')

        summary = self.page.locator('#admin-backup-group > summary')
        self.assertFalse(expanded())
        summary.focus()
        summary.press('Enter')
        self.assertTrue(self.page.locator('#' + GROUPS[1]).evaluate('el=>el.open'))
        self.assertTrue(expanded())
        self.assertTrue(summary.evaluate('el=>el===document.activeElement'))
        summary.press('Tab')
        child = self.page.locator('#toggle-backup')
        self.assertTrue(child.evaluate('el=>el===document.activeElement'))
        child.press('Enter')
        self.assertEqual(child.get_attribute('aria-expanded'), 'true')
        self.assertIn('[expanded]', child.aria_snapshot())
        summary.focus()
        summary.press('Space')
        self.assertFalse(self.page.locator('#' + GROUPS[1]).evaluate('el=>el.open'))
        self.assertFalse(expanded())
        self.assertTrue(summary.evaluate('el=>el===document.activeElement'))
        session.detach()

    def test_test_mode_start_and_return_to_student_home(self):
        before = self.snapshot()
        for group in GROUPS:
            self.group(group, False)
        self.page.locator('#admin-start-test').click()
        self.screen('home')
        self.assertEqual(self.page.evaluate('profile'), 'test')
        self.page.locator('#test-return-admin').click()
        self.screen('admin')
        self.page.locator('#admin-back').click()
        self.screen('home')
        self.assertEqual(self.page.evaluate('profile'), 'student')
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(len(self.dialogs), 1)

    def test_history_return_preserves_editor_file_preview_and_menu_state(self):
        self.editor()
        text = self.upload('import', self.import_data())
        self.group(GROUPS[1])
        self.page.go_back()
        self.screen('home')
        self.page.go_forward()
        self.screen('admin')
        self.assertEqual(self.page.get_by_label('問題文', exact=True).input_value(), '保存前の入力\n続きも保持')
        self.assertEqual(self.page.locator('#import-preview').inner_text(), text)
        self.assertEqual(self.page.locator('#import-file').evaluate('el=>el.files.length'), 1)
        self.assertTrue(self.page.locator('#' + GROUPS[1]).evaluate('el=>el.open'))

    def test_close_group_during_import_does_not_duplicate_save(self):
        self.upload('import', self.import_data())
        self.page.evaluate('''()=>{
          const original=saveNewQuestions;
          window.saveCalls=0;
          saveNewQuestions=async(...args)=>{
            saveCalls++;
            await new Promise(resolve=>window.releaseSave=resolve);
            return original(...args);
          };
        }''')
        self.page.locator('#import-apply').click()
        self.page.wait_for_function('importing&&typeof releaseSave==="function"')
        self.cycle(GROUPS[0])
        self.assertTrue(self.page.locator('#import-apply').is_disabled())
        self.assertEqual(self.page.evaluate('saveCalls'), 1)
        self.page.evaluate('releaseSave()')
        self.page.wait_for_function('!importing')
        self.assertEqual(self.page.evaluate('saveCalls'), 1)
        self.assertIsNotNone(self.page.evaluate('readOne("questions","TEST-ADMIN-NEW")'))

    def test_close_group_during_restore_keeps_single_execution(self):
        before = self.snapshot()
        self.upload('backup', self.backup())
        self.page.evaluate('''()=>{
          const original=replaceAllStores;
          window.restoreCalls=0;
          replaceAllStores=async(...args)=>{
            restoreCalls++;
            await new Promise(resolve=>window.releaseRestore=resolve);
            return original(...args);
          };
        }''')
        self.page.locator('#backup-restore').click()
        self.page.wait_for_function('backingUp&&typeof releaseRestore==="function"')
        self.cycle(GROUPS[1])
        self.assertTrue(self.page.locator('#backup-restore').is_disabled())
        self.assertEqual(self.page.evaluate('restoreCalls'), 1)
        self.assertEqual(len(self.dialogs), 1)
        self.page.evaluate('releaseRestore()')
        self.page.wait_for_function('!backingUp&&pendingRestore===null')
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.page.evaluate('restoreCalls'), 1)

    def test_close_group_during_reset_keeps_single_execution(self):
        self.panel('reset')
        self.page.locator('#reset-test').check()
        self.page.locator('#reset-ack').check()
        self.page.wait_for_function('!document.querySelector("#reset-apply").disabled')
        self.page.evaluate('''()=>{
          const original=performReset;
          window.resetCalls=0;
          performReset=async(...args)=>{
            resetCalls++;
            await new Promise(resolve=>window.releaseReset=resolve);
            return original(...args);
          };
        }''')
        self.page.locator('#reset-apply').click()
        self.page.wait_for_function('resetting&&typeof releaseReset==="function"')
        self.cycle(GROUPS[2])
        self.assertTrue(self.page.locator('#reset-apply').is_disabled())
        self.assertTrue(self.page.locator('#reset-all').is_disabled())
        self.assertEqual(self.page.evaluate('resetCalls'), 1)
        self.assertEqual(len(self.dialogs), 1)
        self.page.evaluate('releaseReset()')
        self.page.wait_for_function('!resetting&&!backingUp')
        self.assertEqual(self.page.evaluate('resetCalls'), 1)


if __name__ == '__main__':
    unittest.main()
