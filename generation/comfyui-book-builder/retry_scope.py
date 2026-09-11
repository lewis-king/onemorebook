"""Choose narrowly scoped edits from measured review evidence, without new approvals."""
import math


def failed_gates(report, expected_ids):
    """Identify unresolved review gates, without interpreting free-form diagnoses."""
    review = report.get('review') or {}
    gates = {'check:' + key for key, value in (review.get('checks') or {}).items() if value is False}
    if review.get('uncertain'):
        gates.add('uncertain')
    if review.get('unexpected_character_count', 0):
        gates.add('unexpected_cast')
    cast = {c['id']: c for c in review.get('characters', [])}
    for cid in expected_ids:
        character = cast.get(cid, {})
        if character.get('count') != 1:
            gates.add('count:' + cid)
        for key in ('identity_matches', 'appearance_matches', 'scale_matches'):
            if character.get(key) is False:
                gates.add(key + ':' + cid)
    for key in ('object_scale_checks', 'visual_reference_checks'):
        for check in report.get(key) or []:
            if check.get('accepted') is False:
                gates.add(key + ':' + str(check.get('id', 'unknown')))
    if review.get('issues') and not gates:
        gates.add('unclassified_review_objection')
    return gates


def scene_edit_restart(failed_reports, strategies, expected_ids):
    """Stop an ineffective edit chain; this decision never grants approval.

    One failed edit with unchanged gates or a regression starts afresh. An edit
    that removes failed gates may get a second edit, but never a third in a row.
    Only recorded scene edits count; a fresh render or a measured masked repair
    starts a new chain. Follow actual source links, not adjacent attempt numbers.
    """
    from .candidate_ranking import cast_penalty
    if not failed_reports:
        return None
    reports = dict(failed_reports)
    latest_attempt, latest = failed_reports[-1]
    strategy = strategies.get(latest_attempt) or {}
    source = strategy.get('source_attempt')
    if (latest.get('accepted') or strategy.get('strategy') != 'scene_edit'
            or type(source) is not int or source >= latest_attempt or source not in reports):
        return None
    previous = reports[source]
    before, after = failed_gates(previous, expected_ids), failed_gates(latest, expected_ids)
    chain_length, current, seen = 0, latest_attempt, set()
    while current not in seen:
        seen.add(current)
        step = strategies.get(current) or {}
        parent = step.get('source_attempt')
        if (step.get('strategy') != 'scene_edit' or type(parent) is not int
                or parent >= current or parent not in reports):
            break
        chain_length += 1
        current = parent
    reason = None
    if cast_penalty(latest, expected_ids) > cast_penalty(previous, expected_ids) or after - before:
        reason = 'The scene edit introduced a new failed review gate; start fresh from canonical references.'
    elif chain_length >= 2:
        reason = 'Two consecutive scene edits were insufficient; start fresh from canonical references.'
    elif after and after == before and not (scale_only_targets(previous) and scale_only_targets(latest)
                                            and not scale_edit_stalled(previous, latest)):
        reason = 'The scene edit left the same review gates unresolved; start fresh from canonical references.'
    if reason is None:
        return None
    return {'version': 1, 'decision': 'canonical_redraw', 'reason': reason,
            'latest_attempt': latest_attempt, 'edited_source_attempt': source,
            'consecutive_scene_edits': chain_length,
            'previous_failed_gates': sorted(before), 'current_failed_gates': sorted(after)}


def scale_only_targets(report):
    review = report.get('review', {})
    if (report.get('accepted') or review.get('uncertain')
            or review.get('unexpected_character_count') != 0
            or not review.get('checks') or not all(review['checks'].values())):
        return {}
    characters = review.get('characters', [])
    if not characters or any(c.get('count') != 1 or c.get('identity_matches') is not True
                             or c.get('appearance_matches') is not True for c in characters):
        return {}
    failed = [c['id'] for c in characters if c.get('scale_matches') is False]
    if not failed:
        return {}
    # A size-only edit must never swallow a separate action, costume or prop veto.
    if any(not any(issue.startswith(cid+' scale:') for cid in failed)
           for issue in review.get('issues', [])):
        return {}
    result = {}
    for cid in failed:
        geometry = report.get('geometry', {}).get(cid, {})
        factor = geometry.get('relative_factor', 0)
        if (geometry.get('measurement_decisive') is not True
                or not isinstance(factor, (int, float)) or not math.isfinite(factor) or factor <= 0):
            return {}
        result[cid] = geometry
    return result


def scale_edit_stalled(previous, current):
    """After an ineffective measured size edit, try fresh canonical conditioning."""
    before, after = scale_only_targets(previous), scale_only_targets(current)
    shared = before.keys() & after.keys()
    if not shared:
        return False
    old_error = sum(abs(math.log(before[cid]['relative_factor'])) for cid in shared)
    new_error = sum(abs(math.log(after[cid]['relative_factor'])) for cid in shared)
    return old_error > 0.05 and new_error >= old_error * 0.90


def measured_scale_instructions(project, report):
    cast = {c['id']: c for c in project['book']['characters']}
    instructions = []
    for cid, geometry in scale_only_targets(report).items():
        target, anchor = cast[cid]['name'], cast[geometry['anchor_id']]['name']
        percent = 100 / geometry['relative_factor']
        relation = 100 * geometry['intended_ratio']
        direction = 'Reduce' if percent < 100 else 'Increase'
        instructions.append(
            f"{direction} {target}'s full body to about {percent:.0f}% of its CURRENT illustrated height. "
            f"The resulting standing height of {target} must be about {relation:.0f}% of {anchor}'s. "
            f"Keep {anchor} and the other characters at their existing sizes. "
            f"Keep {target}'s feet on the same ground plane and preserve its body shape, face and outfit. "
            "Move any held objects coherently with the resized hands, maintaining each grip.")
    return ' '.join(instructions)
