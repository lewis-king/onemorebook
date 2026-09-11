from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
from .preview import register_preview_routes

register_preview_routes()

from .assisted_nodes import CLASSES
from .assisted_web import register as register_assisted_routes
NODE_CLASS_MAPPINGS.update({cls.__name__:cls for cls in CLASSES})
NODE_DISPLAY_NAME_MAPPINGS.update({
    'BookAssistedStart':'Book Creator · Start assisted book',
    'BookAssistedStep':'Book Creator · Generate one stage',
    'BookAssistedReference':'Book Creator · Approved reference',
    'BookAssistedSaveCandidate':'Book Creator · Save for your review',
})
register_assisted_routes()

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
