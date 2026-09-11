"""Per-image rendering provenance for the reader, separate from story contracts."""

METHODS = {
    'text_to_image': 'Text to image',
    'reference_generation': 'New image from references',
    'image_edit': 'Image edit of an existing illustration',
    'assembly': 'Assembly of existing images',
    'unknown': 'Generation method not recorded',
}


def from_graph(graph, method):
    nodes = list(graph.values())
    def first(kind):
        return next((n['inputs'] for n in nodes if n['class_type'] == kind), {})
    sampler = first('KSampler')
    schedule = first('Flux2Scheduler')
    latent = first('EmptyFlux2LatentImage') or first('EmptySD3LatentImage')
    return {
        'method': method, 'provenance': 'recorded from executed graph',
        'model': first('UNETLoader').get('unet_name'),
        'loras': [{'name': n['inputs']['lora_name'], 'strength': n['inputs']['strength_model']}
                  for n in nodes if n['class_type'] == 'LoraLoaderModelOnly'],
        'steps': schedule.get('steps', sampler.get('steps')),
        'guidance': first('FluxGuidance').get('guidance'), 'cfg': sampler.get('cfg'),
        'sampler': first('KSamplerSelect').get('sampler_name', sampler.get('sampler_name')),
        'scheduler': 'Flux2Scheduler' if schedule else sampler.get('scheduler'),
        'width': latent.get('width'), 'height': latent.get('height'),
    }


def legacy(project, spec, strategy):
    """Label old artifacts from their saved recipe; never guess an unknown mode."""
    settings = project.get('render_settings', {})
    info = {'method': 'unknown', 'model': None, 'loras': [],
            'provenance': 'derived from saved project settings and attempt strategy'}
    if settings.get('renderer') != 'flux2':
        return info
    info['model'] = settings.get('flux_model')
    if strategy == 'canonical_redraw':
        info['method'] = ('reference_generation' if spec.get('references') or spec.get('visual_references')
                          else 'text_to_image')
    elif strategy in ('duplicate_removal', 'scene_edit', 'masked_size_repair'):
        info['method'] = 'image_edit'
    else:
        return info
    from .render import flux_recipe
    recipe = flux_recipe(settings, spec, fresh=strategy == 'canonical_redraw')
    info.update(steps=recipe['steps'], guidance=recipe['guidance'], sampler='euler',
                scheduler='Flux2Scheduler', width=1024, height=1024)
    if recipe['lora']:
        info['loras'] = [{'name': recipe['lora'], 'strength': 1.0}]
    return info
