import { createClient } from '@supabase/supabase-js';
import dotenv from 'dotenv';
import path from 'path';

// Load environment variables from .env file
dotenv.config({ path: path.resolve(__dirname, '../../.env') });

// Initialize Supabase client
const supabaseUrl = process.env.SUPABASE_URL || '';
const supabaseKey = process.env.SUPABASE_ANON_KEY || '';

if (!supabaseUrl || !supabaseKey) {
  console.error('Missing Supabase credentials. Please check your .env file.');
  process.exit(1);
}

const supabase = createClient(supabaseUrl, supabaseKey);

async function initializeSupabase() {
  console.log('Initializing Supabase tables and storage...');

  // Create books table using SQL via RPC
  try {
    // This needs to be run in the Supabase SQL editor
    console.log(`
      -- Run this SQL in your Supabase SQL Editor:
      
      -- Create books table
      CREATE TABLE IF NOT EXISTS books (
        id UUID PRIMARY KEY,
        title TEXT NOT NULL,
        content JSONB NOT NULL,
        age_range TEXT NOT NULL,
        theme TEXT NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
      );

      -- Add RLS policies
      ALTER TABLE books ENABLE ROW LEVEL SECURITY;
      
      -- Create policy to allow authenticated users to select their own books
      CREATE POLICY "Users can view their own books" 
        ON books FOR SELECT 
        USING (auth.uid() = created_by);
        
      -- Create policy to allow authenticated users to insert books
      CREATE POLICY "Users can insert their own books" 
        ON books FOR INSERT 
        WITH CHECK (auth.uid() = created_by);
        
      -- Add a created_by column to track ownership
      ALTER TABLE books ADD COLUMN IF NOT EXISTS created_by UUID REFERENCES auth.users NOT NULL;
    `);

    // Create storage bucket for book images
    const { data: bucketData, error: bucketError } = await supabase
      .storage
      .createBucket('book-imgs', {
        public: true, // Images will be publicly accessible
        fileSizeLimit: 5242880, // 5MB limit for images
      });

    if (bucketError) {
      console.error('Error creating storage bucket:', bucketError.message);
    } else {
      console.log('Storage bucket "book-images" created successfully');
    }

    console.log('Supabase initialization complete. Please run the SQL commands in your Supabase dashboard SQL editor.');
  } catch (error) {
    console.error('Error during Supabase initialization:', error);
  }
}

initializeSupabase();
