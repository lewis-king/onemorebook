"""Shared interpretation of private camera staging, leaving public text intact."""
import re

SPECIAL_VIEW = r'\b(cutaway|cross[- ]section|split[- ](?:view|screen))\b'


def continuous_view(project, prose=''):
    requested = ' '.join(str(project.get('config', {}).get(k, ''))
                         for k in ('story_idea', 'art_style')) + ' ' + prose
    return (project.get('render_settings', {}).get('compact_prompt_policy', 0) >= 11
            and not re.search(SPECIAL_VIEW, requested, re.I))


def normalize(project, prose, text):
    if not continuous_view(project, prose):
        return text
    return re.sub(r'\b(?:cutaway|cross[- ]section(?:al)?|split[- ](?:view|screen))\s*(?:view)?\b',
                  'close view', text, flags=re.I)


class ScenePromptError(ValueError):
    """One scene could not be planned; canonical integrity errors remain fatal."""
