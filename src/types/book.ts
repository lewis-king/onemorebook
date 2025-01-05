export interface Book {
    id: string;
    partitionKey: string;  // This will always be 'BOOK'
    stars: number;
    title: string;
    content: string;
    coverImage: {
        url: string;
        platformUrl: string;
        prompt: string;
    };
    createdAt: string;
    metadata: {
        ageRange: string;
        theme: string;
        characters: string[];
    };
}