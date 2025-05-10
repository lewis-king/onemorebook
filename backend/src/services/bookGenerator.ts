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
      modelName: process.env.LLM_MODEL || 'o3-mini',
      // temperature: 0.9,
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
      The writing style should be lively and age-appropriate. For younger children, use simple words, repetition, and gentle humor. For older children, allow for more complex sentences and subtle humor. The tone should match the age range (e.g., gentle and soothing for ages 3-5, adventurous and imaginative for ages 6-8).
      Each character should have a clear personality trait or quirk that is reflected in the story. Settings should be described vividly, and each page should introduce a new visual element or scene to keep the story visually engaging.
      The story should have a gentle theme or lesson appropriate for the age range (e.g., friendship, courage, kindness), woven naturally into the narrative.
      The book should have at least 5 pages${request.numOfPages ? ` (target: ${request.numOfPages} pages)` : ' (ideally more so that the story can be more engaging)'}, where each page has a short paragraph of text (2-3 sentences).
      The story should be about what is described in the story prompt, should include the listed characters and be fun, engaging and unique.
      For each page, in addition to the text, include a list of the main characters present on that page (from the provided character list) as an array called charactersPresent. IMPORTANT: For each character in charactersPresent, include ONLY the character's name (e.g., "Benny"). If a character does not appear on a page, do not include them in that page's charactersPresent array.
      For each page's imagePrompt, write a detailed, natural description for generating an illustration that matches the text on that page. When referencing a character, always use the format: Character Name - [descriptive adjective phrase] (e.g., "Luna (a brave, adventurous young fox with a bushy tail, golden fur, and a playful spirit)"). The adjective phrase should be highly descriptive and suitable for image generation (include species, color, personality traits, clothing, etc.). The imagePrompt should explicitly and naturally mention all relevant characters present on that page (using this format), so that the prompt is suitable for generating an accurate illustration. Do not just append the characters—integrate them into the scene description. Specify the illustration style (e.g., bright watercolor, playful cartoon), main colors, and the overall mood of the scene.
      For the coverImagePrompt, write a detailed, natural description for generating the book cover illustration. The coverImagePrompt should visually and descriptively feature all the main characters (using the Character Name - [descriptive adjective phrase] format) and capture the overall theme or story of the book. Integrate the characters and theme naturally into the scene description, specifying the illustration style (e.g., bright watercolor, playful cartoon), main colors, and the overall mood of the cover. The prompt should be ready to use for generating an accurate and engaging book cover image.
      Ensure the story and illustrations reflect diversity and inclusion, showing characters of different backgrounds and abilities.
      Output should be formatted as valid JSON with the following structure:
      {{
        "title": "The Book Title",
        "theme": "The theme of the book based on one of these categories: Animals, Adventure, Fantasy, Friendship, Mystery, Feelings, School Life, Space, Sci-Fi, Superheroes, Fairytales, Family, Dinosaurs, Nature, Holidays, Seasons, Monsters",
        "bookSummary": "A short summary of the book",
        "characters": ["Main Character", "Character 2", "Character 3"],
        "mainCharacterDescriptivePrompt": "Main Character - [descriptive adjective phrase]",
        "coverImagePrompt": "A detailed description for generating the book cover",
        "styleReferencePrompt": "A detailed description for generating the book style - should not include characters but the overall style and mood of the book",
        "pages": [
          {{
            "pageNumber": 1,
            "text": "The text content for page 1 - 2+ sentences (based on age range)",
            "imagePrompt": "A detailed image prompt for page 1",
            "charactersPresent": ["Character 1", "Character 2"]
            "isMainCharacterPresent": true - if the main character is referenced in the text, false if not,
          }}
          // ...and so on for all pages
        ]
      }}
      Double-check that your output is valid JSON and matches the structure exactly, with no trailing commas or comments.
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
        theme: z.string(),
        bookSummary: z.string(),
        characters: z.array(z.string()),
        mainCharacterDescriptivePrompt: z.string(),
        coverImagePrompt: z.string(),
        styleReferencePrompt: z.string(),
        pages: z.array(z.object({
          pageNumber: z.number(),
          text: z.string(),
          imagePrompt: z.string(),
          charactersPresent: z.array(z.string()).optional(),
          isMainCharacterPresent: z.boolean().optional(),
        })),
      });
      const validatedData = BookResponseSchema.parse(bookData);
      // Compose BookContent (no images yet)
      const bookContent: BookContent = {
        id: '', // Will be set after DB insert
        pages: validatedData.pages,
        metadata: {
          title: validatedData.title,
          theme: validatedData.theme,
          bookSummary: validatedData.bookSummary,
          mainCharacterDescriptivePrompt: validatedData.mainCharacterDescriptivePrompt,
          characters: validatedData.characters,
          coverImagePrompt: validatedData.coverImagePrompt,
          styleReferencePrompt: validatedData.styleReferencePrompt,
          ageRange: request.ageRange,
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
    // 1. Generate character reference image ONLY for the main character (index 0)
    const mainCharacterPrompt = bookContent.metadata.mainCharacterDescriptivePrompt;
    const mainCharacterRef = await this.imageGenerator.generateCharacterReference(mainCharacterPrompt);
    const crefUrls = [mainCharacterRef.url];

    // Store main character reference image
    await this.imageStorage.uploadImage(mainCharacterRef.url, bookId, `character1.jpeg`);

    // 2. Generate style reference image(s) from coverImagePrompt and/or bookSummary
    const stylePrompt = bookContent.metadata.styleReferencePrompt;
    const styleRef = await this.imageGenerator.generateStyleReference(stylePrompt);
    const srefUrls = [styleRef.url];
    await this.imageStorage.uploadImage(styleRef.url, bookId, `style1.jpeg`);

    // Optionally store reference URLs in metadata
    (bookContent.metadata as any).characterReferenceUrls = crefUrls;
    (bookContent.metadata as any).styleReferenceUrls = srefUrls;

    // 3. Generate and upload cover image using references
    if (bookContent.pages.length > 0) {
      // Use coverImagePrompt directly (already includes main characters and theme)
      const coverImageResult = await this.imageGenerator.generateCoverImage(
        bookContent.metadata.coverImagePrompt,
        crefUrls,
        srefUrls
      );
      await this.imageStorage.uploadImage(coverImageResult.url, bookId, 'cover.jpg');

      // 4. Generate and upload each page image using references
      // Parallelize image generation and upload for all pages
      const mainCharacterName = bookContent.metadata.characters[0];
      const pageImageTasks = bookContent.pages.map(async (page, i) => {
        // Only pass crefUrl if the main character is referenced in the imagePrompt
        const crefUrlsToPass = page.isMainCharacterPresent ? crefUrls : [];
        return this.imageGenerator.generatePageImage(
          page.imagePrompt,
          bookContent.metadata.bookSummary,
          crefUrlsToPass,
          srefUrls
        ).then(imageResult =>
          this.imageStorage.uploadImage(imageResult.url, bookId, `page${i+1}.jpg`)
        );
      });
      await Promise.all(pageImageTasks);
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
