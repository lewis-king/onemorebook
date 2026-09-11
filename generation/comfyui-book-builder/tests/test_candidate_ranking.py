"""Recovery must retain useful attempts after a later duplicate-character regression."""
import copy
import hashlib
import importlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_book as fixtures
from test_quality import visual_report

ranking = importlib.import_module('book_test_pack.candidate_ranking')


class CandidateRankingTests(unittest.TestCase):
    setUp = fixtures.BookTests.setUp
    restore_module = fixtures.BookTests.restore_module

    def scene(self):
        self.project['render_settings'].update(renderer='flux2', reference_strategy='cast_guide',
            scene_edit_version=5, candidate_recovery_policy=1, art_attempts=5)
        for c,h in zip(self.project['book']['characters'],[110,50,55]):
            c['height_cm']=h
        return next(s for s in fixtures.story.asset_specs(self.project) if s['name']=='pages/page-002.png')

    def test_extra_unknown_figure_cannot_outrank_intact_cast_even_if_selected_draft(self):
        spec=self.scene()
        intact=visual_report(self.project,spec)
        intact['accepted']=False
        intact['review']['issues']=['Correct a local tail defect.', 'Smooth the ball.']
        extra=copy.deepcopy(intact)
        extra['review']['unexpected_character_count']=1
        extra['review']['issues']=['Extra character.']
        ids=['mira','pip','fern']
        self.assertLess(ranking.rank_candidate(intact,ids), ranking.rank_candidate(extra,ids,compared_choice=True))
        self.assertTrue(ranking.can_correct_cast(intact,ids))
        self.assertFalse(ranking.can_correct_cast(extra,ids))

    def test_resolved_statue_is_not_reintroduced_as_extra_actor(self):
        spec=self.scene()
        report=visual_report(self.project,spec)
        report['inventory']={'figure_count':4}
        report['count_reconciliation']={'resolved':True,'figure_count':3}
        ids=['mira','pip','fern']
        self.assertEqual(ranking.cast_penalty(report,ids),0)
        report['count_reconciliation']['resolved']=False
        self.assertGreater(ranking.cast_penalty(report,ids),0)

    def test_incomplete_identity_evidence_is_ineligible_for_preserving_cast(self):
        spec=self.scene()
        report=visual_report(self.project,spec)
        ids=['mira','pip','fern']
        for changed in ('missing_record','wrong_identity','duplicate','unknown_figure'):
            candidate=copy.deepcopy(report)
            if changed=='missing_record': candidate['review']['characters'].pop()
            if changed=='wrong_identity': candidate['review']['characters'][0]['identity_matches']=False
            if changed=='duplicate': candidate['review']['characters'][0]['count']=2
            if changed=='unknown_figure': candidate['review']['unexpected_character_count']=1
            self.assertFalse(ranking.can_correct_cast(candidate,ids),changed)

    def test_reuse_searches_past_a_newer_failed_rendition_and_skips_corrupt_bytes(self):
        import torch
        from PIL import Image
        self.project['book_root']=str(self.output/'books/recovery')
        self.project['render_settings'].update(quality_required=True,qa_version='old')
        sources=[]
        for label,extra in [('good',0),('corrupt',0),('newer-regression',1)]:
            source=copy.deepcopy(self.project)
            source['render_root']=str(Path(source['book_root'])/'renders'/label)
            spec=fixtures.story.asset_specs(source)[0]
            png=fixtures.storage.image_bytes(spec,torch.rand((1,1024,1024,3)))
            report=visual_report(source,spec)
            report.update(accepted=False,png_sha256=hashlib.sha256(png).hexdigest(),seed=spec['seed'],prompt=spec['prompt'])
            report['review']['unexpected_character_count']=extra
            report['review']['issues']=['Extra figure'] if extra else ['Small texture defect']
            directory=fixtures.storage.review_directory(source,spec)
            fixtures.storage.write_exclusive(directory/'attempt-01.png',png)
            fixtures.storage.write_json(directory/'attempt-01-review.json',report)
            fixtures.storage.write_json(Path(source['render_root'])/'project.json',source)
            if label=='corrupt': (directory/'attempt-01.png').write_bytes(b'corrupt')
            sources.append(directory/'attempt-01.png')
        target=copy.deepcopy(self.project)
        target['render_root']=str(Path(target['book_root'])/'renders/target')
        target['render_settings'].update(qa_version='new',candidate_recovery_policy=1)
        spec=fixtures.story.asset_specs(target)[0]
        with patch('book_test_pack.draft_selection.selected_draft_candidate',return_value={'path':str(sources[2])}):
            self.assertTrue(fixtures.storage.reuse_candidate_pixels(target,spec))
        out=fixtures.storage.review_directory(target,spec)
        meta=json.loads((out/'attempt-01-render.json').read_text())
        self.assertEqual(meta['reused_from']['path'],str(sources[0]))
        self.assertEqual(Image.open(out/'attempt-01.png').tobytes(),Image.open(sources[0]).tobytes())
        self.assertFalse(fixtures.storage.approval_path(target,spec).exists())
        self.assertFalse(fixtures.storage.valid_asset(target,spec))

    def test_retry_returns_to_earlier_intact_cast_after_regression(self):
        nodes=importlib.import_module('book_test_pack.nodes')
        repair=importlib.import_module('book_test_pack.repair')
        spec=self.scene()
        report=visual_report(self.project,spec)
        report['accepted']=False
        report['review']['checks']['anatomy_sound']=False
        report['review']['retry_instructions']=['Remove the extra tail from the child.']
        directory=fixtures.storage.review_directory(self.project,spec)
        fixtures.storage.write_json(directory/'attempt-01-review.json',report)
        regression=copy.deepcopy(report)
        regression['review']['unexpected_character_count']=1
        regression['review']['retry_instructions']=['Remove the extra child.']
        fixtures.storage.write_json(directory/'attempt-02-review.json',regression)
        with patch.object(repair,'try_scale_repair',return_value=False), patch.object(nodes,'expand_attempt',return_value={}) as expand:
            nodes.BookV2RenderAsset().run(self.project,spec,'')
        self.assertEqual(expand.call_args.args[2:5],(3,'Remove the extra tail from the child.',1))
        strategy=json.loads((directory/'attempt-03-strategy.json').read_text())
        self.assertEqual(strategy['recovered_from_regression'],{'latest_attempt':2,'chosen_attempt':1})


if __name__=='__main__': unittest.main()
