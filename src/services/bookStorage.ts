import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient, PutCommand, GetCommand, QueryCommand, UpdateCommand } from "@aws-sdk/lib-dynamodb";
import { v4 as uuidv4 } from 'uuid';
import { Book } from '../types/book';
import {config} from "../config/config";

export type SortOrder = 'asc' | 'desc';

export interface ListBooksOptions {
    sortBy: 'stars' | 'date';
    order: SortOrder;
    limit?: number;
}

export class BookStorageService {
    private docClient: DynamoDBDocumentClient;

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

    async storeBook(bookData: Omit<Book, 'id' | 'createdAt' | 'stars'>): Promise<Book> {
        const now = new Date().toISOString();
        const book: {
            dummy: string;
            createdAt: string;
            metadata: { ageRange: string; theme: string; characters: string[] };
            id: string;
            stars: number;
            title: string;
            content: string
        } = {
            ...bookData,
            id: uuidv4(),
            stars: 0,
            createdAt: now,
            dummy: 'BOOK', // Required for GSIs
        };

        await this.docClient.send(new PutCommand({
            TableName: config.aws.dynamoTable,
            Item: book,
        }));

        return book;
    }

    async listBooks(options: ListBooksOptions): Promise<Book[]> {
        const { sortBy, order, limit = 10 } = options;
        const indexName = sortBy === 'stars' ? 'StarsSortIndex' : 'DateSortIndex';

        const response = await this.docClient.send(new QueryCommand({
            TableName: config.aws.dynamoTable,
            IndexName: indexName,
            KeyConditionExpression: 'dummy = :dummy',
            ExpressionAttributeValues: {
                ':dummy': 'BOOK',
            },
            ScanIndexForward: order === 'asc', // false for descending order
            Limit: limit,
        }));

        return (response.Items || []) as Book[];
    }

    async getBook(id: string): Promise<Book | null> {
        const response = await this.docClient.send(new GetCommand({
            TableName: config.aws.dynamoTable,
            Key: { id },
        }));

        return response.Item as Book || null;
    }

    async updateStars(id: string, stars: number): Promise<Book | null> {
        const response = await this.docClient.send(new UpdateCommand({
            TableName: config.aws.dynamoTable,
            Key: { id },
            UpdateExpression: 'set stars = :stars',
            ExpressionAttributeValues: {
                ':stars': stars,
            },
            ReturnValues: 'ALL_NEW',
        }));

        return response.Attributes as Book || null;
    }

    async getTopBooks(limit: number = 10): Promise<Book[]> {
        const response = await this.docClient.send(new QueryCommand({
            TableName: config.aws.dynamoTable,
            IndexName: 'StarsSortIndex',
            KeyConditionExpression: 'dummy = :dummy',
            ExpressionAttributeValues: {
                ':dummy': 'BOOK', // We'll use this as a partition key in the GSI
            },
            ScanIndexForward: false, // This will sort in descending order
            Limit: limit,
        }));

        return (response.Items || []) as Book[];
    }
}