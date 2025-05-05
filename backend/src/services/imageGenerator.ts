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

// Utility function to sanitize prompts for image generation
function sanitizePrompt(prompt: string): string {
    return prompt
        .replace(/\—/g, '-')
        .replace(/[—–]/g, '-') // em dash or en dash to hyphen
        .replace(/--+/g, '-')   // double or more hyphens to single hyphen
        .replace(/\s+/g, ' ')  // normalize whitespace
        .trim();
}

export class ImageGeneratorService {

    private async requestImage(prompt: string, extraParams: Record<string, any> = {}): Promise<{ url: string, prompt: string }> {
        try {
            console.log('[Midjourney API SANITIZED PROMPT]', prompt);

            const body = JSON.stringify({
                prompt: prompt,
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
                throw new Error(`Midjourney API error: ${response.status} ${errorText} body: ${body}`);
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
            return { url: imageUrl, prompt: prompt };
        } catch (error) {
            console.error('Error generating image:', error);
            throw new Error('Failed to generate image');
        }
    }

    async generateCharacterReference(prompt: string): Promise<{ url: string, prompt: string }> {
        const cleanedPrompt = sanitizePrompt(prompt);
        return this.requestImage(`Children's book character reference: ${cleanedPrompt}`);
    }

    async generateStyleReference(prompt: string): Promise<{ url: string, prompt: string }> {
        const cleanedPrompt = sanitizePrompt(prompt);
        const finalPrompt = `Children's book style reference: ${cleanedPrompt}`;
        console.log('[generateStyleReference FINAL PROMPT]', finalPrompt);
        return this.requestImage(finalPrompt);
    }

    async generateCoverImage(prompt: string, crefUrls: string[] = [], srefUrls: string[] = []): Promise<{ url: string, prompt: string }> {
        // Sanitize prompt before using
        const cleanedPrompt = sanitizePrompt(prompt);
        const cref = crefUrls[0] ? `--cref ${crefUrls[0]} --cw 100` : '';
        const sref = srefUrls[0] ? `--sref ${srefUrls[0]}` : '';
        const fullPrompt = `${cleanedPrompt} ${cref} ${sref}`.replace(/ +/g, ' ').trim();
        return this.requestImage(fullPrompt);
    }

    async generatePageImage(prompt: string, summary: string, crefUrls: string[] = [], srefUrls: string[] = []): Promise<{ url: string, prompt: string }> {
        // Sanitize prompt before using
        const cleanedPrompt = sanitizePrompt(prompt);
        const cref = crefUrls[0] ? `--cref ${crefUrls[0]} --cw 100` : '';
        const sref = srefUrls[0] ? `--sref ${srefUrls[0]}` : '';
        const fullPrompt = `${cleanedPrompt} ${cref} ${sref}`.replace(/ +/g, ' ').trim();
        return this.requestImage(fullPrompt);
    }
}