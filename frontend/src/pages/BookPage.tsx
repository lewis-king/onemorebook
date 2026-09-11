import { createResource, createSignal, Show, createEffect, onMount, onCleanup } from "solid-js";
import { useParams } from "@solidjs/router";
import { bookService } from "../services/api";
import { BookSpread } from "../components/BookPage/BookSpread";
import PageControls from "../components/BookPage/PageControls";
// import StarRating from "../components/StarRating";

export default function BookPage() {
    const params = useParams();
    // Guard: only fetch if params.id is defined and not 'undefined'
    const validId = params.id && params.id !== 'undefined';
    const [book] = createResource(() => validId ? params.id : undefined, bookService.getBook);
    const [currentPage, setCurrentPage] = createSignal(0);
    const [error, setError] = createSignal<string | null>(null);
    const [pageFlipInstance, setPageFlipInstance] = createSignal<any>(null);
    const [stars, setStars] = createSignal<number>(0);
    let voting = false;

    // Sync stars signal with book data when book loads/changes
    createEffect(() => {
        if (book.error) return;
        const current = book();
        if (current && typeof current.stars === 'number') {
            setStars(current.stars);
        }
    });

    // Helper to extract page content and images from new structure
    const getPages = () => {
        const b = book();
        if (!b || !b.content || !Array.isArray(b.content.pages)) return [];
        // Insert a placeholder for the cover at index 0, then all story pages, then a placeholder for the rating/ending page
        return [""]
            .concat(b.content.pages.map(p => p.text || ""))
            .concat([""]); // for the rating/ending page
    };
    const getPageImages = () => {
        const b = book();
        if (!b || !b.content || !Array.isArray(b.content.pages)) return [];
        const baseUrl = `https://kwhyhflyyjhtbvbmtdmt.supabase.co/storage/v1/object/public/book-imgs/${b.id}`;
        // First image is the cover, then the rest are story pages. No placeholder at the end!
        return [{ url: getCoverImage() }]
            .concat(b.content.pages.map((page, i) => ({
                url: page.imageUrl || `${baseUrl}/page_${i+1}.png`,
                fallbackUrl: `${baseUrl}/page${i+1}.jpg`
            })));
    };
    const getCoverImage = () => {
        const b = book();
        return b?.cover_image_url || `https://kwhyhflyyjhtbvbmtdmt.supabase.co/storage/v1/object/public/book-imgs/${b?.id ?? ''}/cover.jpg`;
    };

    const handleUpvote = async (id: string, currentStars: number) => {
        if (voting) return;
        voting = true;
        try {
            const updated = await bookService.updateStars(id, currentStars);
            setStars(updated.stars);
        } catch (e) {
            console.error('Error updating stars:', e);
            setError(e instanceof Error ? e.message : 'Failed to update stars');
        } finally { voting = false; }
    };


    // Helper for Next/Back with animation
    const handlePrevious = () => {
        const flip = pageFlipInstance();
        if (flip && flip.flipPrev) {
            flip.flipPrev();
        } else if (currentPage() > 0) {
            setCurrentPage(currentPage() - 1);
        }
    };
    const handleNext = () => {
        const flip = pageFlipInstance();
        if (flip && flip.flipNext) {
            flip.flipNext();
        } else if (currentPage() < getPages().length - 1) {
            setCurrentPage(currentPage() + 1);
        }
    };

    // Flip pages with the keyboard arrow keys too
    const handleKeyDown = (e: KeyboardEvent) => {
        if (e.key === 'ArrowLeft') handlePrevious();
        else if (e.key === 'ArrowRight') handleNext();
        else if (e.key === 'Escape' && isFullscreen()) exitReaderFullscreen();
    };
    onMount(() => window.addEventListener('keydown', handleKeyDown));
    onCleanup(() => window.removeEventListener('keydown', handleKeyDown));

    // Full screen ("Big screen") reading mode
    let readerRef: HTMLDivElement | undefined;
    const [isFullscreen, setIsFullscreen] = createSignal(false);

    const refreshBookSize = () => {
        // Let the new layout settle, then re-measure the flipbook
        setTimeout(() => pageFlipInstance()?.update?.(), 150);
    };

    const handleFullscreenChange = () => {
        setIsFullscreen(!!document.fullscreenElement);
        refreshBookSize();
    };

    const enterReaderFullscreen = async () => {
        try {
            if (readerRef?.requestFullscreen) {
                await readerRef.requestFullscreen();
            } else {
                setIsFullscreen(true); // immersive fallback (e.g. iPhone Safari)
                refreshBookSize();
            }
        } catch {
            setIsFullscreen(true); // browser refused; still give the big view
            refreshBookSize();
        }
    };

    const exitReaderFullscreen = () => {
        if (document.fullscreenElement) {
            document.exitFullscreen().catch(() => {});
        }
        setIsFullscreen(false);
        refreshBookSize();
    };

    const toggleFullscreen = () => {
        if (isFullscreen()) exitReaderFullscreen();
        else enterReaderFullscreen();
    };

    onMount(() => document.addEventListener('fullscreenchange', handleFullscreenChange));
    onCleanup(() => {
        document.removeEventListener('fullscreenchange', handleFullscreenChange);
        // Leaving the book (e.g. Back to Stories) must not strand the browser in full screen
        if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    });

    return (
        <div
            ref={readerRef}
            class={`w-full flex flex-col items-center justify-center ${isFullscreen() ? 'reader-fullscreen' : 'max-w-[1600px] mx-auto px-1 md:px-4 lg:px-12'}`}
        >
            <Show when={book.error}>
                <div role="alert" class="rounded-xl bg-red-50 p-6 text-red-800">
                    <p>{book.error?.message || 'Could not load this book.'}</p>
                    <a href="/" class="underline">Back to stories</a>
                </div>
            </Show>
            <Show when={error()}>
                <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">
                    {error()}
                </div>
            </Show>

            {/* Add PageControls above the book */}
            <Show when={!book.error && !book.loading && book()}>
                <PageControls
                    currentPage={currentPage()}
                    totalPages={getPages().length}
                    onPrevious={handlePrevious}
                    onNext={handleNext}
                    fullscreen={isFullscreen()}
                    onToggleFullscreen={toggleFullscreen}
                />
            </Show>

            <Show
                when={!book.error && !book.loading && book()}
                fallback={
                    <div class="text-center py-20">
                        <Show when={!book.error}>
                            <div class="text-6xl mb-4 animate-bounce">📖</div>
                            <div class="text-xl font-comic text-kiddy-primary animate-pulse">Opening your story...</div>
                        </Show>
                    </div>
                }
            >
                <BookSpread
                    pages={getPages()}
                    coverImage={getCoverImage()}
                    pageImages={getPageImages()}
                    onPageFlipInit={setPageFlipInstance}
                    onPageChange={setCurrentPage}
                    bookId={book()?.id ?? ''}
                    stars={stars()}
                    onUpvote={handleUpvote}
                    currentPage={currentPage()} // Pass currentPage prop
                />
            </Show>
        </div>
    );
}
