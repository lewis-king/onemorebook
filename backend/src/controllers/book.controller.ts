import { Request, Response } from 'express';
import { v4 as uuidv4 } from 'uuid';
import { GenerateBookSchema } from '../types';
import supabaseService from '../services/supabase.service';
import bookGeneratorService from '../services/book-generator.service';

export async function generateBook(req: Request, res: Response) {
  try {
    // Validate request
    const validatedData = GenerateBookSchema.parse(req.body);
    
    // Create a unique ID for the book
    const bookId = uuidv4();
    
    // Generate book content using LLM
    const bookContent = await bookGeneratorService.generateBook(validatedData);
    
    // Store book data in Supabase
    const book = await supabaseService.createBook({
      id: bookId,
      title: validatedData.title,
      content: bookContent,
      age_range: validatedData.ageRange,
      theme: validatedData.theme,
      created_by: req.user?.id, // This will be available when auth is implemented
    });
    
    // Return the generated book details
    res.status(201).json({
      message: 'Book generated successfully',
      bookId,
      book: bookContent
    });
  } catch (error: any) {
    console.error('Error generating book:', error);
    
    if (error.name === 'ZodError') {
      return res.status(400).json({ error: error.errors });
    }
    
    res.status(500).json({ error: 'An unexpected error occurred' });
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
    
    // Make sure the user owns the book (when auth is implemented)
    if (req.user?.id && existingBook.created_by !== req.user.id) {
      return res.status(403).json({ error: 'Forbidden' });
    }
    
    // Update the book
    const updatedBook = await supabaseService.updateBook(id, req.body);
    res.status(200).json(updatedBook);
  } catch (error) {
    console.error('Error updating book:', error);
    res.status(500).json({ error: 'An unexpected error occurred' });
  }
}

export async function deleteBook(req: Request, res: Response) {
  const { id } = req.params;
  
  try {
    // Get the existing book to make sure it exists
    const existingBook = await supabaseService.getBookById(id);
    
    if (!existingBook) {
      return res.status(404).json({ error: 'Book not found' });
    }
    
    // Make sure the user owns the book (when auth is implemented)
    if (req.user?.id && existingBook.created_by !== req.user.id) {
      return res.status(403).json({ error: 'Forbidden' });
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
