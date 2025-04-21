const MIDJOURNEY_API_KEY = process.env.MIDJOURNEY_API_KEY;
// Update to new endpoint as per deprecation notice
const MIDJOURNEY_API_URL = 'https://api.goapi.ai/mj/v2/imagine';

if (!MIDJOURNEY_API_KEY) {
    throw new Error('Midjourney API key not found');
}

interface MidjourneyApiResponse {
    image_url?: string;
    url?: string;
    [key: string]: any;
}

interface MidjourneyTaskDetail {
    status?: string;
    task_result?: {
        image_url?: string;
        temporary_image_urls?: string[];
    };
}

export class ImageGeneratorService {
    private ensurePromptParamsSpaced(prompt: string): string {
        // Inserts a space before any --param if missing
        return prompt.replace(/([^\s])(--[\w-]+)/g, '$1 $2');
    }

    private async requestImage(prompt: string, extraParams: Record<string, any> = {}): Promise<{ url: string, prompt: string }> {
        try {
            // Ensure prompt params are spaced
            prompt = this.ensurePromptParamsSpaced(prompt);
            const body = JSON.stringify({
                prompt,
                skip_prompt_check: false,
                process_mode: 'fast',
                aspect_ratio: '',
                webhook_endpoint: '',
                webhook_secret: '',
                ...extraParams,
            });
            console.log('[Midjourney API Request]', {
                url: MIDJOURNEY_API_URL,
                headers: {
                    'X-API-Key': MIDJOURNEY_API_KEY!,
                    'Content-Type': 'application/json',
                },
                body: JSON.parse(body),
            });
            // 1. Initial request to start task
            const response = await fetch(MIDJOURNEY_API_URL, {
                method: 'POST',
                headers: {
                    'X-API-Key': MIDJOURNEY_API_KEY!,
                    'Content-Type': 'application/json',
                },
                body,
            });
            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`Midjourney API error: ${response.status} ${errorText}`);
            }
            const data = await response.json() as { task_id: string, success: boolean, status: string, message: string };
            if (!data.task_id) {
                throw new Error('No task_id returned from Midjourney');
            }

            // 2. Poll for completion using the correct endpoint and POST body
            const fetchUrl = 'https://api.goapi.ai/mj/v2/fetch';
            let pollCount = 0;
            const maxPolls = 48; // poll for up to ~4 minutes (5s x 48)
            const pollDelay = 5000; // ms
            let imageUrl = '';
            while (pollCount < maxPolls) {
                await new Promise(res => setTimeout(res, pollDelay));
                pollCount++;
                console.log(`[Midjourney Poll #${pollCount}] Polling for task_id: ${data.task_id}`);
                const pollRes = await fetch(fetchUrl, {
                    method: 'POST',
                    headers: {
                        'X-API-Key': MIDJOURNEY_API_KEY!,
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ task_id: data.task_id }),
                });
                if (!pollRes.ok) {
                    console.warn(`[Midjourney Poll #${pollCount}] Non-OK response: ${pollRes.status}`);
                    continue;
                }
                const pollData = await pollRes.json() as MidjourneyTaskDetail;
                console.log(`[Midjourney Poll #${pollCount}] Status: ${pollData.status}`, JSON.stringify(pollData));
                if (pollData.status === 'completed' || pollData.status === 'finished') {
                    imageUrl = pollData.task_result?.temporary_image_urls?.[0] || pollData.task_result?.image_url || '';
                    break;
                } else if (pollData.status === 'failed') {
                    throw new Error('Midjourney image generation failed');
                } // else, status is 'processing' or other, so keep polling
            }
            if (!imageUrl) {
                throw new Error('No image URL returned from Midjourney after polling');
            }
            return { url: imageUrl, prompt };
        } catch (error) {
            console.error('Error generating image:', error);
            throw new Error('Failed to generate image');
        }
    }

    async generateCharacterReference(prompt: string): Promise<{ url: string, prompt: string }> {
        return this.requestImage(`Children's book character reference: ${prompt}`);
    }

    async generateStyleReference(prompt: string): Promise<{ url: string, prompt: string }> {
        return this.requestImage(`Children's book style reference: ${prompt}`);
    }

    async generateCoverImage(prompt: string, crefUrls: string[] = [], srefUrls: string[] = []): Promise<{ url: string, prompt: string }> {
        let cref = crefUrls.length ? `--cref ${crefUrls.join(' ')} --cw 0` : '';
        let sref = srefUrls.length ? `--sref ${srefUrls.join(' ')}` : '';
        const fullPrompt = `Children's book style - Book cover illustration to generate image for: ${prompt}. ${cref} ${sref}`.trim();
        return this.requestImage(fullPrompt);
    }

    async generatePageImage(prompt: string, summary: string, crefUrls: string[] = [], srefUrls: string[] = []): Promise<{ url: string, prompt: string }> {
        let cref = crefUrls.length ? `--cref ${crefUrls.join(' ')} --cw 0` : '';
        let sref = srefUrls.length ? `--sref ${srefUrls.join(' ')}` : '';
        const fullPrompt = `Children's book style - Book page illustration to generate image for: ${prompt}. Book Summary for context: ${summary}. ${cref} ${sref}`.trim();
        return this.requestImage(fullPrompt);
    }
}