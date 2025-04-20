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
        <div class="space-y-12 max-w-7xl mx-auto px-4 py-8">
            <WelcomeHero />

            <CategoryFilter
                selected={selectedCategory()}
                onSelect={setSelectedCategory}
            />

            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
                <Show when={!books.loading} fallback={<div class="text-center text-lg font-comic text-gray-400 py-12 animate-pulse">Loading books...</div>}>
                    <Show when={filteredBooks().length > 0} fallback={
                        <div class="col-span-full flex flex-col items-center justify-center py-16">
                          <div class="text-5xl mb-4 animate-bounce">🦄</div>
                          <div class="text-2xl font-comic text-kiddy-primary mb-2">No stories yet!</div>
                          <div class="text-lg text-gray-500 mb-6">Be the first to create an adventure.</div>
                          <a href="/create" class="bg-gradient-to-r from-kiddy-accent to-yellow-300 text-kiddy-primary font-comic text-lg px-8 py-4 rounded-full shadow-lg hover:scale-105 transition-transform duration-300 flex items-center gap-2">
                            <span>➕</span> <span>Create Your Story</span>
                          </a>
                        </div>
                    }>
                        <For each={filteredBooks()}>{book => <BookCard {...book} onUpvote={handleUpvote} />}</For>
                    </Show>
                </Show>
            </div>

            {/* Floating Create Story Button for mobile */}
            <a href="/create" class="fixed bottom-8 right-8 z-50 bg-gradient-to-r from-kiddy-accent to-yellow-300 text-kiddy-primary font-comic text-lg px-6 py-4 rounded-full shadow-xl hover:scale-110 transition-transform duration-300 flex items-center gap-2 md:hidden">
              <span>➕</span> <span>Create Story</span>
            </a>
        </div>
    );
}