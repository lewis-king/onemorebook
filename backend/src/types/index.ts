import { z } from 'zod';

// Book page interface
export interface BookPage {
  pageNumber: number;
  text: string;
  imagePrompt: string;
  imageUrl?: string;
  charactersPresent?: string[]; // Main characters present on this page
  isMainCharacterPresent?: boolean; // If the main character is present on this page
}

// Book content interface
export interface BookContent {
  id: string;
  pages: BookPage[];
  metadata: {
    title: string;
    theme: string;
    bookSummary: string;
    mainCharacterDescriptivePrompt: string;
    coverImagePrompt: string;
    styleReferencePrompt: string;
    ageRange: string;
    characters: string[];
    storyPrompt: string;
    createdAt: string;
  };
}

// Book database record
export interface Book {
  id: string;
  title: string;
  theme?: string;
  book_summary?: string;
  cover_image_prompt?: string;
  content: BookContent;
  age_range: string;
  story_prompt: string;
  characters: string[];
  created_at?: string;
  updated_at?: string;
  status: 'pending' | 'complete' | 'failed';
}

// Zod schema for book generation request validation
export const GenerateBookSchema = z.object({
  characters: z.array(z.string()).min(1, 'At least one character is required'),
  storyPrompt: z.string().min(1, 'Story prompt is required'),
  ageRange: z.string().min(1, 'Age range is required'),
  numOfPages: z.number().int().min(3, 'Number of pages must be at least 3').optional(),
});

export type GenerateBookRequest = z.infer<typeof GenerateBookSchema>;

// Zod schema for story upload request validation
export const UploadStoryPageSchema = z.object({
  text: z.string().min(1, 'Page text is required'),
  pageNumber: z.number().int().min(1),
  imagePrompt: z.string(),
  charactersPresent: z.array(z.string()).optional(),
  isMainCharacterPresent: z.boolean().optional(),
});

export const UploadStoryMetadataSchema = z.object({
  title: z.string().min(1, 'Title is required'),
  theme: z.string(),
  bookSummary: z.string(),
  mainCharacterDescriptivePrompt: z.string(),
  coverImagePrompt: z.string(),
  styleReferencePrompt: z.string(),
  ageRange: z.string().min(1, 'Age range is required'),
  characters: z.array(z.string()),
  storyPrompt: z.string(),
});

export const UploadStorySchema = z.object({
  story: z.object({
    pages: z.array(UploadStoryPageSchema).min(1, 'At least one page is required'),
    metadata: UploadStoryMetadataSchema,
  }),
  coverImageBase64: z.string().min(1, 'Cover image is required'),
  pageImages: z.array(z.object({
    pageNumber: z.number().int().min(1),
    imageBase64: z.string().min(1),
  })),
  characterImages: z.array(z.object({
    name: z.string(),
    imageBase64: z.string().min(1),
  })).optional(),
});

export type UploadStoryRequest = z.infer<typeof UploadStorySchema>;

export const UpdateStorySchema = z.object({
  story: z.object({
    pages: z.array(UploadStoryPageSchema).min(1, 'At least one page is required'),
    metadata: UploadStoryMetadataSchema,
  }),
  coverImageBase64: z.string().optional(),
  pageImages: z.array(z.object({
    pageNumber: z.number().int().min(1),
    imageBase64: z.string().min(1),
  })).optional(),
  characterImages: z.array(z.object({
    name: z.string(),
    imageBase64: z.string().min(1),
  })).optional(),
});

export type UpdateStoryRequest = z.infer<typeof UpdateStorySchema>;

// Supabase Database types
export type Tables = {
  books: Book;
};
