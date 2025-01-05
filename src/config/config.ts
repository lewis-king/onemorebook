export const config = {
    aws: {
        region: process.env.AWS_REGION || 'us-east-1',
        dynamoTable: process.env.DYNAMO_TABLE || 'children-books',
    },
    llm: {
        model: process.env.LLM_MODEL || 'gpt-4o',
        temperature: 0.7,
    },
};