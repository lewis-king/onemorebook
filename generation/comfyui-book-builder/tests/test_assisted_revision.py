"""Page revisions exercise persisted approvals and return state; all books are fixtures."""
import copy
import hashlib
import importlib
import json
import unittest
from unittest.mock import patch
import test_assisted_creator as helpers

store=helpers.store
engine=helpers.engine
revision=importlib.import_module('book_test_pack.assisted_revision')


class RevisionFixtures:
    setUp=helpers.AssistedCreatorTests.setUp
    restore_module=helpers.AssistedCreatorTests.restore_module
    state=helpers.AssistedCreatorTests.state
    add=helpers.AssistedCreatorTests.add
    approve=helpers.AssistedCreatorTests.approve
    plan=helpers.AssistedCreatorTests.plan
    prepare=helpers.AssistedCreatorTests.prepare
    png=helpers.AssistedCreatorTests.png

    def reviewing_second_page(self):
        state=self.prepare()
        while state['current_stage']!='pages/page-002.png':
            state=self.approve(self.png(state))
        return self.png(state)

    def revise(self,state,page='pages/page-001.png'):
        return revision.begin(state,page)


class PageRevisionTests(RevisionFixtures,unittest.TestCase):
    def test_new_ids_and_legacy_short_alias_round_trip_without_renaming(self):
        new=store.create({})
        self.assertRegex(new['id'],r'^book-\d{14}-[a-f0-9]{10}$')
        legacy=copy.deepcopy(new);legacy['id']=new['id'].replace('book-','book-assisted-',1)
        old_dir=store.root(legacy['id']);old_dir.mkdir()
        store.save(legacy)
        # A real new-format ID takes precedence if both exist.
        self.assertEqual(store.read(new['id'])['id'],new['id'])
        (store.root(new['id'])/'creator.json').unlink();store.root(new['id']).rmdir()
        self.assertEqual(store.read(new['id'])['id'],legacy['id'])
        self.assertEqual(store.root(new['id']),old_dir)
        self.assertEqual(store.listing()[0]['creator_url'],store.creator_url(new['id']))
        self.assertEqual(store.listing()[0]['id'],legacy['id'])
        legacy['revision']+=1;store.save(legacy)
        self.assertEqual(store.read(new['id'])['revision'],legacy['revision'])
        for bad in ['../book-20260911112233-abcdef1234','book-abc-def','book-20260911112233-abcdef1234/../../']:
            with self.assertRaises(ValueError):store.read(bad)

    def test_replace_and_return_preserves_later_stage_and_all_original_bytes(self):
        state=self.reviewing_second_page();original=copy.deepcopy(state)
        later=copy.deepcopy(store.stage(state))
        old=engine.selected(state,'pages/page-001.png')
        old_bytes=store.candidate_path(state,old).read_bytes()
        old_approval=(store.root(state['id'])/'creator/decisions'/f"{store.stage(state,'pages/page-001.png')['decision_id']}.json").read_bytes()
        state=self.revise(state)
        self.assertEqual(state['status'],'awaiting_review');self.assertIsNone(state['job'])
        self.assertEqual(store.stage(state,later['id']),later)
        state=self.png(state)
        self.assertEqual(state['page_revision']['original']['selected'],old['id'])
        state=store.read(state['id']) # restart/reopen retains the return point and candidate
        state=self.approve(state)
        self.assertEqual(state['current_stage'],later['id'])
        self.assertEqual(state['status'],original['status'])
        self.assertEqual(state['job'],original['job'])
        self.assertEqual(store.stage(state),later)
        self.assertNotIn('page_revision',state)
        self.assertNotEqual(engine.selected(state,'pages/page-001.png')['id'],old['id'])
        self.assertEqual(store.candidate_path(state,old).read_bytes(),old_bytes)
        self.assertEqual((store.root(state['id'])/'creator/decisions'/f"{store.stage(original,'pages/page-001.png')['decision_id']}.json").read_bytes(),old_approval)
        engine.approved(state,'pages/page-001.png')
        decisions=[json.loads(p.read_text()) for p in (store.root(state['id'])/'creator/decisions').glob('*.json')]
        self.assertEqual(sum(d['action']=='reopen' for d in decisions),1)
        self.assertEqual(sum(d['action']=='approve' and d['stage_id']=='pages/page-001.png' for d in decisions),2)

    def test_keep_original_retains_new_attempts_but_restores_approval_and_prompt(self):
        state=self.reviewing_second_page();prior=copy.deepcopy(state)
        state=self.revise(state);state=self.png(state)
        store.stage(state)['prompt_base']={'prompt':'New experimental prompt.'};store.save(state)
        state=revision.keep_original(store.read(state['id']))
        target=store.stage(state,'pages/page-001.png');old=store.stage(prior,'pages/page-001.png')
        self.assertEqual(target['selected'],old['selected']);self.assertEqual(target['decision_id'],old['decision_id'])
        self.assertEqual(target['status'],'approved');self.assertNotIn('prompt_base',target)
        self.assertEqual(len(target['candidates']),2)
        self.assertEqual(state['job'],prior['job']);self.assertEqual(state['current_stage'],prior['current_stage'])
        engine.approved(state,target['id'])
        decisions=[json.loads(p.read_text()) for p in (store.root(state['id'])/'creator/decisions').glob('*.json')]
        self.assertEqual(sum(d['action']=='keep_original' for d in decisions),1)

    def test_busy_reference_and_nested_revision_rejections_do_not_mutate(self):
        state=self.reviewing_second_page()
        before=copy.deepcopy(state)
        with self.assertRaisesRegex(ValueError,'stay fixed'):revision.begin(state,'story')
        self.assertEqual(state,before)
        for status in ['queued','generating','exporting']:
            state['status']=status
            with self.assertRaisesRegex(store.Conflict,'Wait'):self.revise(state)
        state['status']='awaiting_review';state=self.revise(state)
        with self.assertRaisesRegex(store.Conflict,'Finish revising'):revision.begin(state,'cover.png')
        state['status']='generating'
        with self.assertRaisesRegex(store.Conflict,'Wait'):revision.keep_original(state)

    def test_error_return_and_dependent_scene_preserve_context(self):
        state=self.reviewing_second_page();state.update(status='error',error='An interrupted later page.')
        store.save(state);before=copy.deepcopy(state)
        state=self.revise(state);state=self.approve(self.png(state))
        for key in revision.RETURN_FIELDS:self.assertEqual(state[key],before[key])
        store.stage(state)['references'].append('pages/page-001.png')
        with self.assertRaisesRegex(ValueError,'used as a reference'):self.revise(state)

    def test_cancel_finished_revision_keeps_finished_url_and_original_approval(self):
        state=self.reviewing_second_page()
        while state['status']!='exporting':state=self.approve(self.png(state))
        state=engine.export_session(state);url=state['book_url']
        state=self.revise(state,'cover.png')
        self.assertEqual(state['page_revision']['return_to']['status'],'complete')
        state=revision.keep_original(state)
        self.assertEqual(state['status'],'complete');self.assertEqual(state['book_url'],url)
        self.assertNotIn('export_revision',state)
        engine.approved(state,'cover.png')

    def test_finished_book_gets_new_export_old_export_and_other_pages_unchanged(self):
        state=self.reviewing_second_page()
        while state['status']!='exporting':state=self.approve(self.png(state))
        state=engine.export_session(state);root=store.root(state['id']);first=state['book_url']
        old_files={p.relative_to(root/'export').as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'export').rglob('*') if p.is_file()}
        state=self.revise(state);state=self.png(state)
        state=self.approve(state)
        self.assertEqual(state['status'],'exporting')
        state=engine.export_session(store.read(state['id']))
        self.assertEqual(state['status'],'complete');self.assertNotEqual(state['book_url'],first)
        for name,sha in old_files.items():self.assertEqual(hashlib.sha256((root/'export'/name).read_bytes()).hexdigest(),sha)
        target=root/'exports'/state['export_revision']
        manifest=json.loads((target/'manifest.json').read_text())
        record=next(a for a in manifest['approvals'] if a['stage']=='pages/page-001.png')
        self.assertEqual(record['candidate'],'pages/page-001.png:2')
        for name in ['story.json','pages/page-002.png','pages/page-003.png']:
            self.assertEqual((target/name).read_bytes(),(root/'export'/name).read_bytes())
        state=engine.export_session(state) # restart/retry is idempotent
        self.assertEqual(len(state['exports']),2)
        self.assertIn(first,[item['book_url'] for item in state['exports']])


class PageRevisionApiTests(RevisionFixtures,unittest.IsolatedAsyncioTestCase):
    async def test_error_with_live_job_cannot_be_parked(self):
        from aiohttp import web
        from aiohttp.test_utils import TestClient,TestServer
        from unittest.mock import AsyncMock
        api=importlib.import_module('book_test_pack.assisted_web')
        state=self.reviewing_second_page();state.update(status='error',error='MCP receipt missing.');store.save(state)
        app=web.Application();app.router.add_post('/api/{sid}',api.api)
        before=(store.root(state['id'])/'creator.json').read_bytes()
        async with TestClient(TestServer(app)) as client:
            with patch.object(api,'locate',new=AsyncMock(return_value=('fixture-job','active'))),patch.object(api,'launch') as launch:
                r=await client.post('/api/'+state['id'],json={'action':'reopen','revision':state['revision'],'stage_id':'pages/page-001.png'},headers={'X-Book-Creator':'1'})
                self.assertEqual(r.status,409);self.assertIn('still running',await r.text())
                launch.assert_not_called()
        self.assertEqual((store.root(state['id'])/'creator.json').read_bytes(),before)

    async def test_api_reopen_edit_approve_and_return_without_replaying_later_stage(self):
        from aiohttp import web
        from aiohttp.test_utils import TestClient,TestServer
        api=importlib.import_module('book_test_pack.assisted_web')
        state=self.reviewing_second_page();sid=state['id'];return_job=copy.deepcopy(state['job'])
        app=web.Application();app.router.add_post('/api/{sid}',api.api)
        async with TestClient(TestServer(app)) as client:
            async def send(action,**extra):
                return await client.post('/api/'+sid,json={'action':action,'revision':state['revision'],**extra},headers={'X-Book-Creator':'1'})
            with patch.object(api,'launch') as launch:
                r=await send('reopen',stage_id='pages/page-001.png');self.assertEqual(r.status,200,await r.text());state=await r.json()
                launch.assert_not_called()
                self.assertTrue(state['can_revise_pages'])
                r=await send('edit',candidate_id='pages/page-001.png:1',feedback='Keep the mouse, repair the shell.')
                self.assertEqual(r.status,200,await r.text());state=await r.json();launch.assert_called_once_with(sid,resume=False)
                self.assertEqual(state['job']['mode'],'edit');self.assertEqual(state['job']['source_candidate'],'pages/page-001.png:1')
                # Complete the mocked edit, with the saved original bytes as a fixture output.
                original=engine.selected(state,state['current_stage']);path=engine.directory(sid,state['current_stage'],state['job']['attempt'])/'candidate.png'
                helpers.fixtures.storage.write_exclusive(path,store.candidate_path(state,original).read_bytes())
                state=store.record_candidate(sid,state['current_stage'],state['job']['attempt'],path,{'approved_reference_sha256':{},'method':'test_fixture'})
                launch.reset_mock()
                r=await send('approve',candidate_id=store.stage(state)['selected']);self.assertEqual(r.status,200,await r.text());state=await r.json()
                self.assertEqual(state['current_stage'],'pages/page-002.png');self.assertEqual(state['job'],return_job)
                launch.assert_not_called()
                stale=await client.post('/api/'+sid,json={'action':'reopen','revision':state['revision']-1,'stage_id':'pages/page-001.png'},headers={'X-Book-Creator':'1'})
                self.assertEqual(stale.status,409)

    async def test_legacy_alias_uses_canonical_job_identity(self):
        from aiohttp import web
        from aiohttp.test_utils import TestClient,TestServer
        api=importlib.import_module('book_test_pack.assisted_web')
        state=self.state();sid=state['id'];oldroot=store.root(sid)
        legacy=sid.replace('book-','book-assisted-',1);oldroot.rename(store.root(legacy));state['id']=legacy;store.save(state)
        app=web.Application();app.router.add_post('/api/{sid}',api.api)
        async with TestClient(TestServer(app)) as client:
            with patch.object(api,'launch') as launch:
                r=await client.post('/api/'+sid,json={'action':'regenerate','revision':state['revision'],'candidate_id':'story:1'},headers={'X-Book-Creator':'1'})
                self.assertEqual(r.status,200,await r.text())
                launch.assert_called_once_with(legacy,resume=False)
                self.assertEqual((await r.json())['creator_url'],'/book-builder/create/'+sid)


class ReferenceRevisionTests(RevisionFixtures, unittest.TestCase):
    def approved_through_first_character(self):
        state = self.prepare()  # story + plan approved, current stage style.png
        state = self.approve(self.png(state))            # style.png
        state = self.approve(self.png(state))            # characters/mira.png
        state = self.approve(self.png(state))            # characters/pip.png
        return state                                       # current: characters/fern.png

    def test_replacing_style_invalidates_everything_downstream(self):
        state = self.approved_through_first_character()
        old_style = engine.selected(state, 'style.png')
        old_pip = engine.selected(state, 'characters/pip.png')
        state = revision.begin(state, 'style.png')
        self.assertEqual(state['current_stage'], 'style.png')
        self.assertEqual(store.stage(state, 'style.png')['status'], 'awaiting_review')
        state = self.png(state)
        state = self.approve(state)
        # The pipeline resumes right after the style with dependents reset.
        self.assertEqual(state['current_stage'], 'characters/mira.png')
        self.assertEqual(state['status'], 'ready')
        self.assertNotIn('page_revision', state)
        self.assertEqual(store.stage(state, 'style.png')['status'], 'approved')
        for dependent in ('characters/mira.png', 'characters/pip.png'):
            self.assertEqual(store.stage(state, dependent)['status'], 'pending')
        # Old attempts survive for comparison; story and plan stay approved.
        self.assertNotEqual(engine.selected(state, 'style.png')['id'], old_style['id'])
        pip = store.stage(state, 'characters/pip.png')
        self.assertEqual([c['id'] for c in pip['candidates']], [old_pip['id']])
        self.assertEqual(store.stage(state, 'story')['status'], 'approved')
        self.assertEqual(store.stage(state, 'plan')['status'], 'approved')

    def test_keep_original_after_reference_revision_restores_downstream(self):
        state = self.approved_through_first_character()
        prior = copy.deepcopy(state)
        state = revision.begin(state, 'style.png')
        state = self.png(state)
        state = revision.keep_original(store.read(state['id']))
        self.assertEqual(state['status'], prior['status'])
        self.assertEqual(state['current_stage'], prior['current_stage'])
        self.assertEqual(store.stage(state, 'style.png')['status'], 'approved')
        self.assertEqual(store.stage(state, 'characters/mira.png')['status'], 'approved')
        self.assertEqual(store.stage(state, 'characters/pip.png')['status'], 'approved')

    def test_pending_downstream_is_not_reset_and_scenes_still_guard_references(self):
        state = self.approved_through_first_character()
        # Nothing approved downstream of fern yet: revising fern's neighbour
        # prop-style is covered above; a never-approved stage cannot be reopened.
        with self.assertRaisesRegex(ValueError, 'Only an approved'):
            revision.begin(state, 'characters/fern.png')
        store.stage(state, 'locations/garden.png')['status'] = 'pending'
        state = revision.begin(state, 'style.png')
        state = self.approve(self.png(state))
        self.assertEqual(store.stage(state, 'locations/garden.png')['status'], 'pending')
