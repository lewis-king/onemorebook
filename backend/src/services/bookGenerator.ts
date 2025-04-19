import { ChatOpenAI } from "langchain/chat_models/openai";
import { PromptTemplate } from "langchain/prompts";
import { StructuredOutputParser } from "langchain/output_parsers";
import { z } from "zod";
import { Book } from '../types/book';
import { ImageGeneratorService } from './imageGenerator';
import { ImageStorageService } from './imageStorage';

export class BookGeneratorService {
    private llm: ChatOpenAI;
    private parser: StructuredOutputParser<any>;
    private imageGenerator: ImageGeneratorService;
    private imageStorage: ImageStorageService;

    constructor() {
        if (!process.env.OPENAI_API_KEY) {
            throw new Error('OpenAI API key not found');
        }

        this.llm = new ChatOpenAI({
            modelName: "gpt-4.1",
            temperature: 0.7,
            openAIApiKey: process.env.OPENAI_API_KEY,
        });

        // More strict parser
        this.parser = StructuredOutputParser.fromZodSchema(
            z.object({
                title: z.string().min(1),
                content: z.string().min(1),  // We'll validate page breaks in the content
                metadata: z.object({
                    ageRange: z.string(),
                    theme: z.string(),
                    characters: z.array(z.string())
                }),
            })
        );

        this.imageGenerator = new ImageGeneratorService();
        this.imageStorage = new ImageStorageService();
    }

    async generateBook(prompt: string): Promise<Omit<Book, 'id' | 'createdAt' | 'stars'>> {
        try {
            // Generate the story content
            const storyContent = await this.generateStoryContent(prompt);

            // Create a focused prompt for the cover image
            const coverImagePrompt = `Create a children's book cover for "${storyContent.title}". 
        The story is about ${storyContent.metadata.characters.join(', ')} 
        and has themes of ${storyContent.metadata.theme}. 
        The target age range is ${storyContent.metadata.ageRange}.`;

            // Generate image with DALL-E
            const dalleImage = await this.imageGenerator.generateCoverImage(coverImagePrompt);

            // Generate a temporary ID for the book
            const tempId = `temp-${Date.now()}`;

            // Upload to S3 and get permanent URL
            const s3Url = await this.imageStorage.uploadImage(dalleImage.url, tempId);

            // Return the complete book data
            return {
                partitionKey: "BOOK",
                title: storyContent.title,
                content: storyContent.content,
                metadata: storyContent.metadata,
                coverImage: {
                    url: s3Url,
                    platformUrl: dalleImage.url,
                    prompt: dalleImage.prompt,
                },
                pageImages: []
            };
        } catch (error) {
            console.error('Error in book generation:', error);
            throw new Error('Failed to generate book: ' + (error as Error).message);
        }
    }

    private async generateStoryContent(prompt: string): Promise<Omit<Book, 'id' | 'createdAt' | 'stars' | 'coverImage'>> {
        const template = `You are a professional children's book author. Create a children's story with the following exact structure:

{format_instructions}

REQUIRED FORMAT:
The content field should be a single text field containing the entire story with PAGE_BREAK markers between pages.

Example of correct response structure (replace with your story):

Title: The Magical Garden

Content: In a colorful garden filled with butterflies, lived a young fairy named Luna. She had sparkly wings and loved to help flowers grow.
PAGE_BREAK
One day, Luna discovered a wilting rose that had lost all its color. 'Don't worry,' she whispered to the flower, 'I will help you.'
PAGE_BREAK
Luna sprinkled her magical fairy dust on the rose, but nothing happened. She knew she needed to try something different.
PAGE_BREAK
She gathered her friends - a wise owl, a hardworking bee, and a gentle rain cloud - to help her with the rose.
PAGE_BREAK
Together, they combined their magic: the owl's wisdom, the bee's honey, the cloud's rain, and Luna's fairy dust.
PAGE_BREAK
Suddenly, the rose began to glow! Its color returned brighter than ever, and it became the most beautiful flower in the garden.

Metadata:
- Age Range: 4-6 years
- Theme: friendship and cooperation
- Characters: Luna the fairy, wise owl, hardworking bee, rain cloud

CRITICAL REQUIREMENTS:
1. The story MUST be at least 6 pages long
2. Each page must be separated by 'PAGE_BREAK'
3. All story content must be in one continuous text
4. The content must be properly formatted for the Zod parser
5. Include appropriate metadata

Now write a complete story based on this prompt: {prompt}`;

        const promptTemplate = new PromptTemplate({
            template,
            inputVariables: ["prompt"],
            partialVariables: {
                format_instructions: this.parser.getFormatInstructions(),
            },
        });

        const input = await promptTemplate.format({ prompt });
        let response = await this.llm.invoke(input);

        // Validate page count before parsing
        const pages = response.text.split('PAGE_BREAK').filter(page => page.trim().length > 0);
        if (pages.length < 6) {
            const retryPrompt = `Your previous response only had ${pages.length} pages. Please generate a new story with at least 6 pages. Remember to keep all content in a single continuous text with PAGE_BREAK separators.\n\n${input}`;
            response = await this.llm.invoke(retryPrompt);
        }

        return this.parser.parse(response.text);
    }
}
