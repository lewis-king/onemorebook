"""Actual input-image budget for the local FLUX.2.dev assisted renderer."""
# BFL recommends at most six reference images for dev (different from pro/klein).
# https://docs.bfl.ml/guides/prompting_editing_overview
MAX_REFERENCE_IMAGES = 6


def scene_reference_count(character_refs, asset_refs):
    # Visible characters are combined into ONE cast image. An otherwise empty
    # scene gets one style image; there is no extra style input on populated scenes.
    return max(1, int(bool(character_refs)) + len(asset_refs))
