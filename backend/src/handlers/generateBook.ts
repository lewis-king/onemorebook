// This file is now deprecated
// The functionality has been migrated to the Express controller in:
// ../controllers/book.controller.ts - generateBook function
//
// This file is kept for reference only and can be safely deleted

import { Request, Response } from 'express';
import { generateBook } from '../controllers/book.controller';

// Export the controller function for compatibility
export { generateBook };