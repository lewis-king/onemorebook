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
  title: string;
  pages: BookPage[];
  metadata: {
    ageRange: string;
    theme: string;
    additionalInfo: string;
    createdAt: string;
  };
}

// Book database record
export interface Book {
  id: string;
  title: string;
  content: BookContent;
  age_range: string;
  theme: string;
  created_at?: string;
  updated_at?: string;
  created_by?: string;
}

// Zod schema for book generation request validation
export const GenerateBookSchema = z.object({
  title: z.string().min(1, 'Title is required'),
  ageRange: z.string().min(1, 'Age range is required'),
  mainCharacter: z.string().min(1, 'Main character is required'),
  theme: z.string().min(1, 'Theme is required'),
  additionalInfo: z.string().optional(),
});

export type GenerateBookRequest = z.infer<typeof GenerateBookSchema>;

// Supabase Database types
export type Tables = {
  books: Book;
};
