import { Book, CreateBookParams, UploadStoryParams, UpdateStoryParams } from '../types/book';
import { API_BASE_URL } from '../config';

async function readResponse<T>(response: Response): Promise<T> {
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(typeof data?.error === 'string' ? data.error : 'The library is unavailable. Please try again.');
  if (data === null) throw new Error('The library returned an unreadable response. Please try again.');
  return data as T;
}

export const bookService = {
  async listBooks({ limit = 9, offset = 0, sortBy = 'stars', order = 'desc' } = {}): Promise<Book[]> {
    const params = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
      sortBy,
      order,
    });
    const response = await fetch(`${API_BASE_URL}/books?${params.toString()}`);
    const data = await readResponse<Book[]>(response);
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
    return readResponse<Book[]>(response);
  },

  async getBook(id: string): Promise<Book> {
    const response = await fetch(`${API_BASE_URL}/books/${id}`);
    return readResponse<Book>(response);
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

  async updateStars(id: string, _currentStars?: number): Promise<Pick<Book, 'id' | 'stars'>> {
    const response = await fetch(`${API_BASE_URL}/books/${id}/stars`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: '{}',
    });
    return readResponse<Pick<Book, 'id' | 'stars'>>(response);
  },

  async uploadStory(params: UploadStoryParams): Promise<{ bookId: string; book: Book }> {
    const response = await fetch(`${API_BASE_URL}/books/upload`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(params),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || 'Upload failed');
    }
    return response.json();
  },

  async updateStory(bookId: string, params: UpdateStoryParams): Promise<{ bookId: string; book: Book }> {
    const response = await fetch(`${API_BASE_URL}/books/${bookId}/upload`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(params),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || 'Update failed');
    }
    return response.json();
  },
};
