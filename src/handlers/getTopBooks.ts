import { APIGatewayProxyEvent, APIGatewayProxyResult } from 'aws-lambda';
import { BookStorageService } from '../services/bookStorage';

export const handler = async (
    event: APIGatewayProxyEvent
): Promise<APIGatewayProxyResult> => {
    try {
        const limit = event.queryStringParameters?.limit
            ? parseInt(event.queryStringParameters.limit, 10)
            : 10;

        const storage = new BookStorageService();
        const books = await storage.getTopBooks(limit);

        return {
            statusCode: 200,
            body: JSON.stringify(books),
        };
    } catch (error) {
        console.error('Error retrieving top books:', error);
        return {
            statusCode: 500,
            body: JSON.stringify({ error: 'Internal server error' }),
        };
    }
};