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
    const [error, setError] = createSignal('');
    const voting = new Set<string>();
    const limit = 9;

    const fetchBooks = async (reset = false) => {
        setLoading(true);
        setError('');
        try {
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
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Could not load the library. Please try again.');
        } finally {
            setLoading(false);
            setInitialLoad(false);
        }
    };

    // Debounced scroll handler
    const handleScroll = debounce(() => {
        if (loading() || !hasMore() || error()) return;
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
        if (voting.has(id)) return;
        voting.add(id);
        try {
            const updated = await bookService.updateStars(id, currentStars);
            setBooks(prev => prev.map(book => book.id === id ? { ...book, stars: updated.stars } : book));
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Could not add your star. Please try again.');
        } finally { voting.delete(id); }
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
            

            <div id="stories" class="scroll-mt-8 text-center pt-4">
                <h2 class="font-comic text-3xl md:text-4xl text-kiddy-primary">
                    Pick tonight's story 📚
                </h2>
                <p class="font-rounded text-gray-500 mt-2 text-sm md:text-base">
                    Tap a book to open it up and read together
                </p>
            </div>

            <Show when={error()}>
                <div role="alert" class="rounded-xl bg-red-50 p-4 text-red-800">
                    <p>{error()}</p>
                    <button onClick={() => fetchBooks(true)} class="mt-2 underline">Try again</button>
                </div>
            </Show>
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
                <Show when={!initialLoad()} fallback={
                    <div class="col-span-full grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8" aria-hidden="true">
                        <span class="sr-only">Loading books...</span>
                        <For each={Array.from({ length: 6 }, (_, i) => i)}>{() => (
                            <div class="bg-white rounded-2xl overflow-hidden shadow-xl shadow-kiddy-primary/10">
                                <div class="aspect-[4/3] bg-gradient-to-br from-gray-100 to-gray-200 animate-pulse"></div>
                                <div class="p-6 space-y-3">
                                    <div class="h-6 rounded-full bg-gray-200 animate-pulse w-3/4"></div>
                                    <div class="h-4 rounded-full bg-gray-200 animate-pulse w-1/2"></div>
                                    <div class="h-11 rounded-full bg-gray-200 animate-pulse mt-6"></div>
                                </div>
                            </div>
                        )}</For>
                    </div>
                }>
                    <Show when={filteredBooks().length > 0} fallback={
                        <div class="col-span-full flex flex-col items-center justify-center py-16">
                          <div class="text-5xl mb-4 animate-bounce">🦄</div>
                          <div class="text-2xl font-comic text-kiddy-primary mb-2">No stories yet!</div>
                          <div class="text-lg text-gray-500 mb-6">New bedtime adventures will appear here.</div>
                        </div>
                    }>
                        <For each={filteredBooks()}>{(book, index) => (
                            <div class="animate-fade-up h-full" style={{ "animation-delay": `${Math.min(index(), 8) * 70}ms` }}>
                                <BookCard {...book} onUpvote={handleUpvote} />
                            </div>
                        )}</For>
                        <Show when={loading() && !initialLoad()}>
                            <div class="col-span-full flex justify-center py-8">
                                <div class="animate-spin rounded-full h-8 w-8 border-t-4 border-b-4 border-kiddy-accent"></div>
                                <span class="ml-4 text-lg text-gray-400 font-comic">Loading more books…</span>
                            </div>
                        </Show>
                    </Show>
                </Show>
            </div>

        </div>
    );
}
