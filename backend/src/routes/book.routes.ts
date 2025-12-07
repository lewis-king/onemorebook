import { Router } from 'express';
import * as bookController from '../controllers/book.controller';

const router: Router = Router();

// Book routes
router.post('/books', bookController.generateBook);
router.post('/books/upload', bookController.uploadStory);
router.get('/books/:id', bookController.getBookById);
router.get('/books', bookController.listBooks);
router.put('/books/:id/stars', bookController.updateBookStars);
router.put('/books/:id/upload', bookController.updateStory);
router.get('/user/books', bookController.getUserBooks);
router.put('/books/:id', bookController.updateBook);
//router.delete('/books/:id', bookController.deleteBook);

export default router;
