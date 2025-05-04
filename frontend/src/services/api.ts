import { Book, CreateBookParams } from '../types/book';
import { API_BASE_URL } from '../config';

export const bookService = {
  async listBooks({ limit = 9, offset = 0, sortBy = 'stars', order = 'desc' } = {}): Promise<Book[]> {
    const params = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
      sortBy,
      order,
    });
    const response = await fetch(`${API_BASE_URL}/books?${params.toString()}`);
    const data = await response.json();
    // Optionally, ensure all fields are present and fallback if needed
    return data.map((book: any) => ({
      ...book,
      book_summary: book.book_summary || '',
      content: book.content || { id: '', pages: [], metadata: { title: '', ageRange: '', createdAt: '', characters: [], storyPrompt: '' } },
      age_range: book.age_range || '',
      story_prompt: book.story_prompt || '',
      characters: book.characters || [],
      created_at: book.created_at || '',
      updated_at: book.updated_at || '',
      stars: book.stars || 0
    }));
  },

  async getTopBooks(): Promise<Book[]> {
    const response = await fetch(`${API_BASE_URL}/books/top`);
    return response.json();
  },

  async getBook(id: string): Promise<Book> {
    const response = await fetch(`${API_BASE_URL}/books/${id}`);
    return response.json();
  },

  async createBook(params: CreateBookParams): Promise<Book> {
    const response = await fetch(`${API_BASE_URL}/books`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ ...params, theme: params.storyPrompt }),
    });
    return response.json();
  },

  async updateStars(id: string, currentStars: number): Promise<Book> {
    const response = await fetch(`${API_BASE_URL}/books/${id}/stars`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        id,
        stars: currentStars + 1
      }),
    });
    return response.json();
  },
};