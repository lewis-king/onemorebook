import { createSignal, onCleanup, onMount, For, Show, createMemo } from "solid-js";
import { Book } from '../types/book';
import BookCard from "../components/BookCard";
// import CategoryFilter from "../components/CategoryFilter";
import WelcomeHero from "../components/WelcomeHero";
import { bookService } from "../services/api";

// Debounce utility
function debounce(fn: (...args: any[]) => void, delay: number) {
  let timeout: ReturnType<typeof setTimeout>;
  return (...args: any[]) => {
    clearTimeout(timeout);
    timeout = setTimeout(() => fn(...args), delay);
  };
}

export default function HomePage() {
    const [selectedCategory] = createSignal('all');
    const [books, setBooks] = createSignal<Book[]>([]);
    const [loading, setLoading] = createSignal(false);
    const [hasMore, setHasMore] = createSignal(true);
    const [offset, setOffset] = createSignal(0);
    const [initialLoad, setInitialLoad] = createSignal(true);
    const limit = 9;

    const fetchBooks = async (reset = false) => {
        setLoading(true);
        const newBooks = await bookService.listBooks({ limit, offset: reset ? 0 : offset() });
        if (reset) {
            setBooks(newBooks);
            setOffset(newBooks.length);
            setInitialLoad(false);
        } else {
            setBooks(prev => [...prev, ...newBooks]);
            setOffset(prev => prev + newBooks.length);
        }
        setHasMore(newBooks.length === limit);
        setLoading(false);
    };

    // Debounced scroll handler
    const handleScroll = debounce(() => {
        if (loading() || !hasMore()) return;
        if (window.innerHeight + window.scrollY >= document.body.offsetHeight - 300) {
            fetchBooks();
        }
    }, 200);

    onMount(() => {
        fetchBooks(true);
        window.addEventListener('scroll', handleScroll);
    });

    onCleanup(() => {
        window.removeEventListener('scroll', handleScroll);
    });

    // Optimized upvote: update local state only
    const handleUpvote = async (id: string, currentStars: number) => {
        await bookService.updateStars(id, currentStars);
        setBooks(prev => prev.map(book => book.id === id ? { ...book, stars: currentStars } : book));
    };

    // Memoized filteredBooks
    const filteredBooks = createMemo(() => {
        if (!books()) return [];
        return selectedCategory() === 'all'
            ? books()
            : books().filter((book: Book) => Array.isArray(book.characters) && book.characters.includes(selectedCategory()));
    });

    return (
        <div class="space-y-12 max-w-7xl mx-auto px-4 py-8">
            <WelcomeHero />

            {/* <CategoryFilter
                selected={selectedCategory()}
                onSelect={cat => {
                    // setSelectedCategory(cat);
                    setOffset(0);
                    fetchBooks(true);
                }}
            /> */}
            

            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
                <Show when={!initialLoad()} fallback={<div class="text-center text-lg font-comic text-gray-400 py-12 animate-pulse">Loading books...</div>}>
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
                        <Show when={loading() && !initialLoad()}>
                            <div class="col-span-full flex justify-center py-8">
                                <div class="animate-spin rounded-full h-8 w-8 border-t-4 border-b-4 border-kiddy-accent"></div>
                                <span class="ml-4 text-lg text-gray-400 font-comic">Loading more books…</span>
                            </div>
                        </Show>
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