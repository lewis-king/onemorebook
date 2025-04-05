import { APIGatewayProxyEvent, APIGatewayProxyResult } from 'aws-lambda';
import { BookStorageService } from '../services/bookStorage';

export const handler = async (
    event: APIGatewayProxyEvent
): Promise<APIGatewayProxyResult> => {
    try {
        const sortBy = (event.queryStringParameters?.sortBy || 'stars') as 'stars' | 'date';
        const order = (event.queryStringParameters?.order || 'desc') as 'asc' | 'desc';
        const limit = event.queryStringParameters?.limit
            ? parseInt(event.queryStringParameters.limit, 10)
            : 10;

        // Validate parameters
        if (!['stars', 'date'].includes(sortBy)) {
            return {
                statusCode: 400,
                body: JSON.stringify({ error: 'sortBy must be either "stars" or "date"' }),
            };
        }

        if (!['asc', 'desc'].includes(order)) {
            return {
                statusCode: 400,
                body: JSON.stringify({ error: 'order must be either "asc" or "desc"' }),
            };
        }

        const storage = new BookStorageService();
        const books = await storage.listBooks({ sortBy, order, limit });

        return {
            statusCode: 200,
            body: JSON.stringify(books),
        };
    } catch (error) {
        console.error('Error listing books:', error);
        return {
            statusCode: 500,
            body: JSON.stringify({ error: 'Internal server error' }),
        };
    }
};