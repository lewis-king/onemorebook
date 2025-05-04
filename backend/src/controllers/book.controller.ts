import { Request, Response } from 'express';
import { GenerateBookSchema } from '../types';
import supabaseService from '../services/supabase.service';
import bookGeneratorService from '../services/bookGenerator';

export async function generateBook(req: Request, res: Response) {
  try {
    // Accept raw body, validate only after autofill
    let validatedData = { ...req.body };

    // If characters or storyPrompt missing/empty, autofill
    if (!validatedData.ageRange) {
      return res.status(400).json({ error: 'ageRange is required' });
    }
    
    if (!validatedData.characters || validatedData.characters.length === 0 || !validatedData.storyPrompt) {
      const autofill = await bookGeneratorService.autofillBookFields({
        ageRange: validatedData.ageRange,
        numOfPages: validatedData.numOfPages
      });
      if (!autofill.characters || autofill.characters.length === 0 || !autofill.storyPrompt) {
        return res.status(500).json({ error: 'AI autofill failed to generate story details. Please try again.' });
      }
      validatedData = {
        ...validatedData,
        characters: autofill.characters,
        storyPrompt: autofill.storyPrompt,
      };
    }
    // Assign required fields
    validatedData = {
      ...validatedData,
      ageRange: validatedData.ageRange,
      characters: validatedData.characters || [],
      storyPrompt: validatedData.storyPrompt || '',
    };
    // Now validate as full schema (enforces required fields)
    const parsedData = GenerateBookSchema.parse(validatedData);
    // Step 1: Generate book content (pages, image prompts, no images yet)
    const bookContent = await bookGeneratorService.generateBookContent(parsedData);

    // Step 2: Insert book record as soon as we need the ID (status: 'pending')
    let insertedBook;
    try {
      insertedBook = await supabaseService.createBook({
        title: bookContent.metadata.title || 'Untitled',
        book_summary: bookContent.metadata.bookSummary,
        cover_image_prompt: bookContent.metadata.coverImagePrompt,
        age_range: parsedData.ageRange,
        characters: parsedData.characters,
        story_prompt: parsedData.storyPrompt,
        content: bookContent,
        status: 'pending',
      });
      if (!insertedBook || !insertedBook.id) {
        throw new Error('Failed to create book in database');
      }
    } catch (dbError) {
      console.error('Error during initial DB insert:', dbError);
      return res.status(500).json({ error: 'Book generation failed at initial saving step. Please try again.' });
    }
    const bookId = insertedBook.id;

    // Step 3: Generate/upload images using the book ID
    let bookContentWithImages;
    try {
      bookContentWithImages = await bookGeneratorService.generateAndAttachImages(bookId, bookContent);
    } catch (imageGenError) {
      // If image generation fails, mark status as 'failed'
      await supabaseService.updateBook(bookId, { status: 'failed' });
      console.error('Error during image generation:', imageGenError);
      return res.status(500).json({ error: 'Book generation failed during image creation. Please try again.' });
    }

    // Step 4: Update book record to 'complete' and save final content
    try {
      await supabaseService.updateBook(bookId, {
        content: bookContentWithImages,
        status: 'complete',
      });
    } catch (dbError) {
      // If DB update fails, mark as 'failed'
      await supabaseService.updateBook(bookId, { status: 'failed' });
      console.error('Error during DB update:', dbError);
      return res.status(500).json({ error: 'Book generation failed at saving step. Please try again.' });
    }

    // Step 5: Return the generated book details
    res.status(201).json({
      message: 'Book generated successfully',
      bookId,
      book: bookContentWithImages
    });
  } catch (error: any) {
    console.error('Error generating book:', error);
    if (error.name === 'ZodError') {
      return res.status(400).json({ error: error.errors });
    }
    res.status(500).json({ error: 'Book generation failed. Please try again.' });
  }
}

export async function getBookById(req: Request, res: Response) {
  const { id } = req.params;
  
  try {
    const book = await supabaseService.getBookById(id);
    
    if (!book) {
      return res.status(404).json({ error: 'Book not found' });
    }
    
    res.status(200).json(book);
  } catch (error) {
    console.error('Error retrieving book:', error);
    res.status(500).json({ error: 'An unexpected error occurred' });
  }
}

export async function listBooks(req: Request, res: Response) {
  try {
    const sortBy = (req.query.sortBy as string || 'stars') as 'stars' | 'date';
    const order = (req.query.order as string || 'desc') as 'asc' | 'desc';
    const limit = req.query.limit ? parseInt(req.query.limit as string, 10) : 9;
    const offset = req.query.offset ? parseInt(req.query.offset as string, 10) : 0;

    // Validate parameters
    if (!['stars', 'date'].includes(sortBy)) {
      return res.status(400).json({ error: 'sortBy must be either "stars" or "date"' });
    }

    if (!['asc', 'desc'].includes(order)) {
      return res.status(400).json({ error: 'order must be either "asc" or "desc"' });
    }

    const books = await supabaseService.listBooks({ sortBy, order, limit, offset });
    // Transform each book to the new format
    const transformedBooks = books.map((book: any) => ({
      id: book.id,
      title: book.title,
      book_summary: book.book_summary,
      cover_image_prompt: book.cover_image_prompt,
      content: book.content,
      age_range: book.content?.metadata?.ageRange || book.age_range,
      story_prompt: book.content?.metadata?.storyPrompt || book.story_prompt,
      characters: book.content?.metadata?.characters || book.characters,
      created_at: book.created_at,
      updated_at: book.updated_at,
      stars: book.stars || 0
    }));
    res.status(200).json(transformedBooks);
  } catch (error) {
    console.error('Error listing books:', error);
    res.status(500).json({ error: 'An unexpected error occurred' });
  }
}

export async function updateBookStars(req: Request, res: Response) {
  try {
    const { id } = req.params;
    const { stars } = req.body;

    console.log('Updating stars for book:', { id, stars });

    if (!id || typeof stars !== 'number') {
      return res.status(400).json({
        error: 'Book ID and stars count are required',
        receivedId: id,
        receivedStars: stars,
        receivedType: typeof stars
      });
    }

    const updatedBook = await supabaseService.updateBookStars(id, stars);

    if (!updatedBook) {
      return res.status(404).json({ error: 'Book not found' });
    }

    res.status(200).json(updatedBook);
  } catch (error) {
    console.error('Error updating book stars:', error);
    res.status(500).json({ 
      error: 'An unexpected error occurred', 
      details: (error as Error).message 
    });
  }
}

export async function getUserBooks(req: Request, res: Response) {
  try {
    if (!req.user?.id) {
      return res.status(401).json({ error: 'Unauthorized' });
    }
    
    const books = await supabaseService.getUserBooks(req.user.id);
    res.status(200).json(books);
  } catch (error) {
    console.error('Error retrieving user books:', error);
    res.status(500).json({ error: 'An unexpected error occurred' });
  }
}

export async function updateBook(req: Request, res: Response) {
  const { id } = req.params;
  
  try {
    // Get the existing book to make sure it exists
    const existingBook = await supabaseService.getBookById(id);
    
    if (!existingBook) {
      return res.status(404).json({ error: 'Book not found' });
    }

    // Update the book
    const updatedBook = await supabaseService.updateBook(id, req.body);
    res.status(200).json(updatedBook);
  } catch (error) {
    console.error('Error updating book:', error);
    res.status(500).json({ error: 'An unexpected error occurred' });
  }
}

// Commenting out deleteBook for now
/*
export async function deleteBook(req: Request, res: Response) {
  const { id } = req.params;
  
  try {
    // Get the existing book to make sure it exists
    const existingBook = await supabaseService.getBookById(id);
    
    if (!existingBook) {
      return res.status(404).json({ error: 'Book not found' });
    }

    // Delete book images
    await supabaseService.deleteBookImages(id);
    
    // Delete the book
    await supabaseService.deleteBook(id);
    
    res.status(204).send();
  } catch (error) {
    console.error('Error deleting book:', error);
    res.status(500).json({ error: 'An unexpected error occurred' });
  }
}
*/
