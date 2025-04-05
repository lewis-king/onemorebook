import { APIGatewayProxyEvent, APIGatewayProxyResult } from 'aws-lambda';
import { BookGeneratorService } from '../services/bookGenerator';
import { BookStorageService } from '../services/bookStorage';

export const handler = async (
    event: APIGatewayProxyEvent
): Promise<APIGatewayProxyResult> => {
    try {
        const body = JSON.parse(event.body || '{}');
        const { prompt } = body;

        if (!prompt) {
            return {
                statusCode: 400,
                body: JSON.stringify({ error: 'Prompt is required' }),
            };
        }

        const generator = new BookGeneratorService();
        const storage = new BookStorageService();

        const bookData = await generator.generateBook(prompt);
        const book = await storage.storeBook(bookData);

        return {
            statusCode: 200,
            body: JSON.stringify(book),
        };
    } catch (error) {
        console.error('Error generating book:', error);
        return {
            statusCode: 500,
            body: JSON.stringify({ error: 'Internal server error' }),
        };
    }
};