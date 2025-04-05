import { Router } from 'express';
import * as bookController from '../controllers/book.controller';

const router = Router();

// Book routes
router.post('/generate-book', bookController.generateBook);
router.get('/books/:id', bookController.getBookById);
router.get('/user/books', bookController.getUserBooks);
router.put('/books/:id', bookController.updateBook);
router.delete('/books/:id', bookController.deleteBook);

export default router;
