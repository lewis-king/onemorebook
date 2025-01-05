// src/services/imageStorage.ts
import { S3Client, PutObjectCommand } from "@aws-sdk/client-s3";
import { fromIni } from "@aws-sdk/credential-providers";
import fetch from 'node-fetch';
import { config } from '../config/config';

export class ImageStorageService {
    private s3Client: S3Client;

    constructor() {
        this.s3Client = new S3Client({
            region: config.aws.region,
            credentials: fromIni({
                profile: process.env.AWS_PROFILE || 'default'
            })
        });
    }

    async uploadImage(imageUrl: string, bookId: string): Promise<string> {
        try {
            const response = await fetch(imageUrl);
            const imageBuffer = await response.buffer();  // Use buffer() instead of arrayBuffer() for node-fetch v2

            const key = `covers/${bookId}/cover.png`;

            await this.s3Client.send(new PutObjectCommand({
                Bucket: config.aws.s3Bucket,
                Key: key,
                Body: imageBuffer,  // Can use the buffer directly
                ContentType: 'image/png'
            }));

            return `https://${config.aws.s3Bucket}.s3.${config.aws.region}.amazonaws.com/${key}`;
        } catch (error) {
            console.error('Error uploading image to S3:', error);
            throw new Error('Failed to upload image to S3');
        }
    }
}