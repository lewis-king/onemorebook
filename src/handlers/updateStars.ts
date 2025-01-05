import { APIGatewayProxyEvent, APIGatewayProxyResult } from 'aws-lambda';
import { BookStorageService } from '../services/bookStorage';

export const handler = async (
    event: APIGatewayProxyEvent
): Promise<APIGatewayProxyResult> => {
    try {
        const bookId = event.pathParameters?.id;
        const body = JSON.parse(event.body || '{}');
        const { stars } = body;

        console.log('Updating stars for book:', { bookId, stars }); // Add logging

        if (!bookId || typeof stars !== 'number') {
            return {
                statusCode: 400,
                body: JSON.stringify({
                    error: 'Book ID and stars count are required',
                    receivedId: bookId,
                    receivedStars: stars,
                    receivedType: typeof stars
                }),
            };
        }

        const storage = new BookStorageService();
        const updatedBook = await storage.updateStars(bookId, stars);

        if (!updatedBook) {
            return {
                statusCode: 404,
                body: JSON.stringify({ error: 'Book not found' }),
            };
        }

        return {
            statusCode: 200,
            body: JSON.stringify(updatedBook),
            headers: {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
            },
        };
    } catch (error) {
        console.error('Error updating book stars:', error);
        return {
            statusCode: 500,
            body: JSON.stringify({ error: 'Internal server error', details: (error as Error).message }),
        };
    }
};