import { createSignal, createResource, For, Show } from "solid-js";
import BookCard from "../components/BookCard";
import CategoryFilter from "../components/CategoryFilter";
import WelcomeHero from "../components/WelcomeHero";
import { bookService } from "../services/api";

export default function HomePage() {
    const [selectedCategory, setSelectedCategory] = createSignal('all');

    const [books, { refetch }] = createResource(bookService.listBooks);

    const handleUpvote = async (id: string, currentStars: number) => {
        await bookService.updateStars(id, currentStars);
        refetch();
    };

    const filteredBooks = () => {
        if (!books()) return [];

        // No need to sort by stars if backend already sorts, but keep fallback
        return selectedCategory() === 'all'
            ? books()
            : books().filter(book => Array.isArray(book.characters) && book.characters.includes(selectedCategory()));
    };

    return (
        <div class="space-y-8">
            <WelcomeHero />

            <CategoryFilter
                selected={selectedCategory()}
                onSelect={setSelectedCategory}
            />

            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
                <Show when={!books.loading} fallback={<div>Loading books...</div>}>
                    <For each={filteredBooks()}>
                        {book => <BookCard {...book} onUpvote={handleUpvote} />}
                    </For>
                </Show>
            </div>
        </div>
    );
}