import { APIGatewayProxyEvent, APIGatewayProxyResult } from 'aws-lambda';
import { BookStorageService } from '../services/bookStorage';

export const handler = async (
    event: APIGatewayProxyEvent
): Promise<APIGatewayProxyResult> => {
    try {
        const bookId = event.pathParameters?.id;

        if (!bookId) {
            return {
                statusCode: 400,
                body: JSON.stringify({ error: 'Book ID is required' }),
            };
        }

        const storage = new BookStorageService();
        const book = await storage.getBook(bookId);

        if (!book) {
            return {
                statusCode: 404,
                body: JSON.stringify({ error: 'Book not found' }),
            };
        }

        return {
            statusCode: 200,
            body: JSON.stringify(book),
        };
    } catch (error) {
        console.error('Error retrieving book:', error);
        return {
            statusCode: 500,
            body: JSON.stringify({ error: 'Internal server error' }),
        };
    }
};