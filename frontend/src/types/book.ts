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

export interface UploadStoryPage {
    text: string;
    pageNumber: number;
    imagePrompt: string;
    charactersPresent?: string[];
    isMainCharacterPresent?: boolean;
}

export interface UploadStoryMetadata {
    title: string;
    theme: string;
    bookSummary: string;
    mainCharacterDescriptivePrompt: string;
    coverImagePrompt: string;
    styleReferencePrompt: string;
    ageRange: string;
    characters: string[];
    storyPrompt: string;
}

export interface UploadStoryParams {
    story: {
        pages: UploadStoryPage[];
        metadata: UploadStoryMetadata;
    };
    coverImageBase64: string;
    pageImages: {
        pageNumber: number;
        imageBase64: string;
    }[];
    characterImages?: {
        name: string;
        imageBase64: string;
    }[];
}

export interface UpdateStoryParams {
    story: {
        pages: UploadStoryPage[];
        metadata: UploadStoryMetadata;
    };
    coverImageBase64?: string;
    pageImages?: {
        pageNumber: number;
        imageBase64: string;
    }[];
    characterImages?: {
        name: string;
        imageBase64: string;
    }[];
}