import { createClient, SupabaseClient } from '@supabase/supabase-js';
import dotenv from 'dotenv';
import { Book, Tables } from '../types';

// Load environment variables
dotenv.config();

class SupabaseService {
  private client: SupabaseClient;
  private static instance: SupabaseService;

  private constructor() {
    const supabaseUrl = process.env.SUPABASE_URL || '';
    const supabaseKey = process.env.SUPABASE_ANON_KEY || '';
    
    if (!supabaseUrl || !supabaseKey) {
      throw new Error('Missing Supabase credentials. Please check your .env file.');
    }
    
    this.client = createClient<Tables>(supabaseUrl, supabaseKey);
  }

  public static getInstance(): SupabaseService {
    if (!SupabaseService.instance) {
      SupabaseService.instance = new SupabaseService();
    }
    return SupabaseService.instance;
  }

  // Books table operations
  async createBook(book: Book): Promise<Book | null> {
    const { data, error } = await this.client
      .from('books')
      .insert([book])
      .select()
      .single();
      
    if (error) {
      console.error('Error creating book:', error);
      throw error;
    }
    
    return data;
  }

  async getBookById(id: string): Promise<Book | null> {
    const { data, error } = await this.client
      .from('books')
      .select('*')
      .eq('id', id)
      .single();
      
    if (error) {
      console.error('Error fetching book:', error);
      throw error;
    }
    
    return data;
  }

  async getUserBooks(userId: string): Promise<Book[]> {
    const { data, error } = await this.client
      .from('books')
      .select('*')
      .eq('created_by', userId)
      .order('created_at', { ascending: false });
      
    if (error) {
      console.error('Error fetching user books:', error);
      throw error;
    }
    
    return data || [];
  }

  async updateBook(id: string, updates: Partial<Omit<Book, 'id'>>): Promise<Book | null> {
    const { data, error } = await this.client
      .from('books')
      .update(updates)
      .eq('id', id)
      .select()
      .single();
      
    if (error) {
      console.error('Error updating book:', error);
      throw error;
    }
    
    return data;
  }

  async deleteBook(id: string): Promise<void> {
    const { error } = await this.client
      .from('books')
      .delete()
      .eq('id', id);
      
    if (error) {
      console.error('Error deleting book:', error);
      throw error;
    }
  }

  // File storage operations
  async uploadBookImage(bookId: string, pageNumber: number, file: Uint8Array, fileType: string): Promise<string> {
    const fileName = `${bookId}/page_${pageNumber}.${fileType.split('/')[1] || 'png'}`;
    
    const { data, error } = await this.client
      .storage
      .from('book-images')
      .upload(fileName, file, {
        contentType: fileType,
        upsert: true
      });
      
    if (error) {
      console.error('Error uploading image:', error);
      throw error;
    }
    
    // Get public URL for the image
    const { data: { publicUrl } } = this.client
      .storage
      .from('book-images')
      .getPublicUrl(fileName);
      
    return publicUrl;
  }

  async deleteBookImages(bookId: string): Promise<void> {
    const { data, error } = await this.client
      .storage
      .from('book-images')
      .list(bookId);
      
    if (error) {
      console.error('Error listing book images:', error);
      throw error;
    }
    
    if (data && data.length > 0) {
      const filesToDelete = data.map(file => `${bookId}/${file.name}`);
      
      const { error: deleteError } = await this.client
        .storage
        .from('book-images')
        .remove(filesToDelete);
        
      if (deleteError) {
        console.error('Error deleting book images:', deleteError);
        throw deleteError;
      }
    }
  }
}

export default SupabaseService.getInstance();
