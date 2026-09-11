"""Prefer intact casts when selecting pixels for a new, mandatory review.

This ranks saved evidence; it cannot approve an image or remove a QA objection.
"""
import math


def cast_penalty(report, expected_ids):
    review = report.get('review', {})
    characters = review.get('characters', [])
    by_id = {c['id']: c for c in characters}
    expected = set(expected_ids)
    penalty = len(expected.symmetric_difference(by_id)) + len(characters)-len(by_id)
    for cid in expected:
        c = by_id.get(cid, {})
        count = c.get('count')
        penalty += abs(count-1) if type(count) is int else 1
        penalty += c.get('identity_matches') is not True
    unexpected = review.get('unexpected_character_count')
    penalty += unexpected if type(unexpected) is int and unexpected >= 0 else 1
    # Use the reconciled count when a face was correctly classified as a statue.
    # A blind inventory alone must not reintroduce that resolved false rejection.
    reconciliation = report.get('count_reconciliation') or {}
    inventory = reconciliation if reconciliation.get('resolved') else (report.get('inventory') or {})
    count = inventory.get('figure_count')
    if type(count) is int:
        penalty += abs(count-len(expected_ids))
    return penalty


def rank_candidate(report, expected_ids, compared_choice=False, approved=False):
    review = report.get('review', {})
    badness = 10*sum(value is not True for value in review.get('checks', {}).values())
    badness += len(review.get('issues', []))
    if review.get('checks', {}).get('no_unwanted_text') is False:
        badness += 50
    badness += 100*sum(c.get('appearance_matches') is not True for c in review.get('characters', []))
    for geometry in (report.get('geometry') or {}).values():
        factor = geometry.get('relative_factor')
        if isinstance(factor, (int, float)) and factor > 0:
            badness += min(20, 10*abs(math.log(factor)))
    # A whole-set comparison breaks ties only within the same cast severity.
    # Neither a recent rendition nor the chosen draft may conceal a better cast.
    return (cast_penalty(report, expected_ids), not approved, not compared_choice, badness)


def can_correct_cast(report, expected_ids):
    review = report.get('review', {})
    return (cast_penalty(report, expected_ids) == 0
            and all(c.get('appearance_matches') is True for c in review.get('characters', [])))
