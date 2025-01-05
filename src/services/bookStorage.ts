import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import {DynamoDBDocumentClient, PutCommand, GetCommand, QueryCommand, UpdateCommand} from "@aws-sdk/lib-dynamodb";
import { v4 as uuidv4 } from 'uuid';
import { Book } from '../types/book';
import { config } from '../config/config';

export interface ListBooksOptions {
    sortBy: 'stars' | 'date';
    order: 'asc' | 'desc';
    limit?: number;
}

export class BookStorageService {
    private docClient: DynamoDBDocumentClient;
    private readonly PARTITION_KEY = 'BOOK';

    constructor() {
        const clientConfig = {
            region: config.aws.region,
            ...(process.env.IS_OFFLINE === 'true' && {
                endpoint: 'http://localhost:8000',
                credentials: {
                    accessKeyId: 'local',
                    secretAccessKey: 'local',
                },
            }),
        };

        const client = new DynamoDBClient(clientConfig);
        this.docClient = DynamoDBDocumentClient.from(client);
    }

    async storeBook(bookData: Omit<Book, 'id' | 'createdAt' | 'stars' | 'partitionKey'>): Promise<Book> {
        const book: Book = {
            ...bookData,
            id: uuidv4(),
            partitionKey: this.PARTITION_KEY,
            stars: 0,
            createdAt: new Date().toISOString(),
        };

        await this.docClient.send(new PutCommand({
            TableName: config.aws.dynamoTable,
            Item: book,
        }));

        return book;
    }

    async getBook(id: string): Promise<Book | null> {
        const response = await this.docClient.send(new GetCommand({
            TableName: config.aws.dynamoTable,
            Key: {
                partitionKey: this.PARTITION_KEY,
                id
            },
        }));

        return response.Item as Book || null;
    }

    async listBooks(options: ListBooksOptions): Promise<Book[]> {
        const { sortBy, order, limit = 10 } = options;
        const indexName = sortBy === 'stars' ? 'StarsSortIndex' : 'DateSortIndex';

        const response = await this.docClient.send(new QueryCommand({
            TableName: config.aws.dynamoTable,
            IndexName: indexName,
            KeyConditionExpression: 'partitionKey = :pk',
            ExpressionAttributeValues: {
                ':pk': this.PARTITION_KEY,
            },
            ScanIndexForward: order === 'asc',
            Limit: limit,
        }));

        return (response.Items || []) as Book[];
    }

    async updateStars(id: string, stars: number): Promise<Book | null> {
        const response = await this.docClient.send(new UpdateCommand({
            TableName: config.aws.dynamoTable,
            Key: {
                partitionKey: this.PARTITION_KEY,  // This is required
                id
            },
            UpdateExpression: 'set stars = :stars',
            ExpressionAttributeValues: {
                ':stars': stars,
            },
            ReturnValues: 'ALL_NEW',
        }));

        return response.Attributes as Book || null;
    }
}