export interface BookPage {
    text: string;
    pageNumber: number;
    imagePrompt: string;
    imageUrl?: string;
}

export interface BookContentMetadata {
    title: string;
    ageRange: string;
    createdAt: string;
    characters: string[];
    storyPrompt: string;
    theme?: string;
}

export interface BookContent {
    id: string;
    pages: BookPage[];
    metadata: BookContentMetadata;
}

export interface Book {
    id: string;
    title: string;
    book_summary: string;
    cover_image_prompt: string;
    content: BookContent;
    age_range: string;
    theme?: string;
    story_prompt: string;
    characters: string[];
    created_at: string;
    updated_at: string;
    stars: number;
}

export interface CreateBookParams {
    characters: string[];
    storyPrompt: string;
    ageRange: string;
    numOfPages?: number;
}