import { APIGatewayProxyEvent, APIGatewayProxyResult } from 'aws-lambda';
import { BookStorageService } from '../services/bookStorage';

export const handler = async (
    event: APIGatewayProxyEvent
): Promise<APIGatewayProxyResult> => {
    try {
        const bookId = event.pathParameters?.id;
        const body = JSON.parse(event.body || '{}');
        const { stars } = body;

        if (!bookId || typeof stars !== 'number') {
            return {
                statusCode: 400,
                body: JSON.stringify({ error: 'Book ID and stars count are required' }),
            };
        }

        const storage = new BookStorageService();
        const book = await storage.updateStars(bookId, stars);

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
        console.error('Error updating book stars:', error);
        return {
            statusCode: 500,
            body: JSON.stringify({ error: 'Internal server error' }),
        };
    }
};