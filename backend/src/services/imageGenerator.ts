import { DallEAPIWrapper } from "@langchain/openai";

export class ImageGeneratorService {
    private imageModel: DallEAPIWrapper;

    constructor() {
        if (!process.env.OPENAI_API_KEY) {
            throw new Error('OpenAI API key not found');
        }

        this.imageModel = new DallEAPIWrapper({
            modelName: "dall-e-3",
            size: "1024x1024",
            quality: "standard",
            n: 1,
        });
    }

    async generateCoverImage(prompt: string): Promise<{ url: string, prompt: string }> {
        try {
            const imageUrl = await this.imageModel.invoke(
                `Book cover illustration: ${prompt}. Style: Children's book illustration, bright, engaging, appropriate for young readers.`
            );

            if (!imageUrl) {
                throw new Error('No image generated');
            }

            return {
                url: imageUrl,
                prompt: prompt,
            };
        } catch (error) {
            console.error('Error generating image:', error);
            throw new Error('Failed to generate cover image');
        }
    }
}