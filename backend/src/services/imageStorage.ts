// src/services/imageStorage.ts
import { createClient, SupabaseClient } from '@supabase/supabase-js';
import fetch from 'node-fetch';
import { config } from '../config/config';

export class ImageStorageService {
    private client: SupabaseClient;

    constructor() {
        const { url, anonKey } = config.supabase;
        
        if (!url || !anonKey) {
            throw new Error('Missing Supabase credentials. Please check your environment variables.');
        }
        
        this.client = createClient(url, anonKey);
    }

    async uploadImage(imageUrl: string, bookId: string): Promise<string> {
        try {
            const response = await fetch(imageUrl);
            const imageBuffer = await response.buffer();  // Use buffer() instead of arrayBuffer() for node-fetch v2

            const filePath = `${bookId}/cover.png`;
            const bucketName = config.supabase.storageCoversBucket;

            const { data, error } = await this.client
                .storage
                .from(bucketName)
                .upload(filePath, imageBuffer, {
                    contentType: 'image/png',
                    upsert: true
                });

            if (error) {
                console.error('Error uploading image to Supabase:', error);
                throw error;
            }

            // Get the public URL for the uploaded image
            const { data: urlData } = this.client
                .storage
                .from(bucketName)
                .getPublicUrl(filePath);

            return urlData.publicUrl;
        } catch (error) {
            console.error('Error uploading image:', error);
            throw error;
        }
    }

    async deleteImage(bookId: string): Promise<void> {
        try {
            const filePath = `${bookId}/cover.png`;
            const bucketName = config.supabase.storageCoversBucket;

            const { error } = await this.client
                .storage
                .from(bucketName)
                .remove([filePath]);

            if (error) {
                console.error('Error deleting image from Supabase:', error);
                throw error;
            }
        } catch (error) {
            console.error('Error deleting image:', error);
            throw error;
        }
    }
}