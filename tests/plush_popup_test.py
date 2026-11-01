"""Issue #15。localhost・一時Chromium・公開可能な架空データだけで検証する。

実行方法・Playwrightの準備はquestion_editor_test.pyと同じ。
Safari実機のbfcache・VoiceOver・OSジェスチャーは別途確認する。
"""

import unittest

import arcade_board_test as board_test
import plush_test
import secret_plush_test as secret_test


class PlushPopupTest(unittest.TestCase):
    # ライフサイクルのみ再利用し、既存テストは継承・変更しない。
    setUpClass = classmethod(board_test.ArcadeBoardTest.setUpClass.__func__)
    tearDownClass = classmethod(board_test.ArcadeBoardTest.tearDownClass.__func__)
    tearDown = board_test.ArcadeBoardTest.tearDown
    on_dialog = board_test.ArcadeBoardTest.on_dialog
    snapshot = board_test.ArcadeBoardTest.snapshot

    def setUp(self):
        board_test.ArcadeBoardTest.setUp(self)
        self.install()

    def ready(self):
        board_test.ArcadeBoardTest.ready(self)
        self.page.evaluate(secret_test.HELPERS)

    def install(self, student=('shiba', 'shiba', 'secret_koryun', 'secret_koryun'),
                test=('shiba', 'secret_yuniko'), who='student'):
        self.page.evaluate("""async ({student,test,who,slots})=>{
          const data=secretFixture(student,'student'),other=secretFixture(test,'test');
          for(const name of ['arcadePlays','arcadePrizes','coinSpends'])data[name].push(...other[name]);
          data.arcadeBoards=['student','test'].map(profile=>({profile,slots:[...slots]}));
          await plushInstall(data);await navigate('arcade',who);
        }""", {'student': list(student), 'test': list(test), 'who': who, 'slots': secret_test.SLOTS})

    def card(self, prize='shiba'):
        return self.page.locator(f'.plush-item[data-prize-id="{prize}"]')

    def open(self, prize='shiba'):
        self.card(prize).click()
        self.page.wait_for_function("document.querySelector('#plush-detail-dialog').open")

    def close(self, method='button'):
        if method == 'button':
            self.page.get_by_role('button', name='× 閉じる', exact=True).click()
        elif method == 'outside':
            self.page.touchscreen.tap(3, 3)
        else:
            self.page.keyboard.press('Escape')
        self.assert_cleared()

    def assert_cleared(self):
        self.page.wait_for_function("!document.querySelector('#plush-detail-dialog').open")
        self.assertIsNone(self.page.locator('#plush-detail-image').get_attribute('src'))
        self.assertEqual(self.page.locator('#plush-detail-image').get_attribute('alt'), '')
        self.assertEqual(self.page.locator('#plush-detail-title').text_content(), '')
        self.assertEqual(self.page.locator('#plush-detail-count').text_content(), '')
        self.assertFalse(self.page.evaluate("document.body.classList.contains('plush-modal-open')"))

    def assert_prize(self, prize, name, amount):
        self.assertEqual(self.page.locator('#plush-detail-image').get_attribute('src'), f'assets/plush/{prize}.webp')
        self.assertEqual(self.page.locator('#plush-detail-image').get_attribute('alt'), name)
        self.assertEqual(self.page.locator('#plush-detail-title').inner_text(), name)
        self.assertEqual(self.page.locator('#plush-detail-count').inner_text(), f'獲得数：{amount}体')
        self.assertTrue(self.page.get_by_role('dialog', name=name, exact=True).is_visible())
        self.page.wait_for_function("document.querySelector('#plush-detail-image').naturalWidth>0")

    def test_owned_normal_image_name_and_saved_count(self):
        self.open()
        self.assert_prize('shiba', 'しば犬', 2)

    def test_owned_secret_image_name_and_saved_count(self):
        self.open('secret_koryun')
        self.assert_prize('secret_koryun', 'こりゅん', 2)

    def test_all_twenty_normal_and_three_secrets_use_same_dialog(self):
        types = {**plush_test.TYPES, **secret_test.SECRETS}
        self.install(student=types)
        for prize, name in types.items():
            with self.subTest(prize=prize):
                self.open(prize)
                self.assert_prize(prize, name, 1)
                self.close()
        self.assertEqual(self.page.locator('#plush-detail-dialog').count(), 1)

    def test_unowned_normal_stays_gray_and_inoperable(self):
        item = self.page.locator('#arcade-collection-list .not-owned').first
        self.assertEqual(item.evaluate('el=>el.tagName'), 'DIV')
        self.assertEqual(item.evaluate('el=>el.tabIndex'), -1)
        self.assertIsNone(item.get_attribute('data-prize-id'))
        self.assertIn('grayscale(1)', item.locator('img').evaluate('el=>getComputedStyle(el).filter'))
        item.click()
        self.assert_cleared()

    def test_unowned_secrets_have_no_identity_or_operation_hooks(self):
        self.install(student=())
        items = self.page.locator('#arcade-secret-collection-list .plush-item')
        self.assertEqual(items.count(), 3)
        for item in items.all():
            self.assertEqual(item.locator('img').get_attribute('src'), secret_test.UNKNOWN)
            self.assertEqual(item.locator('img').get_attribute('alt'), '？？？')
            self.assertIsNone(item.get_attribute('aria-label'))
            self.assertIsNone(item.get_attribute('data-prize-id'))
            self.assertEqual(item.evaluate('el=>el.tabIndex'), -1)
            for prize, name in secret_test.SECRETS.items():
                self.assertNotIn(prize, item.evaluate('el=>el.outerHTML'))
                self.assertNotIn(name, item.evaluate('el=>el.outerHTML'))
            item.click()
            self.assert_cleared()

    def test_forged_or_stale_owned_card_cannot_reveal_unearned_secret(self):
        self.install(student=())
        self.page.evaluate("""async ()=>{
          const fake=plushCollectionItem('secret_koryun',1);
          $('arcade-secret-collection-list').append(fake);
          await openPlushDetail(fake);fake.remove();
        }""")
        self.assert_cleared()

    def test_close_button_restores_focus_and_clears_content(self):
        self.open()
        self.assertTrue(self.page.locator('#plush-detail-close').evaluate('el=>el===document.activeElement'))
        self.close()
        self.assertTrue(self.card().evaluate('el=>el===document.activeElement'))

    def test_backdrop_touch_closes_and_restores_focus(self):
        self.open()
        self.close('outside')
        self.assertTrue(self.card().evaluate('el=>el===document.activeElement'))

    def test_escape_and_keyboard_activation_and_focus_trap(self):
        card = self.card()
        self.assertEqual(card.get_attribute('aria-haspopup'), 'dialog')
        self.assertIn('しば犬を大きく見る', card.get_attribute('aria-label'))
        for key in ['Enter', 'Space']:
            card.focus()
            self.page.keyboard.press(key)
            self.page.wait_for_function("document.querySelector('#plush-detail-dialog').open")
            for tab in ['Tab', 'Shift+Tab']:
                self.page.keyboard.press(tab)
                self.assertTrue(self.page.locator('#plush-detail-close').evaluate('el=>el===document.activeElement'))
            self.close('escape')
            self.assertTrue(card.evaluate('el=>el===document.activeElement'))

    def test_image_padding_and_drag_from_inside_do_not_close(self):
        self.open()
        self.page.locator('#plush-detail-image').click()
        rect = self.page.locator('#plush-detail-dialog').bounding_box()
        self.page.mouse.click(rect['x'] + 4, rect['y'] + 4)
        self.assertTrue(self.page.locator('#plush-detail-dialog').evaluate('el=>el.open'))
        image = self.page.locator('#plush-detail-image').bounding_box()
        self.page.mouse.move(image['x'] + 20, image['y'] + 20)
        self.page.mouse.down()
        self.page.mouse.move(3, 3)
        self.page.mouse.up()
        self.assertTrue(self.page.locator('#plush-detail-dialog').evaluate('el=>el.open'))
        self.close('outside')

    def test_rerendered_opener_returns_focus_to_collection_heading(self):
        self.open('secret_koryun')
        self.page.evaluate('renderArcadeCollection()')
        self.close()
        self.assertTrue(self.page.locator('#arcade-collection-title').evaluate('el=>el===document.activeElement'))

    def test_student_test_switch_clears_identity_and_uses_own_counts(self):
        self.open('secret_koryun')
        self.page.evaluate("navigate('arcade','test')")
        self.assert_cleared()
        self.assertEqual(self.card('secret_koryun').count(), 0)
        self.open()
        self.assert_prize('shiba', 'しば犬', 1)
        self.close()
        self.open('secret_yuniko')
        self.assert_prize('secret_yuniko', 'ゆにこ', 1)
        self.page.evaluate("navigate('arcade','student')")
        self.assert_cleared()
        self.assertEqual(self.card('secret_yuniko').count(), 0)
        self.open('secret_koryun')
        self.assert_prize('secret_koryun', 'こりゅん', 2)

    def test_open_close_preserves_all_fourteen_stores_for_both_profiles(self):
        for who in ['student', 'test']:
            self.page.evaluate("who=>navigate('arcade',who)", who)
            before = self.snapshot()
            self.assertEqual(len(before), 16)
            for method in ['button', 'outside', 'escape']:
                for prize in ['shiba', 'secret_koryun' if who == 'student' else 'secret_yuniko']:
                    self.open(prize)
                    self.assertEqual(self.snapshot(), before)
                    self.close(method)
                    self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.page.evaluate('[DB_VERSION,BACKUP_VERSION,db.objectStoreNames.length]'), [9, 9, 16])

    def test_history_length_state_url_and_api_calls_are_unchanged(self):
        before = self.page.evaluate("({length:history.length,state:history.state,url:location.href})")
        self.page.evaluate("""()=>{
          window.historyCalls=[];
          for(const method of ['pushState','replaceState']) {
            const original=history[method].bind(history);
            history[method]=(...args)=>{historyCalls.push(method);return original(...args);};
          }
        }""")
        for method in ['button', 'outside', 'escape']:
            self.open()
            self.close(method)
        self.assertEqual(self.page.evaluate('historyCalls'), [])
        self.assertEqual(self.page.evaluate("({length:history.length,state:history.state,url:location.href})"), before)

    def test_browser_back_forward_and_navigation_leave_no_old_popup(self):
        self.open('secret_koryun')
        before = self.snapshot()
        self.page.go_back()
        self.page.wait_for_function("!$('home').classList.contains('hidden')")
        self.assert_cleared()
        self.page.go_forward()
        self.page.wait_for_function("!$('arcade').classList.contains('hidden')&&document.querySelector('#arcade-collection-list button')")
        self.assert_cleared()
        self.assertEqual(self.snapshot(), before)
        for screen in ['home', 'admin', 'quiz']:
            self.page.evaluate("navigate('arcade','student')")
            self.open()
            self.page.evaluate("screen=>navigate(screen,'student',screen==='quiz'?'E01':null)", screen)
            self.assert_cleared()

    def test_pagehide_pageshow_and_reload_do_not_restore_popup(self):
        self.open('secret_koryun')
        self.page.evaluate("window.dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}))")
        self.assert_cleared()
        self.page.evaluate("window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}))")
        self.page.wait_for_function("document.querySelector('#arcade-secret-collection-list button')")
        self.assert_cleared()
        self.open()
        before = self.snapshot()
        self.page.reload()
        self.ready()
        self.page.wait_for_function("document.querySelector('#arcade-collection-list button')")
        self.assert_cleared()
        self.assertEqual(self.snapshot(), before)

    def test_restore_replaces_collection_and_clears_popup(self):
        self.open('secret_koryun')
        self.page.evaluate("""async ()=>{
          pendingRestore=secretFixture(['bear'],'student');await applyRestore();
          await navigate('arcade','student');
        }""")
        self.assert_cleared()
        self.assertEqual(self.card('secret_koryun').count(), 0)
        self.open('bear')
        self.assert_prize('bear', 'くま', 1)

    def test_selected_and_full_reset_clear_old_popup_and_identity(self):
        for complete in [False, True]:
            self.install()
            self.open('secret_koryun')
            if complete:
                self.page.evaluate('applyFullReset()')
            else:
                self.page.evaluate("""async ()=>{
                  $('reset-student').checked=true;$('reset-ack').checked=true;
                  await applySelectedReset();
                }""")
            self.assert_cleared()
            self.page.evaluate("navigate('arcade','student')")
            self.assertEqual(self.card().count(), 0)
            self.assertEqual(self.card('secret_koryun').count(), 0)

    def test_delayed_open_is_cancelled_by_profile_navigation_and_restore(self):
        for action in ["await navigateHome('test')", 'pendingRestore=secretFixture();await applyRestore()']:
            self.install()
            self.page.evaluate("""()=>{
              const original=readAll;let hold=true,release;
              const gate=new Promise(resolve=>release=resolve);
              readAll=name=>{
                if(name==='arcadePrizes'&&hold){hold=false;return gate.then(()=>original(name));}
                return original(name);
              };
              window.releasePopup=()=>{readAll=original;release();};
              window.openingPopup=openPlushDetail(document.querySelector('#arcade-secret-collection-list button'));
            }""")
            self.page.evaluate('async ()=>{' + action + ';}')
            self.page.evaluate('async ()=>{releasePopup();await openingPopup;}')
            self.assert_cleared()

    def test_pending_aiming_resolving_and_manual_resume_block_popup(self):
        for status in ['aiming', 'resolving']:
            for waiting in [False, True]:
                self.install()
                self.page.evaluate("""async ({status,waiting})=>{
                  arcadePlay=await purchaseCranePlay(newArcadePlay(profile));
                  if(status==='resolving') {
                    arcadePlay.armX=50;
                    arcadePlay=await commitCraneOutcome(arcadePlay,chooseCraneOutcome(arcadePlay,()=>0));
                  }
                  arcadeResumeRequired=waiting;await renderArcade();
                }""", {'status': status, 'waiting': waiting})
                before = self.snapshot()
                self.card().click()
                self.assert_cleared()
                self.assertEqual(self.snapshot(), before)
                self.assertEqual(self.page.evaluate('arcadeResumeRequired'), waiting)

    def test_saved_pending_play_blocks_even_when_memory_is_stale(self):
        self.page.evaluate("""async ()=>{
          await purchaseCranePlay(newArcadePlay(profile));arcadePlay=null;
          await openPlushDetail(document.querySelector('#arcade-collection-list button'));
        }""")
        self.assert_cleared()

    def test_busy_result_backup_and_reset_block_popup(self):
        for flag in ['arcadeBusy', 'backingUp', 'resetting']:
            self.page.evaluate('async ()=>{' + flag + "=true;await openPlushDetail(document.querySelector('#arcade-collection-list button'));}")
            self.assert_cleared()
            self.page.evaluate('()=>{' + flag + '=false;}')
        self.open()

    def test_interrupted_secret_play_resumes_once_and_reveal_does_not_compete(self):
        self.page.evaluate("""async ()=>{
          arcadePlay=await purchaseCranePlay(newArcadePlay(profile));arcadePlay.armX=50;
          arcadePlay=await commitCraneOutcome(arcadePlay,chooseCraneOutcome(arcadePlay,()=>0));
          arcadeResumeRequired=true;await renderArcade();
        }""")
        before = self.snapshot()
        self.card().click()
        self.assert_cleared()
        # 公開待ちだけゲートで止める。保存・運搬・公開は実関数を通す。
        self.page.evaluate("""()=>{
          const timer=window.setTimeout;
          window.revealGates=[];
          window.setTimeout=(fn,ms,...args)=>{
            if(ms===SECRET_REVEAL_MS.hidden||ms===SECRET_REVEAL_MS.revealed)
              return revealGates.push(()=>fn(...args));
            return timer(fn,0,...args);
          };
          window.restorePopupTimer=()=>window.setTimeout=timer;
          window.resumingPopup=startCrane();
        }""")
        self.page.wait_for_function('revealGates.length===1')
        self.assertEqual(self.page.locator('#crane-secret-reveal img').get_attribute('src'), secret_test.UNKNOWN)
        self.page.evaluate("async ()=>{await openPlushDetail(document.querySelector('#arcade-secret-collection-list button'));}")
        self.assert_cleared()
        self.page.evaluate('revealGates.shift()()')
        self.page.wait_for_function('revealGates.length===1')
        self.assertEqual(self.page.locator('#crane-secret-reveal img').get_attribute('src'), 'assets/plush/secret_koryun.webp')
        self.card().click()
        self.assert_cleared()
        self.page.evaluate('async ()=>{revealGates.shift()();await resumingPopup;restorePopupTimer();}')
        after = self.snapshot()
        self.assertEqual(after['coinSpends'], before['coinSpends'])
        self.assertEqual(len(after['arcadePrizes']), len(before['arcadePrizes']) + 1)
        self.open('secret_koryun')
        self.assert_prize('secret_koryun', 'こりゅん', 3)
        self.close()
        self.assertEqual(self.snapshot(), after)

    def test_background_is_inert_scroll_locked_and_position_restored(self):
        self.card().scroll_into_view_if_needed()
        before = self.page.evaluate('scrollY')
        self.open()
        self.assertEqual(self.page.evaluate('getComputedStyle(document.body).position'), 'fixed')
        self.assertTrue(self.page.locator('#plush-detail-dialog').evaluate("el=>el.matches(':modal')"))
        self.page.mouse.wheel(0, 500)
        # 座標クリックの背面誤操作はネイティブmodalのbackdropへ送られる。
        self.assertEqual(self.page.evaluate('getComputedStyle(document.body).top'), f'-{before}px')
        self.close()
        self.assertAlmostEqual(self.page.evaluate('scrollY'), before, delta=1)

    def test_iphone_ipad_portrait_landscape_rotation_and_short_heights_fit(self):
        self.open('secret_koryun')
        for width, height in [(375, 667), (390, 844), (768, 1024), (1024, 768),
                              (844, 390), (667, 375), (568, 240), (320, 568)]:
            with self.subTest(width=width, height=height):
                self.page.set_viewport_size({'width': width, 'height': height})
                result = self.page.evaluate("""()=>{
                  const dialog=$('plush-detail-dialog'),image=$('plush-detail-image');
                  const d=dialog.getBoundingClientRect(),i=image.getBoundingClientRect();
                  const b=$('plush-detail-close').getBoundingClientRect();
                  return {inside:d.left>=0&&d.right<=innerWidth&&d.top>=0&&d.bottom<=innerHeight,
                    close:b.left>=0&&b.right<=innerWidth&&b.top>=0&&b.bottom<=innerHeight,
                    touch:b.height>=44&&b.width>=44,noOverflow:dialog.scrollWidth<=dialog.clientWidth,
                    image:i.width<=420&&i.width<=d.width,fit:getComputedStyle(image).objectFit};
                }""")
                self.assertEqual(result, {'inside': True, 'close': True, 'touch': True,
                                          'noOverflow': True, 'image': True, 'fit': 'contain'})
        self.page.locator('#plush-detail-dialog').evaluate('el=>el.scrollTop=el.scrollHeight')
        self.close()

    def test_reduced_motion_disables_popup_animation(self):
        self.page.emulate_media(reduced_motion='reduce')
        self.open()
        self.assertEqual(self.page.locator('.plush-detail-art').evaluate('el=>getComputedStyle(el).animationName'), 'none')
