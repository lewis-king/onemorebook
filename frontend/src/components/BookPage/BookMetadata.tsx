import { Component, Show } from "solid-js";
import { Book } from "../../types/book";
import StarRating from "../StarRating";

interface BookMetadataProps {
    book: Book;
    onUpvote: (id: string, currentStars: number) => void;
}

const BookMetadata: Component<BookMetadataProps> = (props) => {
    // Use content.metadata if available, fallback to props.book fields
    const metadata = props.book.content?.metadata ?? {
        ageRange: props.book.age_range,
        theme: '',
        characters: props.book.characters ?? [],
    };
    return (
        <div class="mb-8 text-center">
            <Show when={props.book}>
                <h1 class="text-4xl font-comic text-kiddy-primary mb-4">
                    {props.book.title}
                </h1>

                <div class="flex justify-center gap-4 items-center mb-4">
                    <Show when={metadata}>
                        <span class="text-gray-600">Age Range: {metadata.ageRange}</span>
                        <span>•</span>
                        <span class="text-gray-600">Theme: {metadata.theme}</span>
                        <span>•</span>
                    </Show>
                    <StarRating
                        stars={props.book.stars}
                        onUpvote={(e) => {
                            e.preventDefault();
                            props.onUpvote(props.book.id, props.book.stars);
                        }}
                    />
                </div>

                <Show when={metadata?.characters && metadata.characters.length > 0}>
                    <div class="text-sm text-gray-500">
                        Characters: {metadata.characters.join(', ')}
                    </div>
                </Show>
            </Show>
        </div>
    );
}

export default BookMetadata;