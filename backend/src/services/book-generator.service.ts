import { OpenAI } from '@langchain/openai';
import { PromptTemplate } from 'langchain/prompts';
import { z } from 'zod';
import { v4 as uuidv4 } from 'uuid';
import { BookContent, BookPage, GenerateBookRequest } from '../types';

class BookGeneratorService {
  private openai: OpenAI;
  private static instance: BookGeneratorService;

  private constructor() {
    const apiKey = process.env.OPENAI_API_KEY;
    if (!apiKey) {
      throw new Error('Missing OpenAI API key. Please check your .env file.');
    }
    
    this.openai = new OpenAI({
      apiKey,
      modelName: 'gpt-4',
      temperature: 0.7,
    });
  }

  public static getInstance(): BookGeneratorService {
    if (!BookGeneratorService.instance) {
      BookGeneratorService.instance = new BookGeneratorService();
    }
    return BookGeneratorService.instance;
  }

  async generateBook(request: GenerateBookRequest): Promise<BookContent> {
    const bookId = uuidv4();
    
    // Create a prompt template for book generation
    const bookPromptTemplate = PromptTemplate.fromTemplate(`
      Create a children's book with the following details:
      Title: {title}
      Age Range: {ageRange}
      Main Character: {mainCharacter}
      Theme: {theme}
      Additional Information: {additionalInfo}

      Write a children's book that is appropriate for the specified age range.
      The book should have 5 pages, where each page has a short paragraph of text.
      
      Output should be formatted as valid JSON with the following structure:
      {
        "pages": [
          {
            "pageNumber": 1,
            "text": "The text content for page 1",
            "imagePrompt": "A detailed image prompt for page 1"
          },
          ...and so on for all pages
        ]
      }
      
      Each imagePrompt should be a detailed description for generating an illustration that matches the text on that page.
    `);

    // Format the prompt with user inputs
    const prompt = await bookPromptTemplate.format({
      title: request.title,
      ageRange: request.ageRange,
      mainCharacter: request.mainCharacter,
      theme: request.theme,
      additionalInfo: request.additionalInfo || 'None',
    });

    // Call the LLM to generate the book content
    const response = await this.openai.invoke(prompt);
    
    // Parse the JSON response
    try {
      // Extract JSON from the response text
      const jsonString = this.extractJsonFromString(response);
      const bookData = JSON.parse(jsonString);
      
      // Validate the book data structure using zod
      const BookResponseSchema = z.object({
        pages: z.array(z.object({
          pageNumber: z.number(),
          text: z.string(),
          imagePrompt: z.string(),
        })),
      });
      
      const validatedData = BookResponseSchema.parse(bookData);
      
      // Create the final book content object
      const bookContent: BookContent = {
        id: bookId,
        title: request.title,
        pages: validatedData.pages.map(page => ({
          pageNumber: page.pageNumber,
          text: page.text,
          imagePrompt: page.imagePrompt,
        })),
        metadata: {
          ageRange: request.ageRange,
          theme: request.theme,
          additionalInfo: request.additionalInfo || '',
          createdAt: new Date().toISOString(),
        }
      };
      
      return bookContent;
    } catch (error) {
      console.error('Error parsing book generation response:', error);
      throw new Error('Failed to generate book content');
    }
  }

  async generateImage(prompt: string): Promise<Buffer> {
    // This is a placeholder for image generation
    // In a real implementation, you would integrate with DALL-E or another image generation API
    console.log(`[Image generation] Prompt: ${prompt}`);
    
    // Return a mock image (this would be replaced with actual API call)
    // For now, we're just simulating the API call
    console.log('Image would be generated here with an API call to DALL-E or similar service');
    
    // This is just a placeholder - in production, return the actual image buffer
    throw new Error('Image generation not implemented yet');
  }

  // Helper function to extract JSON from a string that might have other text around it
  private extractJsonFromString(text: string): string {
    const jsonRegex = /{[\s\S]*}/;
    const match = text.match(jsonRegex);
    
    if (!match) {
      throw new Error('Could not extract valid JSON from the response');
    }
    
    return match[0];
  }
}

export default BookGeneratorService.getInstance();
