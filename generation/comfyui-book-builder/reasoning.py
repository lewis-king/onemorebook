"""Shared request policy for the locally supported story reasoning models."""


def story_reasoning_options(model):
    # Keep unknown/non-thinking models compatible; do not send unsupported flags.
    return ({'think': True, 'num_predict': 8192}
            if any(family in model.lower() for family in ('gemma4', 'qwen3.5')) else {})
