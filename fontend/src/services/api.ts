import { Book, CreateBookParams } from '../types/book';

//const API_BASE_URL = 'http://localhost:3000/dev'; // local
const API_BASE_URL = 'http://localhost:3000/dev';

export const bookService = {
  async listBooks(): Promise<Book[]> {
    const response = await fetch(`${API_BASE_URL}/books`);
    return response.json();
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
      body: JSON.stringify(params),
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