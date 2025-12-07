import express, { Request, Response, NextFunction } from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import bookRoutes from './routes/book.routes';
import { authMiddleware } from './middleware/auth.middleware';

// Load environment variables
dotenv.config();

// Initialize Express app
const app = express();
const port = process.env.PORT || 3000;

// Middleware
app.use(cors({
  origin: (origin, callback) => {
    // Allow requests with no origin (like mobile apps or curl requests)
    if (!origin) return callback(null, true);
    const allowedOrigins = [
      'https://onemorebook.ai',
      'http://localhost:3000',
      'http://127.0.0.1:3000',
    ];
    // Allow localhost in development, always allow production domain
    if (
      allowedOrigins.includes(origin) ||
      (process.env.NODE_ENV !== 'production' && origin.startsWith('http://localhost'))
    ) {
      return callback(null, true);
    }
    return callback(new Error('Not allowed by CORS'));
  },
  credentials: true, // if using cookies or authentication
}));
app.use(express.json({ limit: '50mb' }));
app.use(authMiddleware);

// Health check endpoint
app.get('/api/health', (req: Request, res: Response) => {
  res.status(200).json({ status: 'ok', message: 'OneMoreBook Backend is running' });
});

// API Routes
app.use('/api', bookRoutes);

// Error handling middleware
app.use((err: Error, req: Request, res: Response, next: NextFunction) => {
  console.error('Unhandled error:', err);
  res.status(500).json({ 
    error: 'An unexpected error occurred',
    message: process.env.NODE_ENV === 'development' ? err.message : undefined
  });
});

// Start server
app.listen(port, () => {
  console.log(`Server running at http://localhost:${port}`);
  console.log('Environment:', process.env.NODE_ENV || 'development');
});
