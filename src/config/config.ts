export const config = {
    aws: {
        region: process.env.AWS_REGION || 'eu-west-2',
        dynamoTable: process.env.DYNAMO_TABLE || 'children-books',
        s3Bucket: process.env.S3_BUCKET || 'children-books-imgs',
    },
    llm: {
        model: process.env.LLM_MODEL || 'gpt-4o',
        temperature: 0.7,
    },
};