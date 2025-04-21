import { ChatOpenAI } from '@langchain/openai';
import { PromptTemplate } from '@langchain/core/prompts';
import { z } from 'zod';
import { v4 as uuidv4 } from 'uuid';
import { BookContent, GenerateBookRequest } from '../types';
import { ImageGeneratorService } from './imageGenerator';
import { ImageStorageService } from './imageStorage';

class BookGeneratorService {
  private openai: ChatOpenAI;
  private static instance: BookGeneratorService;
  private imageGenerator: ImageGeneratorService;
  private imageStorage: ImageStorageService;

  private constructor() {
    const apiKey = process.env.OPENAI_API_KEY;
    if (!apiKey) {
      throw new Error('Missing OpenAI API key. Please check your .env file.');
    }
    
    this.openai = new ChatOpenAI({
      apiKey,
      modelName: 'gpt-4.1',
      temperature: 0.9,
    });
    this.imageGenerator = new ImageGeneratorService();
    this.imageStorage = new ImageStorageService();
  }

  public static getInstance(): BookGeneratorService {
    if (!BookGeneratorService.instance) {
      BookGeneratorService.instance = new BookGeneratorService();
    }
    return BookGeneratorService.instance;
  }

  async generateBook(request: GenerateBookRequest): Promise<BookContent> {
    const bookId = uuidv4();
    const bookContent = await this.generateBookContent(request);
    const bookContentWithImages = await this.generateAndAttachImages(bookId, bookContent);
    return bookContentWithImages;
  }

  // Step 1: Generate book content (pages, image prompts, no images yet)
  async generateBookContent(request: GenerateBookRequest): Promise<BookContent> {
    // Prompt LLM for book content
    const bookPromptTemplate = PromptTemplate.fromTemplate(`
      Create a children's book with the following details:
      Age Range: {ageRange}
      Characters: {characters}
      Story Prompt: {storyPrompt}
      ${request.numOfPages ? `Number of Pages: ${request.numOfPages}` : ''}

      Write a children's book that is appropriate for the specified age range.
      The book should have at least 5 pages${request.numOfPages ? ` (target: ${request.numOfPages} pages)` : ' (ideally more so that the story can be more engaging)'}, where each page has a short paragraph of text (2-3 sentences).
      The story should be about what is described in the story prompt, should include the listed characters and be fun, engaging and unique.
      Output should be formatted as valid JSON with the following structure:
      {{
        "title": "The Book Title",
        "bookSummary": "A short summary of the book",
        "coverImagePrompt": "A detailed description for generating the book cover",
        "pages": [
          {{
            "pageNumber": 1,
            "text": "The text content for page 1 - 2-3 sentences",
            "imagePrompt": "A detailed image prompt for page 1"
          }}
          // ...and so on for all pages
        ]
      }}
      Each imagePrompt should be a detailed description for generating an illustration that matches the text on that page.
    `);
    const prompt = await bookPromptTemplate.format({
      ageRange: request.ageRange,
      characters: request.characters.join(', '),
      storyPrompt: request.storyPrompt,
    });
    const response = await this.openai.invoke(prompt);
    try {
      let responseText = '';
      if (typeof response === 'string') {
        responseText = response;
      } else if (response && typeof response === 'object') {
        if ('content' in response && typeof response.content === 'string') {
          responseText = response.content;
        } else if ('text' in response && typeof response.text === 'string') {
          responseText = response.text;
        } else if (Array.isArray(response.content)) {
          responseText = response.content.map((part: any) =>
            typeof part === 'string' ? part : part.text || ''
          ).join(' ');
        } else {
          responseText = String(response);
        }
      } else {
        responseText = String(response);
      }
      const jsonString = this.extractJsonFromString(responseText);
      const bookData = JSON.parse(jsonString);
      const BookResponseSchema = z.object({
        title: z.string(),
        bookSummary: z.string(),
        coverImagePrompt: z.string(),
        pages: z.array(z.object({
          pageNumber: z.number(),
          text: z.string(),
          imagePrompt: z.string(),
        })),
      });
      const validatedData = BookResponseSchema.parse(bookData);
      // Compose BookContent (no images yet)
      const bookContent: BookContent = {
        id: '', // Will be set after DB insert
        pages: validatedData.pages,
        metadata: {
          title: validatedData.title,
          bookSummary: validatedData.bookSummary,
          coverImagePrompt: validatedData.coverImagePrompt,
          ageRange: request.ageRange,
          characters: request.characters,
          storyPrompt: request.storyPrompt,
          createdAt: new Date().toISOString(),
        }
      };
      return bookContent;
    } catch (error) {
      console.error('Error parsing book generation response:', error);
      throw new Error('Failed to generate book content');
    }
  }

  // Step 2: Generate/upload images using the book ID, return BookContent with image URLs
  async generateAndAttachImages(bookId: string, bookContent: BookContent): Promise<BookContent> {
    // 1. Generate character reference images from metadata.characters
    const characterPrompts = bookContent.metadata.characters;
    const characterRefs = await Promise.all(
      characterPrompts.map(prompt => this.imageGenerator.generateCharacterReference(prompt))
    );
    const crefUrls = characterRefs.map(ref => ref.url);

    // Store character reference images
    for (let i = 0; i < crefUrls.length; i++) {
      await this.imageStorage.uploadImage(crefUrls[i], bookId, `character${i + 1}.jpeg`);
    }

    // 2. Generate style reference image(s) from coverImagePrompt and/or bookSummary
    // We'll use a single style reference for now, but could expand to more
    const stylePrompt = `${bookContent.metadata.coverImagePrompt}, ${bookContent.metadata.bookSummary}, storybook style, bright, engaging, appropriate for young readers`;
    const styleRef = await this.imageGenerator.generateStyleReference(stylePrompt);
    const srefUrls = [styleRef.url];

    // Store style reference images
    for (let i = 0; i < srefUrls.length; i++) {
      await this.imageStorage.uploadImage(srefUrls[i], bookId, `style${i + 1}.jpeg`);
    }

    // Optionally store reference URLs in metadata
    (bookContent.metadata as any).characterReferenceUrls = crefUrls;
    (bookContent.metadata as any).styleReferenceUrls = srefUrls;

    // 3. Generate and upload cover image using references
    if (bookContent.pages.length > 0) {
      const coverPagePrompt = bookContent.metadata.coverImagePrompt;
      const coverImageResult = await this.imageGenerator.generateCoverImage(coverPagePrompt, crefUrls, srefUrls);
      await this.imageStorage.uploadImage(coverImageResult.url, bookId, 'cover.jpg');
      // 4. Generate and upload each page image using references
      for (let i = 0; i < bookContent.pages.length; i++) {
        const page = bookContent.pages[i];
        const imageResult = await this.imageGenerator.generatePageImage(page.imagePrompt, bookContent.metadata.bookSummary, crefUrls, srefUrls);
        await this.imageStorage.uploadImage(imageResult.url, bookId, `page${i+1}.jpg`);
      }
    }
    return {
      ...bookContent,
      id: bookId,
      pages: bookContent.pages,
    };
  }

  // Autofill characters and story prompt using LLM
  async autofillBookFields({ ageRange, numOfPages }: { ageRange: string, numOfPages?: number }) {
    // Prompt for characters and story prompt
    const autofillPrompt = PromptTemplate.fromTemplate(`
      You are helping a child create a magical storybook. Given the age range: {ageRange}, generate:
      1. A creative story idea (short paragraph explaining the story, imaginative, fun, unique, suitable for the age)
      2. A list of 1-3 main characters (animal, child, mystical creature, etc. Use names and a short description for each, comma-separated)
      Respond as valid JSON with keys 'storyPrompt' and 'characters'.
      Example:
      {{
        "storyPrompt": "A brave kitten and a mystical dragon go on a quest to find a hidden treasure.",
        "characters": ["Milo the brave kitten", "Drago the mystical dragon"]
      }}
    `);
    const prompt = await autofillPrompt.format({ ageRange, numOfPages });
    const response = await this.openai.invoke(prompt);
    // Robustly extract string content from response
    let contentStr = '';
    if (typeof response === 'string') {
      contentStr = response;
    } else if (response && typeof response === 'object') {
      if ('content' in response && typeof response.content === 'string') {
        contentStr = response.content;
      } else if ('text' in response && typeof response.text === 'string') {
        contentStr = response.text;
      } else if (Array.isArray(response.content)) {
        const arr = response.content as any[];
        contentStr = arr.map((c) => c.text || c.content || '').join('\n');
      } else {
        contentStr = String(response);
      }
    } else {
      contentStr = String(response);
    }
    if (!contentStr) {
      throw new Error('Could not extract text content from LLM response');
    }
    const jsonStr = this.extractJsonFromString(contentStr);
    const parsed = JSON.parse(jsonStr);
    // Ensure characters is an array (handle comma-separated string fallback)
    let characters = parsed.characters;
    if (typeof characters === 'string') {
      characters = characters.split(',').map((c: string) => c.trim()).filter(Boolean);
    }
    return {
      storyPrompt: parsed.storyPrompt,
      characters
    };
  }

  private async fetchImageAsUint8Array(imageUrl: string): Promise<Uint8Array> {
    const response = await fetch(imageUrl);
    const arrayBuffer = await response.arrayBuffer();
    return new Uint8Array(arrayBuffer);
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
