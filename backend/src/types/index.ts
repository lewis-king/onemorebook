import { z } from 'zod';

// Book page interface
export interface BookPage {
  pageNumber: number;
  text: string;
  imagePrompt: string;
  imageUrl?: string;
}

// Book content interface
export interface BookContent {
  id: string;
  pages: BookPage[];
  metadata: {
    title: string;
    bookSummary: string;
    coverImagePrompt: string;
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
  book_summary?: string;
  cover_image_prompt?: string;
  content: BookContent;
  age_range: string;
  story_prompt: string;
  characters: string[];
  created_at?: string;
  updated_at?: string;
}

// Zod schema for book generation request validation
export const GenerateBookSchema = z.object({
  characters: z.array(z.string()).min(1, 'At least one character is required'),
  storyPrompt: z.string().min(1, 'Story prompt is required'),
  ageRange: z.string().min(1, 'Age range is required'),
  numOfPages: z.number().int().min(3, 'Number of pages must be at least 3').optional(),
});

export type GenerateBookRequest = z.infer<typeof GenerateBookSchema>;

// Supabase Database types
export type Tables = {
  books: Book;
};
