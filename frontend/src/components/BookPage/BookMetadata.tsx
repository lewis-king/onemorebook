import { Component, Show } from "solid-js";
import { Book } from "../../types/book";
import StarRating from "../StarRating";

interface BookMetadataProps {
    book: Book;
    onUpvote: (id: string, currentStars: number) => void;
}

const BookMetadata: Component<BookMetadataProps> = (props) => {
    return (
        <div class="mb-8 text-center">
            <Show when={props.book}>
                <h1 class="text-4xl font-comic text-kiddy-primary mb-4">
                    {props.book.title}
                </h1>

                <div class="flex justify-center gap-4 items-center mb-4">
                    <Show when={props.book.metadata}>
                        <span class="text-gray-600">Age Range: {props.book.metadata.ageRange}</span>
                        <span>•</span>
                        <span class="text-gray-600">Theme: {props.book.metadata.theme}</span>
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

                <Show when={props.book.metadata?.characters}>
                    <div class="text-sm text-gray-500">
                        Characters: {props.book.metadata.characters.join(', ')}
                    </div>
                </Show>
            </Show>
        </div>
    );
};

export default BookMetadata;