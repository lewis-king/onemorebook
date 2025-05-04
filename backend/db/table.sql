-- Enable the uuid-ossp extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE books (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  title text NOT NULL,
  book_summary text,
  cover_image_prompt text,
  content jsonb, -- stores full BookContent including pages and image URLs
  age_range text NOT NULL,
  story_prompt text NOT NULL,
  characters jsonb NOT NULL, -- stores array of character names
  --user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
  updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()),
  stars integer DEFAULT 0,
  status text NOT NULL DEFAULT 'pending'
);

-- Allow uploads for authenticated users (including anon key) to the book-imgs bucket
create policy "Allow uploads for anon key"
on storage.objects
for insert
to authenticated, anon
with check (bucket_id = 'book-imgs');