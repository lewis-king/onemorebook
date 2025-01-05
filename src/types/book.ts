export interface Book {
    id: string;
    stars: number;
    title: string;
    content: string;
    createdAt: string;
    metadata: {
        ageRange: string;
        theme: string;
        characters: string[];
    };
}