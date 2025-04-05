export interface Book {
    id: string;
    stars: number;
    title: string;
    content: string;
    createdAt: string;
    coverImage: {
        url: string;
    };
    metadata: {
        ageRange: string;
        theme: string;
        characters: string[];
    };
    pageImages: {
        url: string
    }[]
}

export interface CreateBookParams {
    characters: string[];
    theme: string;
    ageRange: string;
}