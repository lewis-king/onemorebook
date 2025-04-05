import { createClient, SupabaseClient } from '@supabase/supabase-js';
import { v4 as uuidv4 } from 'uuid';
import { Book } from '../types/book';
import { config } from '../config/config';

export interface ListBooksOptions {
    sortBy: 'stars' | 'date';
    order: 'asc' | 'desc';
    limit?: number;
}

export class BookStorageService {
    private client: SupabaseClient;

    constructor() {
        const { url, anonKey } = config.supabase;
        
        if (!url || !anonKey) {
            throw new Error('Missing Supabase credentials. Please check your environment variables.');
        }
        
        this.client = createClient(url, anonKey);
    }

    async storeBook(bookData: Omit<Book, 'id' | 'createdAt' | 'stars'>): Promise<Book> {
        const book: Omit<Book, 'partitionKey'> = {
            ...bookData,
            id: uuidv4(),
            stars: 0,
            createdAt: new Date().toISOString(),
        };

        const { data, error } = await this.client
            .from('books')
            .insert([book])
            .select()
            .single();

        if (error) {
            console.error('Error storing book:', error);
            throw error;
        }

        return data as Book;
    }

    async getBook(id: string): Promise<Book | null> {
        const { data, error } = await this.client
            .from('books')
            .select('*')
            .eq('id', id)
            .single();

        if (error) {
            console.error('Error fetching book:', error);
            throw error;
        }

        return data as Book;
    }

    async listBooks(options: ListBooksOptions): Promise<Book[]> {
        const { sortBy, order, limit = 10 } = options;
        const column = sortBy === 'stars' ? 'stars' : 'created_at';

        const { data, error } = await this.client
            .from('books')
            .select('*')
            .order(column, { ascending: order === 'asc' })
            .limit(limit);

        if (error) {
            console.error('Error listing books:', error);
            throw error;
        }

        return data as Book[];
    }

    async updateStars(id: string, stars: number): Promise<Book | null> {
        const { data, error } = await this.client
            .from('books')
            .update({ stars })
            .eq('id', id)
            .select()
            .single();

        if (error) {
            console.error('Error updating stars:', error);
            throw error;
        }

        return data as Book;
    }
}