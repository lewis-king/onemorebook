// src/services/bookGenerator.ts
import { ChatOpenAI } from "langchain/chat_models/openai";
import { PromptTemplate } from "langchain/prompts";
import { StructuredOutputParser } from "langchain/output_parsers";
import { z } from "zod";
import { Book } from '../types/book';
import { ImageGeneratorService } from './imageGenerator';

export class BookGeneratorService {
    private llm: ChatOpenAI;
    private parser: StructuredOutputParser<any>;
    private imageGenerator: ImageGeneratorService;

    constructor() {
        if (!process.env.OPENAI_API_KEY) {
            throw new Error('OpenAI API key not found');
        }

        this.llm = new ChatOpenAI({
            modelName: "gpt-3.5-turbo",
            temperature: 0.7,
            openAIApiKey: process.env.OPENAI_API_KEY,
        });

        this.parser = StructuredOutputParser.fromZodSchema(
            z.object({
                title: z.string(),
                content: z.string(),
                metadata: z.object({
                    ageRange: z.string(),
                    theme: z.string(),
                    characters: z.array(z.string()),
                }),
            })
        );

        this.imageGenerator = new ImageGeneratorService();
    }

    async generateBook(prompt: string): Promise<Omit<Book, 'id' | 'createdAt' | 'stars'>> {
        try {
            // First generate the story content
            const storyContent = await this.generateStoryContent(prompt);

            // Create a focused prompt for the cover image based on the story details
            const coverImagePrompt = `Create a children's book cover for "${storyContent.title}". 
        The story is about ${storyContent.metadata.characters.join(', ')} 
        and has themes of ${storyContent.metadata.theme}. 
        The target age range is ${storyContent.metadata.ageRange}.`;

            // Generate the cover image
            const coverImage = await this.imageGenerator.generateCoverImage(coverImagePrompt);

            const book: {
                dummy: string;
                metadata: { ageRange: string; theme: string; characters: string[] };
                coverImage: { url: string; prompt: string };
                title: string;
                content: string
            } = {
                title: storyContent.title,
                content: storyContent.content,
                metadata: storyContent.metadata,
                coverImage: coverImage,
                dummy: 'BOOK'  // Add this if it's required by your Book interface
            };

            return book;
        } catch (error) {
            console.error('Error in book generation:', error);
            throw new Error('Failed to generate book: ' + (error as Error).message);
        }
    }

    private async generateStoryContent(prompt: string): Promise<Omit<Book, 'id' | 'createdAt' | 'stars' | 'coverImage'>> {
        const template = `
      Create a children's story based on the following prompt: {prompt}
      
      The story should be engaging and appropriate for children.
      The response should include:
      - A catchy title
      - The story content with clear beginning, middle, and end
      - Metadata including target age range, theme, and main characters
      
      Make sure the story length is appropriate for a children's book depending on age range.
      
      {format_instructions}
    `;

        const promptTemplate = new PromptTemplate({
            template,
            inputVariables: ["prompt"],
            partialVariables: {
                format_instructions: this.parser.getFormatInstructions(),
            },
        });

        const input = await promptTemplate.format({ prompt });
        const response = await this.llm.invoke(input);
        return this.parser.parse(response.text);
    }
}